#!/usr/bin/env python3
"""
fetch_and_score.py
------------------
Pulls open jobs from each ATS, filters by PM title + US location + recency,
scores only relevant ones via Claude Haiku, upserts into Supabase.

Env vars (GitHub Actions secrets):
  SUPABASE_URL          https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  service_role key
  ANTHROPIC_API_KEY     Claude API key

Optional:
  SCORE_THRESHOLD       Min score to store a match (default: 65)
"""

import os, json, time, logging, re
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("watchlist")

# ── Config ─────────────────────────────────────────────────────────────────────

SUPABASE_URL         = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
ANTHROPIC_API_KEY    = os.environ["ANTHROPIC_API_KEY"]
SCORE_THRESHOLD      = int(os.getenv("SCORE_THRESHOLD", "65"))

HEADERS_SB = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

CUTOFF_HOURS = 26  # slightly over 24h to avoid missing jobs near the boundary

# ── Candidate profile ──────────────────────────────────────────────────────────
# Lives in profile/candidate_profile.md so it can be edited without touching code.

_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "profile", "candidate_profile.md")
with open(_PROFILE_PATH) as _f:
    CANDIDATE_PROFILE = _f.read()

# ── Filters ────────────────────────────────────────────────────────────────────

PM_KEYWORDS = [
    "product manager",
    "product management",
    "senior product manager",
    "senior pm",
    "technical product manager",
    "ai product manager",
    "product lead",
    "pm ii",
    "pm 2",
    "pm iii",
    "pm 3",
    "product owner",         # some startups use this for PM roles
    "product strategist",
]

EXCLUDE_KEYWORDS = [
    # seniority
    "director", "vp ", "vice president", "head of product", "chief product",
    "principal pm", "group product manager", "distinguished",
    # too junior
    "intern", "apprentice", "associate product manager", "apm ",
    # wrong function
    "marketing", "designer", "engineer", "scientist", "analyst",
    "counsel", "recruiter", "coordinator", "copywriter",
    "account executive", "account manager", "sales",
    "support", "customer success",
    # program/project (not product)
    "program manager", "project manager", "scrum master",
    "operations manager", "supply chain",
]

TARGET_LOCATIONS = [
    # tier 1 — strong preference
    "san francisco", "bay area", "san jose", "mountain view", "palo alto",
    "menlo park", "sunnyvale", "redwood city", "south san francisco",
    "los angeles", "culver city", "santa monica", "venice", "san diego",
    "remote", "hybrid",
    # tier 2 — open to
    "seattle", "new york", "nyc", "boston", "austin", "chicago",
    # catch-alls
    "united states", "usa", ", ca", ", wa", ", ny", ", tx", ", ma",
]

def is_pm_role(title: str) -> bool:
    t = title.lower()
    if not any(k in t for k in PM_KEYWORDS):
        return False
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return False
    return True


def is_target_location(location: str) -> bool:
    if not location or location.strip() == "":
        return True
    return any(k in location.lower() for k in TARGET_LOCATIONS)


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
    if not is_pm_role(title):
        return False
    if not is_target_location(location):
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


def fetch_ashby(slug: str) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        return [
            {
                "ats_job_id": j.get("id", ""),
                "title":      j.get("title", ""),
                "location":   j.get("locationName", ""),
                "url":        j.get("jobUrl", ""),
                "posted_at":  j.get("publishedAt"),
                "raw_jd":     _strip_html(j.get("descriptionHtml", "")),
            }
            for j in r.json().get("jobPostings", [])
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
                "raw_jd":     "",
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
    company (5 pages) — plenty to find PM roles without hammering a tenant
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
                })
            offset += limit
            if offset >= data.get("total", 0):
                break
            time.sleep(0.15)
    except Exception as e:
        log.warning(f"Workday {slug}: {e}")
    return postings


ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "ashby":      fetch_ashby,
    "lever":      fetch_lever,
    "workday":    fetch_workday,
}

# ── Claude Scoring ─────────────────────────────────────────────────────────────

SCORE_SYSTEM = """You are a job-fit evaluator. Output ONLY valid JSON, no markdown, no explanation.
Exactly these fields:
  score        (integer 0-100)
  role_fit     ("strong" | "moderate" | "weak")
  level_fit    ("strong" | "moderate" | "weak")
  location_fit ("strong" | "moderate" | "weak")
  reasoning    (string, max 100 chars, plain English)

Score rubric:
  90-100: excellent fit across role, level, location
  80-89:  strong fit, minor gaps
  70-79:  good but notable gaps
  65-69:  borderline, worth tracking
  <65:    poor fit
"""


def score_job(title: str, location: str, raw_jd: str) -> Optional[dict]:
    prompt = (
        f"CANDIDATE:\n{CANDIDATE_PROFILE}\n\n"
        f"JOB:\nTitle: {title}\nLocation: {location}\n\n"
        f"Description:\n{(raw_jd or '')[:2000]}"
    )
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "system": SCORE_SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"].strip()
        text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        return json.loads(text)
    except Exception as e:
        log.warning(f"Score failed for '{title}': {e}")
        return None


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

    companies = sb_get("companies", {"active": "eq.true", "select": "*"})
    log.info(f"Loaded {len(companies)} active companies")

    # Load existing open jobs for closed-detection
    existing_jobs = sb_get("jobs", {"status": "eq.open", "select": "id,company_id,ats_job_id"})
    existing_map  = {(j["company_id"], j["ats_job_id"]): j["id"] for j in existing_jobs}

    # Build a set of company_ids that already have jobs in the DB
    # These get the 26h recency filter; new companies get all jobs on first run
    companies_with_jobs = {j["company_id"] for j in existing_jobs}

    seen_this_run: set[tuple] = set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)

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

        # First-time companies get no date filter so we seed the DB properly
        is_first_run = co_id not in companies_with_jobs
        active_cutoff = None if is_first_run else cutoff

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

        # Fetch full JD for Greenhouse PM roles only
        if ats_type == "greenhouse":
            for p in relevant:
                p["raw_jd"] = fetch_greenhouse_jd(p["ats_job_id"], ats_slug)
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
            result = score_job(job["title"], job.get("location", ""), job.get("raw_jd", ""))
            if result and isinstance(result.get("score"), int):
                all_scores.append(result["score"])
                if result["score"] >= SCORE_THRESHOLD:
                    match_rows.append({
                        "job_id":       job["id"],
                        "score":        result["score"],
                        "role_fit":     result.get("role_fit"),
                        "level_fit":    result.get("level_fit"),
                        "location_fit": result.get("location_fit"),
                        "reasoning":    result.get("reasoning", ""),
                        "scored_at":    now,
                    })
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

    # Mark jobs that disappeared from ATS as closed
    closed_count = 0
    for (co_id, ats_job_id), job_id in existing_map.items():
        if (co_id, ats_job_id) not in seen_this_run:
            sb_patch("jobs", {"id": job_id}, {"status": "closed"})
            closed_count += 1

    score_summary = f"avg_score={sum(all_scores)/len(all_scores):.0f}" if all_scores else "no jobs scored"
    log.info(
        f"=== Done. companies={len(companies)} fetched={total_fetched} kept={total_kept} "
        f"scored={total_scored} closed={closed_count} errors={total_errors} ({score_summary}) ==="
    )
    if companies_with_matches:
        log.info(f"New matches from: {', '.join(companies_with_matches)}")


# ── Utilities ──────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


if __name__ == "__main__":
    main()
