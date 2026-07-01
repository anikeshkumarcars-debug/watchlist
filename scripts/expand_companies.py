#!/usr/bin/env python3
"""
expand_companies.py
--------------------
Wide-net company discovery. Downloads the full Greenhouse/Ashby/Lever
company lists from the open stapply.ai dataset (~10k companies), skips
anything already in your Supabase `companies` table, then live-checks
each remaining candidate's job board for an actual open PM role (reusing
the same title/location filter as fetch_and_score.py). Only companies
with a real, current PM opening get written out — no guessing by name.

Usage:
  python expand_companies.py                      # all 3 ATS types, 2000/each
  python expand_companies.py --ats greenhouse --limit 4966
  python expand_companies.py --ats ashby lever --limit 1500 --tier explore

Env vars: SUPABASE_URL, SUPABASE_SERVICE_KEY (same as fetch_and_score.py)
Output:   new_companies.sql — review it, then run in the Supabase SQL editor
"""

import argparse, asyncio, csv, io, os, sys
import httpx

# Keep in sync with PM_KEYWORDS / EXCLUDE_KEYWORDS / TARGET_LOCATIONS in fetch_and_score.py
PM_KEYWORDS = ["product manager", "product management", "senior pm", "pm ii",
               "pm i", "pm 2", "pm 1", "product lead", "product builder"]
EXCLUDE_KEYWORDS = ["director", "vp ", "vice president", "head of product", "chief product",
                     "intern", "apprentice", "principal pm", "group product manager",
                     "technical program manager", "program manager", "marketing", "designer",
                     "engineer", "scientist", "analyst", "counsel", "recruiter", "operations",
                     "account executive", "account manager", "sales", "support", "coordinator"]
TARGET_LOCATIONS = ["san francisco", "bay area", "san jose", "mountain view", "palo alto",
                     "menlo park", "sunnyvale", "redwood city", "seattle", "austin", "boston",
                     "new york", "nyc", "los angeles", "irvine", "culver city", "chicago",
                     "remote", "hybrid", "united states", "usa", ", ca", ", wa", ", ny",
                     ", tx", ", ma", ", il", ", or"]

COMPANY_LIST_URLS = {
    "greenhouse": "https://storage.stapply.ai/jobhive/v1/greenhouse/companies.csv",
    "ashby":      "https://storage.stapply.ai/jobhive/v1/ashby/companies.csv",
    "lever":      "https://storage.stapply.ai/jobhive/v1/lever/companies.csv",
}
JOB_API = {
    "greenhouse": lambda slug: f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "ashby":      lambda slug: f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "lever":      lambda slug: f"https://api.lever.co/v0/postings/{slug}?mode=json",
}

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]


def is_pm_role(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in PM_KEYWORDS) and not any(k in t for k in EXCLUDE_KEYWORDS)


def is_target_location(loc: str) -> bool:
    return not loc.strip() or any(k in loc.lower() for k in TARGET_LOCATIONS)


def existing_slugs() -> set[tuple[str, str]]:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/companies",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        params={"select": "ats_type,ats_slug"},
        timeout=20,
    )
    r.raise_for_status()
    return {(c["ats_type"], c["ats_slug"]) for c in r.json()}


def candidates(ats_type: str, limit: int, skip: set) -> list[tuple[str, str]]:
    """Returns [(name, slug), ...] for this ATS, minus ones already in Supabase."""
    resp = httpx.get(COMPANY_LIST_URLS[ats_type], timeout=60)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    out = []
    for row in reader:
        slug = row["slug"]
        if (ats_type, slug) not in skip:
            out.append((row["name"], slug))
    return out[:limit]


async def check_one(client: httpx.AsyncClient, ats_type: str, name: str, slug: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            r = await client.get(JOB_API[ats_type](slug), timeout=15)
            if r.status_code != 200:
                return None
            data = r.json()
            postings = data.get("jobs", []) if ats_type == "greenhouse" else \
                       data.get("jobPostings", []) if ats_type == "ashby" else \
                       (data if isinstance(data, list) else [])
        except Exception:
            return None

        for p in postings:
            title = p.get("title") or p.get("text") or ""
            loc = (p.get("location") or {}).get("name", "") if ats_type == "greenhouse" else \
                  p.get("locationName", "") if ats_type == "ashby" else \
                  (p.get("categories") or {}).get("location", "")
            if is_pm_role(title) and is_target_location(loc):
                return (name, ats_type, slug, title)
        return None


async def scan(ats_type: str, cands: list[tuple[str, str]], concurrency: int):
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        tasks = [check_one(client, ats_type, name, slug, sem) for name, slug in cands]
        results = []
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            r = await coro
            if r:
                results.append(r)
            if i % 200 == 0:
                print(f"  {ats_type}: checked {i}/{len(cands)}, {len(results)} matches so far")
        return results


def esc(s: str) -> str:
    return s.replace("'", "''")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ats", nargs="+", default=["greenhouse", "ashby", "lever"])
    ap.add_argument("--limit", type=int, default=2000, help="candidates to check per ATS")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--tier", default="explore", choices=["dream", "strong", "explore"])
    args = ap.parse_args()

    skip = existing_slugs()
    print(f"{len(skip)} companies already in Supabase — skipping those")

    all_matches = []
    for ats_type in args.ats:
        cands = candidates(ats_type, args.limit, skip)
        print(f"{ats_type}: {len(cands)} new candidates to live-check")
        matches = asyncio.run(scan(ats_type, cands, args.concurrency))
        print(f"{ats_type}: {len(matches)} companies have a live PM match")
        all_matches.extend(matches)

    if not all_matches:
        print("No new matches found.")
        return

    with open("new_companies.sql", "w") as f:
        f.write("-- Auto-discovered via expand_companies.py — review before running.\n")
        f.write("-- Each row had at least one open role matching your PM/location filters at scan time.\n")
        f.write("insert into companies (name, ats_type, ats_slug, tier, active, source, notes) values\n")
        rows = [
            f"  ('{esc(name)}', '{ats_type}', '{esc(slug)}', '{args.tier}', true, 'discovered', "
            f"'auto-discovered: {esc(title[:60])}')"
            for name, ats_type, slug, title in all_matches
        ]
        f.write(",\n".join(rows))
        f.write("\non conflict (ats_type, ats_slug) do nothing;\n")

    print(f"\nWrote {len(all_matches)} candidate companies to new_companies.sql")
    print("Review it, then paste into the Supabase SQL editor.")


if __name__ == "__main__":
    main()
