#!/usr/bin/env python3
"""
fetch_and_score.py
------------------
Pulls open jobs from each ATS, filters by Strategy/BizOps title + Toronto/remote-
Canada location + recency, fetches the JD, and scores relevant jobs against the
candidate profile in two stages (cheap Haiku screen -> Sonnet confirm for the
promising few), then upserts matches into Supabase. The candidate profile +
rubric ride in a cached system block to keep per-call token cost down.

Title classification (Strategy + BizOps families) and the Toronto/remote-Canada
location filter live in filters.py, shared with expand_companies.py.

Env vars (GitHub Actions secrets):
  SUPABASE_URL          https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  service_role key
  ANTHROPIC_API_KEY     Claude API key

Optional (cost/behavior knobs):
  SCORE_THRESHOLD       Min score to store a match (default: 65)
  SCORE_MODEL_STAGE1    Cheap screening model (default: claude-haiku-4-5)
  SCORE_MODEL_STAGE2    Confirmation model (default: claude-sonnet-5)
  STAGE1_PASS           Haiku score that escalates to Sonnet (default: 55)
  JD_MAX_CHARS          JD chars sent to the model (default: 3000)
  FIRST_RUN_DAYS        Back-catalog window for a new company (default: 7)
  MAX_YEARS_REQUIRED    JD years-of-experience ceiling (default: 5)
  DRY_RUN               "true" = fetch + filter only: no Claude calls, no DB
                        writes. Free. Use to validate before a real run.
  MAX_COMPANIES         Cap companies processed (0 = all). Quick smoke tests.
"""

import os, json, time, logging, random, re
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

# Role classification + Toronto/remote-Canada location filters live in
# filters.py so they stay identical between this daily pipeline and
# expand_companies.py (discovery).
from filters import classify_role, is_ca_location, _SENIORITY_RE as _TOO_SENIOR_RE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("watchlist")

# ── Config ─────────────────────────────────────────────────────────────────────

SUPABASE_URL         = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SCORE_THRESHOLD      = int(os.getenv("SCORE_THRESHOLD", "65"))

# Dry run: fetch + filter + log only. No Claude calls (so no cost) and no
# Supabase writes. Everything read-only still runs, so the log shows exactly
# which postings a real run would have scored.
DRY_RUN       = os.getenv("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
MAX_COMPANIES = int(os.getenv("MAX_COMPANIES", "0") or "0")

# Only required for a real run — a dry run never calls the API, so it can run
# without a key (handy for validating filters locally before paying for anything).
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "") if DRY_RUN else os.environ["ANTHROPIC_API_KEY"]

# Two-stage scoring to keep cost down: a cheap Haiku pass screens every job, and
# only jobs that clear STAGE1_PASS get the authoritative (pricier) Sonnet verdict.
# ~97% of jobs are rejected, so this keeps the expensive model off the rejects.
SCORE_MODEL_STAGE1 = os.getenv("SCORE_MODEL_STAGE1", "claude-haiku-4-5")   # screen
SCORE_MODEL_STAGE2 = os.getenv("SCORE_MODEL_STAGE2", "claude-sonnet-5")    # confirm
STAGE1_PASS        = int(os.getenv("STAGE1_PASS", "55"))   # Haiku >= this -> Sonnet
JD_MAX_CHARS       = int(os.getenv("JD_MAX_CHARS", "3000"))  # JD chars sent to the model

# Per-run call counters, surfaced in the final log line for cost visibility.
SCORE_STATS = {
    "stage1": 0, "stage2": 0,
    # Cache diagnostics — Anthropic warns when cache_control is set but never
    # hits (e.g. our ~1,800-token prefix is below Haiku 4.5's 4,096-tok minimum
    # so Haiku silently doesn't cache). Track per-model so the summary shows
    # which stage is actually caching.
    "cache_reads": {},    # {model: total tokens read from cache}
    "cache_writes": {},   # {model: total tokens written to cache}
    "input_tokens": {},   # {model: total uncached input tokens billed at full price}
}

HEADERS_SB = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

# Recency windows:
#   - A company already in the DB fetches only its recent postings (~last 24h).
#   - A brand-new company (no jobs yet) seeds a 30-day back-catalog on first run.
# NOTE: postings with no date (all Workday, some others) can't be dated, so they
# are always kept regardless of either window.
CUTOFF_HOURS   = 26  # slightly over 24h to avoid missing jobs near the boundary
FIRST_RUN_DAYS = int(os.getenv("FIRST_RUN_DAYS", "7"))  # back-catalog window the first time a company is seen

# ── Candidate profile ──────────────────────────────────────────────────────────
# Lives in profile/candidate_profile.md so it can be edited without touching code.

_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "profile", "candidate_profile.md")
with open(_PROFILE_PATH) as _f:
    CANDIDATE_PROFILE = _f.read()

# ── Filters ────────────────────────────────────────────────────────────────────
# The Strategy/BizOps title classifier (classify_role) and the Toronto/remote-
# Canada location check (is_ca_location) are imported from filters.py — the
# single source of truth shared with expand_companies.py.


def is_recent(posted_at: Optional[str], cutoff: datetime) -> bool:
    """Return True if posted_at is within the cutoff window, or if date is unknown."""
    if not posted_at:
        return True  # no date = keep it, we can't tell
    try:
        dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except Exception:
        return True  # parse failure = keep it


def should_keep(title: str, location: str, posted_at: Optional[str], cutoff: Optional[datetime]) -> bool:
    if classify_role(title) is None:
        return False
    if not is_ca_location(location):
        return False
    if cutoff and not is_recent(posted_at, cutoff):
        return False
    return True


# ── ATS Fetchers ───────────────────────────────────────────────────────────────

def fetch_greenhouse(slug: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        return [
            {
                "ats_job_id": str(j["id"]),
                "title":      j.get("title", ""),
                "location":   (j.get("location") or {}).get("name", ""),
                "url":        j.get("absolute_url", ""),
                "posted_at":  j.get("updated_at"),
                "raw_jd":     "",
            }
            for j in r.json().get("jobs", [])
        ]
    except Exception as e:
        log.warning(f"Greenhouse {slug}: {e}")
        return []


def fetch_greenhouse_jd(job_id: str, slug: str) -> str:
    try:
        r = httpx.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}",
            timeout=15,
        )
        r.raise_for_status()
        return _strip_html(r.json().get("content", ""))
    except Exception:
        return ""


def _ashby_location(j: dict) -> str:
    """Ashby splits location across `location` + `secondaryLocations`. Join them
    so a role listed as Vancouver-primary / Toronto-secondary still matches the
    GTA filter instead of being dropped on the primary alone."""
    parts = [j.get("location") or ""]
    for sec in (j.get("secondaryLocations") or []):
        loc = sec.get("location") if isinstance(sec, dict) else None
        if loc:
            parts.append(loc)
    return "; ".join(p for p in parts if p)


def fetch_ashby(slug: str) -> list[dict]:
    # NOTE: the posting API returns {"jobs": [...]} with a "location" field.
    # This previously read "jobPostings"/"locationName" (Ashby's *private* board
    # schema), so every Ashby company silently returned zero jobs. Verified
    # against the live endpoint — keys are: id, title, location,
    # secondaryLocations, jobUrl, publishedAt, descriptionHtml, isListed.
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        return [
            {
                "ats_job_id": j.get("id", ""),
                "title":      j.get("title", ""),
                "location":   _ashby_location(j),
                "url":        j.get("jobUrl", ""),
                "posted_at":  j.get("publishedAt"),
                "raw_jd":     _strip_html(j.get("descriptionHtml", "")),
            }
            for j in r.json().get("jobs", [])
            if j.get("isListed") is not False
        ]
    except Exception as e:
        log.warning(f"Ashby {slug}: {e}")
        return []


def fetch_lever(slug: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        return [
            {
                "ats_job_id": j.get("id", ""),
                "title":      j.get("text", ""),
                "location":   (j.get("categories") or {}).get("location", ""),
                "url":        j.get("hostedUrl", ""),
                "posted_at":  datetime.fromtimestamp(
                                  j["createdAt"] / 1000, tz=timezone.utc
                              ).isoformat() if j.get("createdAt") else None,
                # Lever's list endpoint already includes the full JD, so no
                # per-posting call is needed (unlike Greenhouse/Workday).
                "raw_jd":     _strip_html(j.get("descriptionPlain") or j.get("description") or ""),
            }
            for j in r.json()
        ]
    except Exception as e:
        log.warning(f"Lever {slug}: {e}")
        return []


def fetch_workday(slug: str) -> list[dict]:
    """
    slug format: 'wd{N}/{tenant}/{site}', e.g. 'wd5/nvidia/nvidiaexternalcareersite'
    (see sql/seed.sql header for the format reminder).

    Workday has no public REST API. This calls the same undocumented JSON
    endpoint their own careers-page widget uses. Capped at 100 postings per
    company (5 pages) — plenty to find Strategy/BizOps roles without hammering a tenant
    that has thousands of open reqs.
    """
    try:
        wd_host, tenant, site = slug.split("/", 2)
    except ValueError:
        log.warning(f"Workday slug malformed (expected wdN/tenant/site): {slug}")
        return []

    base = f"https://{tenant}.{wd_host}.myworkdayjobs.com"
    api_url = f"{base}/wday/cxs/{tenant}/{site}/jobs"

    postings, offset, limit, max_pages = [], 0, 20, 5
    try:
        for _ in range(max_pages):
            r = httpx.post(
                api_url,
                json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                headers={"content-type": "application/json"},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            batch = data.get("jobPostings", [])
            if not batch:
                break
            for j in batch:
                ext_path = j.get("externalPath", "")
                job_id = ext_path.rsplit("_", 1)[-1] if ext_path else ext_path
                postings.append({
                    "ats_job_id": job_id or ext_path or j.get("title", ""),
                    "title":      j.get("title", ""),
                    "location":   j.get("locationsText", "") or "",
                    "url":        f"{base}/{site}{ext_path}" if ext_path else base,
                    # Workday only exposes relative strings ("Posted Today"), not
                    # real timestamps, so posted_at stays unknown -> is_recent() keeps it.
                    "posted_at":  None,
                    "raw_jd":     "",
                    # Kept for JD hydration in main(); ignored by the upsert.
                    "_ext_path":  ext_path,
                })
            offset += limit
            if offset >= data.get("total", 0):
                break
            time.sleep(0.15)
    except Exception as e:
        log.warning(f"Workday {slug}: {e}")
    return postings


def fetch_workday_jd(slug: str, ext_path: str) -> str:
    """Fetch a single Workday posting's full JD from the same cxs endpoint the
    careers widget uses. `slug` is 'wd{N}/{tenant}/{site}', `ext_path` is the
    posting's externalPath (starts with '/')."""
    if not ext_path:
        return ""
    try:
        wd_host, tenant, site = slug.split("/", 2)
    except ValueError:
        return ""
    url = f"https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{ext_path}"
    try:
        r = httpx.get(url, headers={"content-type": "application/json"}, timeout=15)
        r.raise_for_status()
        info = r.json().get("jobPostingInfo", {}) or {}
        return _strip_html(info.get("jobDescription", ""))
    except Exception:
        return ""


ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "ashby":      fetch_ashby,
    "lever":      fetch_lever,
    "workday":    fetch_workday,
}

# ── Claude Scoring ─────────────────────────────────────────────────────────────
# Models are configured above (SCORE_MODEL_STAGE1 / STAGE2).

SCORE_SYSTEM = """You are a job-fit evaluator for one specific candidate. Judge how well THIS candidate fits THIS role. Company prestige is irrelevant: a famous firm's role that rigidly demands 5+ years of pure corporate-strategy experience is a BAD fit and must score low.

Output ONLY valid JSON (no markdown, no prose). Exactly these fields:
  score            integer 0-100
  role_family      "strategy" | "bizops" | "other"      (which lens you judged with)
  role_fit         "strong" | "moderate" | "weak"
  level_fit        "strong" | "moderate" | "weak"
  location_fit     "strong" | "moderate" | "weak"
  years_required   integer or null   (max years of experience the JD demands; null if unstated)
  meets_experience true | false      (does the candidate qualify under the candidate's years-of-experience rule?)
  blocker          true | false      (does it require US citizenship/US-only work authorization, a US federal security clearance, or explicitly require a location outside Canada?)
  reasoning        string, max 120 chars, plain English

Which lens to use (role_family):
  - "strategy" = Corporate Strategy / Strategy Consulting / Corporate Development roles. Judge structured-analysis + executive-facing fit (breaking down ambiguous problems, building the recommendation, presenting to leadership).
  - "bizops"   = Business Operations / Revenue Operations / Sales Operations / Ops Analyst-Manager roles. Judge "builds the dashboards/process/reporting that run the business" fit — process + data fluency, cross-functional execution.
  - "other" = neither. Set role_fit weak.
A title-screen guess is provided, but decide for yourself from the JD.

DIMENSION RUBRICS:

ROLE FIT (does the role type match a target family + the candidate's strengths?):
  strong:   A Strategy or BizOps role squarely in the candidate's wheelhouse — tech/fintech/SaaS client base, cross-functional advisory or corp-dev work, dashboard/KPI/reporting ownership, M&A or market analysis.
  moderate: A legitimate Strategy/BizOps role in a viable but less-preferred industry (traditional/non-tech B2B, retail, healthcare, consumer) the candidate could still do well in.
  weak:     Not really a target role — the title is actually EM, designer, pure financial/investment analyst, program/project manager, marketing, or a physical/warehouse ops role (role_family "other") — or it demands deep domain expertise the candidate lacks (e.g. requires a CPA/CFA, requires 5+ years of hands-on software engineering).

LEVEL FIT (apply the candidate's years-of-experience rule literally — the candidate has ~2 years of post-university experience, so BE STRICT here; an over-scored senior role wastes their time):
  strong:   JD asks for ~1-3 years of consulting/strategy/analyst/operations experience, OR uses "Associate"/"Analyst"/"Senior Associate" language, OR explicitly accepts consulting-to-industry transitions.
  moderate: JD asks ~3-5 years, OR says "Manager" but the described scope is individual-contributor (no direct reports), OR accepts "consulting or equivalent" broadly.
  weak:     JD requires 5+ years, OR requires people management / direct reports, OR is Senior Manager / Principal / Director / VP / Head-of level, OR rigidly requires PURE in-house strategy-operations tenure with no consulting-equivalent clause. -> meets_experience false.

TITLE-LEVEL CEILING (applies regardless of what the JD body says): the candidate has ~2 years of experience. Any role titled "Senior Manager", "Sr. Manager", "Senior <function> Manager", "Principal", "Director", "VP", or "Head of" is ABOVE their level -> level_fit weak, meets_experience false. Titles at or below "Manager" / "Senior Analyst" / "Senior Associate" / "Lead" are in range and should be judged on the JD's stated years requirement.

LOCATION FIT:
  strong:   Toronto/GTA (any specific GTA city), Remote with Canada-wide eligibility, or unspecified. Never penalize a specific GTA city.
  moderate: Canada-eligible but ambiguous (e.g. bare "Canada" with no city).
  weak:     A real but non-GTA Canadian city with no remote option (e.g. Vancouver-only, Montreal-only, on-site), or genuinely non-Canadian, or requires relocation outside Canada.

BLOCKER: set blocker true only if the JD requires US citizenship or US-only work authorization, an active US federal security clearance, or explicitly states the role must be based outside Canada with no remote option. The candidate is a Canadian citizen, so Canadian-authorization requirements are never a blocker.

SCORING FORMULA — start at 75, then adjust:
  role_fit:     strong +15 | moderate +5 | weak -20
  level_fit:    strong +10 | moderate +0 | weak -25
  location_fit: strong +5  | moderate +0 | weak -15
Cap at 100, floor at 0. A weak level_fit must land the role below 65.

If blocker is true, the role is unusable regardless of fit: set score to 0.
If the JD is empty/unavailable, score from title + location only, note that in reasoning, and discount role_fit by one tier.
"""


# The rubric + candidate profile are byte-identical on every call, so put them in
# a cached `system` block. On a warm cache (calls are <1s apart within a run) these
# ~1,100 tokens bill at 0.1x instead of full price on every one of ~1,300 calls.
# Caches are per-model, so both stages get their own warm cache. No beta header
# needed for basic ephemeral caching on the raw HTTP API.
SCORE_SYSTEM_BLOCKS = [{
    "type": "text",
    "text": SCORE_SYSTEM + "\n\nCANDIDATE PROFILE:\n" + CANDIDATE_PROFILE,
    "cache_control": {"type": "ephemeral"},
}]


def _call_model(model: str, title: str, location: str, raw_jd: str,
                role_family: Optional[str] = None) -> Optional[dict]:
    """One scoring call against `model`. Returns the guarded verdict dict, or None
    on any failure. The candidate profile lives in the cached system block, so the
    user message carries only the varying job."""
    prompt = (
        f"TITLE-SCREEN ROLE FAMILY GUESS: {role_family or 'unknown'}\n\n"
        f"JOB:\nTitle: {title}\nLocation: {location}\n\n"
        f"Description:\n{(raw_jd or '')[:JD_MAX_CHARS]}"
    )
    payload = {
        "model": model,
        "max_tokens": 1024,
        "system": SCORE_SYSTEM_BLOCKS,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Sonnet 5 (and other 4.6+ models) run adaptive thinking by DEFAULT, which eats
    # max_tokens and truncates the JSON — disable it. Haiku 4.5 doesn't think by
    # default and rejects {"type":"disabled"}, so for it we leave thinking off by
    # omission rather than sending the (invalid) disable flag.
    if "haiku" not in model:
        payload["thinking"] = {"type": "disabled"}
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=45,
        )
        r.raise_for_status()
        body = r.json()
        # Track cache usage per model so we can see if caching is actually firing.
        u = body.get("usage") or {}
        SCORE_STATS["cache_reads"][model]  = SCORE_STATS["cache_reads"].get(model, 0)  + int(u.get("cache_read_input_tokens") or 0)
        SCORE_STATS["cache_writes"][model] = SCORE_STATS["cache_writes"].get(model, 0) + int(u.get("cache_creation_input_tokens") or 0)
        SCORE_STATS["input_tokens"][model] = SCORE_STATS["input_tokens"].get(model, 0) + int(u.get("input_tokens") or 0)
        # Pick the text block explicitly rather than assuming content[0].
        blocks = body.get("content", [])
        text = next((b.get("text", "") for b in blocks if b.get("type") == "text"), "").strip()
        text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        # Parse the FIRST JSON object and ignore anything after it. Haiku is
        # chattier than Sonnet and often appends a sentence of explanation after
        # the JSON despite "output only JSON" — plain json.loads() then throws
        # "Extra data", which was silently dropping ~14% of scores. raw_decode
        # reads one value and stops; skipping to the first "{" also tolerates any
        # leading prose.
        start = text.find("{")
        if start > 0:
            text = text[start:]
        res, _ = json.JSONDecoder().raw_decode(text)
        return _apply_score_guards(res, title)
    except Exception as e:
        log.warning(f"Score failed ({model}) for '{title}': {e}")
        return None


def score_job(title: str, location: str, raw_jd: str, role_family: Optional[str] = None) -> Optional[dict]:
    """Two-stage scorer. The cheap Haiku screen runs on every job; only jobs that
    clear STAGE1_PASS get the authoritative (pricier) Sonnet verdict — so the
    expensive model never spends tokens rejecting the ~97% that don't fit."""
    SCORE_STATS["stage1"] += 1
    screen = _call_model(SCORE_MODEL_STAGE1, title, location, raw_jd, role_family)
    if screen is None:
        return None
    if int(screen.get("score", 0)) >= STAGE1_PASS:
        SCORE_STATS["stage2"] += 1
        confirmed = _call_model(SCORE_MODEL_STAGE2, title, location, raw_jd, role_family)
        if confirmed is not None:
            return confirmed  # Sonnet is authoritative
        # Sonnet failed — keep the Haiku screen rather than dropping the job.
    return screen


# Years-required ceiling: with ~2 years of experience, a JD demanding 5+ years
# is out of range no matter how well the rest of it reads.
MAX_YEARS_REQUIRED = int(os.getenv("MAX_YEARS_REQUIRED", "5"))


def _apply_score_guards(res: dict, title: str = "") -> dict:
    """Deterministic caps so a good-sounding JD can't sneak past the real
    disqualifiers, independent of model wording. Also folds role family +
    years-required into the stored reasoning so the board shows them without
    a schema change."""
    try:
        score = int(res.get("score", 0))
    except (TypeError, ValueError):
        score = 0

    # Title-level ceiling, enforced in code rather than trusting the prompt.
    # classify_role() already drops these before scoring, so this only fires on
    # a title that slipped through a wording we didn't anticipate.
    too_senior = bool(_TOO_SENIOR_RE.search(title or ""))

    # Years ceiling: the model reports years_required; anything at or above the
    # cap is a level miss regardless of the score it assigned.
    yrs = res.get("years_required")
    years_miss = isinstance(yrs, int) and yrs >= MAX_YEARS_REQUIRED

    # Hard blocker (citizenship / clearance / green card / no-sponsorship): unusable.
    if res.get("blocker") is True:
        score = 0
    # Experience/level miss: keep it below the match threshold regardless of how
    # the model scored it (a weak level_fit, an explicit experience miss, a
    # too-senior title, or a years requirement past the cap).
    elif (res.get("level_fit") == "weak" or res.get("meets_experience") is False
          or too_senior or years_miss):
        score = min(score, 55)
        if too_senior or years_miss:
            res["level_fit"] = "weak"
            res["meets_experience"] = False

    res["score"] = max(0, min(100, score))

    fam = res.get("role_family")
    yrs = res.get("years_required")
    tag = ""
    if fam:
        tag = f"[{fam}" + (f", {yrs}y req" if isinstance(yrs, int) else "") + "] "
    res["reasoning"] = (tag + (res.get("reasoning") or ""))[:240]
    return res


# ── Supabase helpers ───────────────────────────────────────────────────────────

def sb_get(path: str, params: dict = None) -> list[dict]:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers=HEADERS_SB,
        params=params,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def sb_upsert(table: str, rows: list[dict], on_conflict: str):
    if not rows:
        return
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**HEADERS_SB, "Prefer": "resolution=merge-duplicates,return=minimal"},
        params={"on_conflict": on_conflict},
        json=rows,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        log.error(f"Upsert {table} failed: {r.status_code} {r.text[:300]}")
    else:
        log.info(f"  upserted {len(rows)} rows -> {table}")


def sb_patch(table: str, filters: dict, data: dict):
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=HEADERS_SB,
        params={k: f"eq.{v}" for k, v in filters.items()},
        json=data,
        timeout=20,
    )
    if r.status_code not in (200, 204):
        log.warning(f"PATCH {table} {filters}: {r.status_code} {r.text[:200]}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("=== Watchlist pipeline starting ===")
    if DRY_RUN:
        log.info("*** DRY RUN — no Claude calls, no database writes. Nothing is billed. ***")

    companies = sb_get("companies", {"active": "eq.true", "select": "*"})
    log.info(f"Loaded {len(companies)} active companies")

    # Load existing open jobs for closed-detection
    existing_jobs = sb_get("jobs", {"status": "eq.open", "select": "id,company_id,ats_job_id"})
    existing_map  = {(j["company_id"], j["ats_job_id"]): j["id"] for j in existing_jobs}

    # Build a set of company_ids that already have jobs in the DB
    # These get the 26h recency filter; new companies get all jobs on first run
    companies_with_jobs = {j["company_id"] for j in existing_jobs}

    seen_this_run: set[tuple] = set()
    _now = datetime.now(timezone.utc)
    cutoff           = _now - timedelta(hours=CUTOFF_HOURS)
    first_run_cutoff = _now - timedelta(days=FIRST_RUN_DAYS)

    # Process order: FIRST-RUN companies (never seen before) first, then the
    # known set in a fresh random order each run. Two wins:
    #  - New discoveries always get their back-catalog seeded, even when we hit
    #    the 120-min workflow timeout (previously the tail was starved).
    #  - Known companies rotate day to day so no single group monopolises the
    #    front and starves the rest.
    first_run_cos = [c for c in companies if c["id"] not in companies_with_jobs]
    known_cos     = [c for c in companies if c["id"] in companies_with_jobs]
    random.shuffle(first_run_cos)   # fair order among new companies too
    random.shuffle(known_cos)
    companies = first_run_cos + known_cos
    log.info(f"Order: {len(first_run_cos)} first-run companies queued first, then {len(known_cos)} known (shuffled)")

    if MAX_COMPANIES:
        companies = companies[:MAX_COMPANIES]
        log.info(f"MAX_COMPANIES={MAX_COMPANIES} — processing only the first {len(companies)}")

    total_fetched = total_kept = total_scored = total_errors = 0
    all_scores: list[int] = []
    companies_with_matches: list[str] = []

    for co in companies:
        co_id, co_name, ats_type, ats_slug = (
            co["id"], co["name"], co["ats_type"], co["ats_slug"]
        )

        fetcher = ATS_FETCHERS.get(ats_type)
        if not fetcher:
            log.warning(f"{co_name}: no fetcher for {ats_type} — skipping")
            total_errors += 1
            continue

        # First-time companies seed a 30-day back-catalog; companies already in
        # the DB get the tight ~24h incremental window.
        is_first_run = co_id not in companies_with_jobs
        active_cutoff = first_run_cutoff if is_first_run else cutoff

        postings = fetcher(ats_slug)
        total_fetched += len(postings)

        relevant = [
            p for p in postings
            if p.get("ats_job_id") and p.get("title")
            and should_keep(p["title"], p.get("location", ""), p.get("posted_at"), active_cutoff)
        ]
        total_kept += len(relevant)

        tag = " [FIRST RUN]" if is_first_run else ""
        log.info(f"{co_name}{tag}: {len(postings)} fetched -> {len(relevant)} kept")

        # Track all fetched job IDs for closed-detection regardless
        for p in postings:
            if p.get("ats_job_id"):
                seen_this_run.add((co_id, p["ats_job_id"]))

        if not relevant:
            time.sleep(0.5)
            continue

        # Dry run stops here: show exactly what a real run would have scored,
        # then move on without hydrating JDs, calling Claude, or writing to the DB.
        if DRY_RUN:
            for p in relevant:
                log.info(f"    WOULD SCORE: {p['title']}  |  {p.get('location', '')}")
            time.sleep(0.3)
            continue

        # Hydrate the full JD for every kept role that doesn't already have one.
        # Ashby and Lever include the JD in their list response; Greenhouse and
        # Workday need a per-posting call. A real JD is what lets the scorer catch
        # experience requirements ("7+ years") instead of guessing from the title.
        for p in relevant:
            if p.get("raw_jd"):
                continue
            if ats_type == "greenhouse":
                p["raw_jd"] = fetch_greenhouse_jd(p["ats_job_id"], ats_slug)
                time.sleep(0.2)
            elif ats_type == "workday":
                p["raw_jd"] = fetch_workday_jd(ats_slug, p.get("_ext_path", ""))
                time.sleep(0.2)

        now = datetime.now(timezone.utc).isoformat()

        sb_upsert("jobs", [
            {
                "company_id":   co_id,
                "ats_job_id":   p["ats_job_id"],
                "title":        p["title"],
                "location":     p.get("location", ""),
                "url":          p["url"],
                "posted_at":    p.get("posted_at"),
                "last_seen_at": now,
                "status":       "open",
                "raw_jd":       (p.get("raw_jd") or "")[:10000],
            }
            for p in relevant
        ], "company_id,ats_job_id")

        # Score jobs that don't have a match yet
        co_jobs = sb_get("jobs", {
            "company_id": f"eq.{co_id}",
            "status":     "eq.open",
            "select":     "id,title,location,raw_jd",
        })
        if not co_jobs:
            time.sleep(0.5)
            continue

        job_ids_csv = ",".join(j["id"] for j in co_jobs)
        matched_ids = {
            m["job_id"]
            for m in sb_get("matches", {
                "job_id": f"in.({job_ids_csv})",
                "select": "job_id",
            })
        }

        to_score = [j for j in co_jobs if j["id"] not in matched_ids]

        match_rows = []
        co_match_count = 0
        for job in to_score:
            family = classify_role(job["title"])
            result = score_job(job["title"], job.get("location", ""), job.get("raw_jd", ""), family)
            if result and isinstance(result.get("score"), int):
                all_scores.append(result["score"])
                # Always persist the score, even sub-threshold. Otherwise `to_score`
                # (jobs without a match row) re-scores every reject every day
                # forever — the single biggest cost leak observed in production
                # (~40% of daily Haiku calls were zombie re-scores).
                # v_watchlist filters by score >= SCORE_THRESHOLD so the board
                # still only shows matches.
                match_rows.append({
                    "job_id":       job["id"],
                    "score":        result["score"],
                    "role_fit":     result.get("role_fit"),
                    "level_fit":    result.get("level_fit"),
                    "location_fit": result.get("location_fit"),
                    "reasoning":    result.get("reasoning", ""),
                    "scored_at":    now,
                })
                if result["score"] >= SCORE_THRESHOLD:
                    total_scored += 1
                    co_match_count += 1
                    log.info(f"    {result['score']}: {job['title']}")
            time.sleep(0.5)

        if to_score:
            log.info(f"  scored {len(to_score)} -> {co_match_count} matched (>= {SCORE_THRESHOLD})")

        if match_rows:
            sb_upsert("matches", match_rows, "job_id")
            companies_with_matches.append(co_name)

        time.sleep(1)

    # Mark jobs that disappeared from ATS as closed. Skipped on a dry run —
    # and it would be wrong there anyway, since MAX_COMPANIES/early-continue
    # means seen_this_run is only a partial view of what's actually open.
    closed_count = 0
    if not DRY_RUN and not MAX_COMPANIES:
        for (co_id, ats_job_id), job_id in existing_map.items():
            if (co_id, ats_job_id) not in seen_this_run:
                sb_patch("jobs", {"id": job_id}, {"status": "closed"})
                closed_count += 1

    score_summary = f"avg_score={sum(all_scores)/len(all_scores):.0f}" if all_scores else "no jobs scored"
    log.info(
        f"=== Done. companies={len(companies)} fetched={total_fetched} kept={total_kept} "
        f"scored={total_scored} closed={closed_count} errors={total_errors} "
        f"haiku_calls={SCORE_STATS['stage1']} sonnet_calls={SCORE_STATS['stage2']} ({score_summary}) ==="
    )
    # Per-model cache diagnostics: read/write/uncached tokens, plus hit-rate.
    # A cache-hit-rate of 0 with nonzero writes = prefix is below the model's
    # minimum cacheable size and caching is silently off (see SCORE_STATS docstring).
    for m_name in sorted(set(SCORE_STATS["input_tokens"]) | set(SCORE_STATS["cache_reads"]) | set(SCORE_STATS["cache_writes"])):
        rd = SCORE_STATS["cache_reads"].get(m_name, 0)
        wr = SCORE_STATS["cache_writes"].get(m_name, 0)
        uc = SCORE_STATS["input_tokens"].get(m_name, 0)
        denom = rd + uc
        hit_pct = (100.0 * rd / denom) if denom else 0.0
        log.info(f"    cache[{m_name}]: read={rd} written={wr} uncached_input={uc} hit_rate={hit_pct:.1f}%")
    if companies_with_matches:
        log.info(f"New matches from: {', '.join(companies_with_matches)}")
    if DRY_RUN:
        log.info(
            f"*** DRY RUN complete — {total_kept} posting(s) passed the filters and "
            f"would be scored on a real run. $0 spent, nothing written. ***"
        )


# ── Utilities ──────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


if __name__ == "__main__":
    main()
