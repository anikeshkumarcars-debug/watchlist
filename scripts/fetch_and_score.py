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
    # core PM titles
    "product manager",
    "product management",
    "technical product manager",
    "product manager technical",
 
    # AI/ML PM titles
    "ai product manager",
    "ml product manager",
    "product manager ai",
    "product manager ml",
    "product manager generative ai",
    "product manager llm",
 
    # platform / infra / tools variants
    "product manager platform",
    "platform product manager",
    "product manager developer",
    "product manager infrastructure",
    "product manager data",
    "product manager automation",
 
    # level-specific
    "pm ii",
    "pm 2",
    "pm iii",
    "pm 3",
    "product manager ii",
    "product manager iii",
 
    # senior — keep but not the primary filter
    "senior product manager",
    "senior pm",
    "senior technical product manager",
    "sr product manager",
    "sr. product manager",
 
    # alt titles
    "product lead",
    "product owner",
    "product strategist",
]
 
EXCLUDE_KEYWORDS = [
    # --- too senior ---
    "director", "sr director", "senior director",
    "vp ", "vp,", "vice president",
    "head of product", "head of pm",
    "chief product", "cpo",
    "principal pm", "principal product",
    "group product manager", "gpm",
    "distinguished",
    "staff product manager",
 
    # --- too junior ---
    "intern", "internship",
    "apprentice",
    "associate product manager", "apm ",
    "new grad", "entry level", "entry-level",
 
    # --- wrong function ---
    "marketing manager", "product marketing",
    "designer", "design manager",
    "software engineer", "data engineer", "ml engineer",
    "data scientist", "research scientist",
    "data analyst", "business analyst", "financial analyst",
    "legal counsel", "attorney",
    "recruiter", "talent acquisition",
    "coordinator", "copywriter", "content writer",
    "account executive", "account manager",
    "sales manager", "sales representative", "sales engineer",
    "customer support", "customer success",
    "solutions architect", "solutions engineer",
    "technical writer",
 
    # --- program/project (not product) ---
    "program manager", "technical program manager", "tpm",
    "project manager", "project coordinator",
    "scrum master",
    "delivery manager",
    "operations manager", "supply chain",
    "release manager",
 
    # --- hard-skip domains ---
    "gaming", "game designer", "game producer",
    "defense", "clearance required", "security clearance",
    "top secret", "ts/sci",
    "semiconductor", "chip design", "vlsi",
    "medical device", "clinical", "pharmaceutical", "pharma",
    "biotech", "life sciences",
    "manufacturing engineer", "industrial engineer",
    "autonomous vehicle", "self-driving",
    "ad tech", "programmatic", "advertising operations",
    "luxury", "fashion",
 
    # --- methodology gates ---
    "safe certified", "safe certification", "scaled agile",
 
    # --- experience gates ---
    "10+ years", "10 years", "12+ years", "15+ years",
    "8+ years of product",
]
 
TARGET_LOCATIONS = [
    # ---- Tier 1: Strong preference ----
    # SF Bay Area
    "san francisco", "bay area", "sf",
    "san jose", "mountain view", "palo alto",
    "menlo park", "sunnyvale", "redwood city",
    "south san francisco", "cupertino", "santa clara",
    "oakland", "berkeley", "fremont", "san mateo",
    "foster city", "burlingame", "milpitas",
    "pleasanton", "walnut creek", "emeryville",
 
    # LA metro
    "los angeles", "culver city", "santa monica",
    "venice", "playa vista", "el segundo",
    "burbank", "glendale", "pasadena", "west hollywood",
    "marina del rey", "beverly hills", "century city",
    "long beach", "torrance", "irvine",
    "costa mesa", "newport beach",
 
    # San Diego
    "san diego", "la jolla",
 
    # Remote
    "remote", "hybrid", "work from home",
    "remote - us", "fully remote", "us remote",
 
    # ---- Tier 2: Open to ----
    # Seattle
    "seattle", "bellevue", "redmond", "kirkland",
 
    # New York
    "new york", "nyc", "manhattan", "brooklyn",
    "jersey city", "hoboken",
 
    # Boston
    "boston", "cambridge", "somerville",
 
    # Austin
    "austin",
 
    # Chicago
    "chicago",
 
    # Denver
    "denver", "boulder",
 
    # Portland
    "portland",
 
    # DC metro
    "washington dc", "arlington", "bethesda", "reston",
 
    # ---- Tier 3: Would consider ----
    "atlanta", "miami", "dallas", "houston",
    "phoenix", "salt lake city",
    "raleigh", "durham", "charlotte",
    "nashville", "minneapolis", "philadelphia",
 
    # ---- Catch-alls ----
    "united states", "usa",
    ", ca", ", wa", ", ny", ", tx", ", ma",
    ", co", ", or", ", il", ", ga", ", va",
    ", md", ", pa", ", nc", ", mn", ", ut",
    ", az", ", fl", ", tn",
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

── DIMENSION RUBRICS ──

ROLE FIT (what the product/domain is):
  strong:   Product is in a high-growth or candidate-preferred domain: AI/ML,
            LLM applications, developer tools, cloud infrastructure, data platforms,
            workflow automation, internal tools/platforms, AI-native startups,
            applied-AI teams, productivity software at strong tech companies.
            Title is PM, Technical PM, AI PM, or Platform PM.
  moderate: Product is in a viable but non-preferred domain: general B2B SaaS,
            e-commerce, fintech, edtech, healthtech (non-clinical), consumer apps,
            marketplaces, or growth-stage startups without a clear AI angle.
            Still a legitimate PM role the candidate could do well in.
  weak:     Role requires deep domain-specific expertise the candidate does not
            have: healthcare/clinical regulation, semiconductor/chip design,
            supply chain/logistics domain knowledge, legal/compliance specialization,
            actuarial/insurance, real estate, automotive engineering, biotech R&D.
            Or the title is actually EM, designer, analyst, program/project manager,
            or marketing.

LEVEL FIT (seniority match):
  strong:   JD asks for 2-5 years PM/product experience, or uses "mid-level" /
            "IC" language without specifying years. Title has no level modifier
            or says "PM II" / "PM III". Scope is individual-contributor.
  moderate: JD asks for 5-7 years, or title says "Senior" but described scope
            is individual-contributor (no direct reports required). Also moderate
            if YOE is unspecified but responsibilities suggest mid-to-senior scope.
  weak:     JD requires 8+ years product experience, or role requires people
            management, or title is Staff/Principal/Director/VP/Head of.

LOCATION FIT:
  strong:   Major US tech hubs, especially California: San Francisco, Bay Area,
            Mountain View, Palo Alto, San Jose, Los Angeles, Santa Monica,
            San Diego, Seattle, New York, Boston, Austin, Denver, Chicago.
            Also strong: Remote or Hybrid with US eligibility.
  moderate: Other US cities (Phoenix, Atlanta, Miami, Dallas, Raleigh, Nashville,
            Salt Lake City, Portland, Philadelphia, etc.) or top international
            locations (Amsterdam, Netherlands, London, EU with remote flexibility).
  weak:     India, Southeast Asia, Latin America, Middle East, Africa, or any
            location requiring in-country work authorization the candidate does
            not have. Non-remote international roles outside US/EU.

── SCORING FORMULA ──

Start at 75. Adjust based on dimension ratings:

  role_fit:     strong +15  |  moderate +5   |  weak -20
  level_fit:    strong +10  |  moderate +5   |  weak -15
  location_fit: strong +5   |  moderate 0    |  weak -10

Cap at 100, floor at 0.

This means:
  strong/strong/strong = 100 (cap)
  strong/strong/moderate = 100 (cap)
  strong/moderate/strong = 100 (cap)
  moderate/strong/strong = 95
  strong/moderate/moderate = 85
  moderate/moderate/strong = 85
  moderate/moderate/moderate = 85
  strong/weak/strong = 75
  weak on any dimension with no strong to compensate < 65

If the JD is empty, score from title + location only. Note in reasoning
that the JD was unavailable and discount role_fit by one tier.
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
