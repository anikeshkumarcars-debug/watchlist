#!/usr/bin/env python3
"""
fetch_and_score.py
------------------
Pulls open jobs from each ATS, scores them via Claude API,
and upserts results into Supabase.

Supported ATS:
  - Greenhouse (boards-api.greenhouse.io)
  - Ashby     (api.ashbyhq.com)
  - Lever     (api.lever.co)
  - Workday   (careers.{subdomain}.com — HTML scrape, best-effort)

Env vars required (set as GitHub Actions secrets):
  SUPABASE_URL          e.g. https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  service_role key (bypasses RLS for writes)
  ANTHROPIC_API_KEY     Claude API key

Optional:
  SCORE_THRESHOLD       Minimum score to upsert a match (default: 60)
  DRY_RUN               Set to "true" to skip DB writes (log only)
"""

import os, sys, json, time, logging, hashlib, re
from datetime import datetime, timezone
from typing import Optional
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("watchlist")

# ── Config ────────────────────────────────────────────────────────────────────

SUPABASE_URL        = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
SCORE_THRESHOLD     = int(os.getenv("SCORE_THRESHOLD", "60"))
DRY_RUN             = os.getenv("DRY_RUN", "false").lower() == "true"

HEADERS_SB = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}

# ── Candidate profile (edit this to match your resume) ────────────────────────

CANDIDATE_PROFILE = """
Name: Shailvi Kumar
Role target: Senior Product Manager / AI Product Manager
Background:
  - 6 years software engineering + product ownership (CS/engineering undergrad)
  - UCLA Anderson MBA candidate, Class of 2026, Easton Technology Management Fellow
  - AWS Senior TPM intern: Amazon Linux PathFinder (OS upgrade advisor product)
  - GIVE: Product Owner, OKR roadmap, PRD authorship, HDFC Bank ML pipeline
  - Builder: shipped Daybreak (GitHub Actions + Claude API autonomous digest),
    Tailorbot (n8n agentic workflow, JD → resume diff + cover letter),
    Dossier (LinkedIn → pre-meeting brief), Sightline + Tidepool (Lovable prototypes)
Strong suits: AI/ML product, 0→1 builds, technical depth, cross-functional leadership
Location preference: San Francisco Bay Area / Los Angeles / Remote
Seniority: Mid to Senior IC (no VP/Director roles)
"""

# ── ATS Fetchers ──────────────────────────────────────────────────────────────

def fetch_greenhouse(slug: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
        return [
            {
                "ats_job_id": str(j["id"]),
                "title": j.get("title", ""),
                "location": (j.get("location") or {}).get("name", ""),
                "url": j.get("absolute_url", ""),
                "posted_at": j.get("updated_at"),
                "raw_jd": _strip_html(j.get("content", "")),
            }
            for j in jobs
        ]
    except Exception as e:
        log.warning(f"Greenhouse {slug}: {e}")
        return []


def fetch_ashby(slug: str) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        jobs = r.json().get("jobPostings", [])
        return [
            {
                "ats_job_id": j.get("id", ""),
                "title": j.get("title", ""),
                "location": j.get("locationName", ""),
                "url": j.get("jobUrl", ""),
                "posted_at": j.get("publishedAt"),
                "raw_jd": _strip_html(j.get("descriptionHtml", "")),
            }
            for j in jobs
            if not j.get("isListed") == False
        ]
    except Exception as e:
        log.warning(f"Ashby {slug}: {e}")
        return []


def fetch_lever(slug: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        jobs = r.json()
        return [
            {
                "ats_job_id": j.get("id", ""),
                "title": j.get("text", ""),
                "location": (j.get("categories") or {}).get("location", ""),
                "url": j.get("hostedUrl", ""),
                "posted_at": datetime.fromtimestamp(
                    j["createdAt"] / 1000, tz=timezone.utc
                ).isoformat() if j.get("createdAt") else None,
                "raw_jd": _strip_html(
                    " ".join(
                        (l.get("content") or "") + " "
                        + " ".join(b.get("content", []) for b in l.get("lists", []))
                        for l in (j.get("descriptionBody", {}).get("body") or [])
                    )
                ),
            }
            for j in jobs
        ]
    except Exception as e:
        log.warning(f"Lever {slug}: {e}")
        return []


def fetch_workday(slug: str) -> list[dict]:
    """
    Workday has no public API. slug format: 'host_subdomain/tenant/site'
    e.g. 'wd5/garmin/External'
    We use their unofficial jobs API endpoint (used by their own career pages).
    This is best-effort; some tenants block scrapers.
    """
    parts = slug.split("/")
    if len(parts) < 3:
        log.warning(f"Workday slug format invalid: {slug} — expected host/tenant/site")
        return []
    host, tenant, site = parts[0], parts[1], "/".join(parts[2:])
    url = (
        f"https://{tenant}.wd{host.replace('wd','')}.myworkdayjobs.com/wday/cxs/"
        f"{tenant}/{site}/jobs"
    )
    payload = {"limit": 20, "offset": 0, "searchText": "product manager"}
    try:
        r = httpx.post(url, json=payload, timeout=30)
        r.raise_for_status()
        jobs = r.json().get("jobPostings", [])
        return [
            {
                "ats_job_id": j.get("bulletFields", [""])[0] or j.get("title", ""),
                "title": j.get("title", ""),
                "location": j.get("locationsText", ""),
                "url": f"https://{tenant}.wd{host.replace('wd','')}.myworkdayjobs.com/en-US/{site}/job/"
                       + j.get("externalPath", "").lstrip("/"),
                "posted_at": j.get("postedOn"),
                "raw_jd": "",
            }
            for j in jobs
        ]
    except Exception as e:
        log.warning(f"Workday {slug}: {e}")
        return []


ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "ashby":      fetch_ashby,
    "lever":      fetch_lever,
    "workday":    fetch_workday,
}

# ── Claude Scoring ─────────────────────────────────────────────────────────────

SCORE_SYSTEM = """You are a job-fit evaluator. Given a candidate profile and a job posting,
output ONLY valid JSON — no markdown, no commentary, no explanation. 
The JSON must have exactly these fields:
  score        (integer 0-100)
  role_fit     ("strong" | "moderate" | "weak")
  level_fit    ("strong" | "moderate" | "weak")
  location_fit ("strong" | "moderate" | "weak")
  reasoning    (string, max 120 chars, plain English, no em dashes)

Score rubric:
  90-100: excellent fit across role, level, and location
  80-89:  strong fit, minor gaps
  70-79:  good candidate but notable gaps
  60-69:  borderline — worth tracking but not prioritizing
  <60:    poor fit
"""

def score_job(title: str, location: str, raw_jd: str) -> Optional[dict]:
    jd_snippet = (raw_jd or "")[:3000]
    prompt = (
        f"CANDIDATE:\n{CANDIDATE_PROFILE}\n\n"
        f"JOB:\nTitle: {title}\nLocation: {location}\n\nDescription:\n{jd_snippet}"
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
                "max_tokens": 300,
                "system": SCORE_SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        return json.loads(raw)
    except Exception as e:
        log.warning(f"Score failed for '{title}': {e}")
        return None


# ── Supabase helpers ──────────────────────────────────────────────────────────

def sb_get(path: str, params: dict = None) -> list[dict]:
    r = httpx.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=HEADERS_SB, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def sb_upsert(table: str, rows: list[dict], on_conflict: str):
    if DRY_RUN:
        log.info(f"[DRY RUN] would upsert {len(rows)} rows into {table}")
        return
    if not rows:
        return
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**HEADERS_SB, "Prefer": f"resolution=merge-duplicates,return=minimal"},
        params={"on_conflict": on_conflict},
        json=rows,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        log.error(f"Upsert {table} failed: {r.status_code} {r.text[:300]}")
    else:
        log.info(f"  upserted {len(rows)} rows → {table}")


def sb_patch(table: str, filters: dict, data: dict):
    if DRY_RUN:
        return
    params = {k: f"eq.{v}" for k, v in filters.items()}
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=HEADERS_SB,
        params=params,
        json=data,
        timeout=20,
    )
    if r.status_code not in (200, 204):
        log.warning(f"PATCH {table} {filters}: {r.status_code} {r.text[:200]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== Watchlist pipeline starting ===")
    if DRY_RUN:
        log.info("DRY RUN mode — no DB writes")

    # 1. Load active companies from Supabase
    companies = sb_get("companies", {"active": "eq.true", "select": "*"})
    log.info(f"Loaded {len(companies)} active companies")

    # 2. Load existing jobs to detect closed ones
    existing_jobs = sb_get(
        "jobs", {"status": "eq.open", "select": "id,company_id,ats_job_id"}
    )
    existing_map = {(j["company_id"], j["ats_job_id"]): j["id"] for j in existing_jobs}
    seen_this_run: set[tuple] = set()

    total_new, total_scored = 0, 0

    for co in companies:
        co_id    = co["id"]
        co_name  = co["name"]
        ats_type = co["ats_type"]
        ats_slug = co["ats_slug"]

        fetcher = ATS_FETCHERS.get(ats_type)
        if not fetcher:
            log.warning(f"No fetcher for ATS type '{ats_type}' ({co_name})")
            continue

        log.info(f"→ {co_name} ({ats_type}/{ats_slug})")
        postings = fetcher(ats_slug)
        log.info(f"  fetched {len(postings)} postings")

        if not postings:
            continue

        # Upsert jobs
        job_rows = [
            {
                "company_id": co_id,
                "ats_job_id": p["ats_job_id"],
                "title":      p["title"],
                "location":   p.get("location", ""),
                "url":        p["url"],
                "posted_at":  p.get("posted_at"),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "status":     "open",
                "raw_jd":     (p.get("raw_jd") or "")[:10000],
            }
            for p in postings
            if p.get("ats_job_id") and p.get("title")
        ]
        sb_upsert("jobs", job_rows, "company_id,ats_job_id")

        # Track what we saw
        for p in postings:
            seen_this_run.add((co_id, p["ats_job_id"]))

        # Score new jobs that don't have a match yet
        if not DRY_RUN:
            # Reload jobs for this company (need UUIDs)
            co_jobs = sb_get("jobs", {
                "company_id": f"eq.{co_id}",
                "status": "eq.open",
                "select": "id,ats_job_id,title,location,raw_jd",
            })
            # Find which have no match yet
            matched_ids = {
                m["job_id"]
                for m in sb_get("matches", {
                    "job_id": f"in.({','.join(j['id'] for j in co_jobs)})" if co_jobs else "eq.00000000-0000-0000-0000-000000000000",
                    "select": "job_id",
                })
            } if co_jobs else set()

            to_score = [j for j in co_jobs if j["id"] not in matched_ids]
            log.info(f"  {len(to_score)} jobs to score")

            match_rows = []
            for job in to_score:
                result = score_job(job["title"], job.get("location", ""), job.get("raw_jd", ""))
                if result and result.get("score", 0) >= SCORE_THRESHOLD:
                    match_rows.append({
                        "job_id":       job["id"],
                        "score":        result["score"],
                        "role_fit":     result.get("role_fit"),
                        "level_fit":    result.get("level_fit"),
                        "location_fit": result.get("location_fit"),
                        "reasoning":    result.get("reasoning", ""),
                        "scored_at":    datetime.now(timezone.utc).isoformat(),
                    })
                    total_scored += 1
                time.sleep(0.3)  # gentle rate limit

            if match_rows:
                sb_upsert("matches", match_rows, "job_id")
            total_new += len(to_score)

        time.sleep(1)  # be polite between companies

    # 3. Mark jobs as closed if they disappeared from the ATS
    for (co_id, ats_job_id), job_id in existing_map.items():
        if (co_id, ats_job_id) not in seen_this_run:
            log.info(f"  marking closed: {ats_job_id}")
            sb_patch("jobs", {"id": job_id}, {"status": "closed"})

    log.info(
        f"=== Done. {total_new} new jobs encountered, "
        f"{total_scored} scored above threshold ({SCORE_THRESHOLD}) ==="
    )


# ── Utilities ─────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


if __name__ == "__main__":
    main()
