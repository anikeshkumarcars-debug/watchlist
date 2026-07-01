# Watchlist Pipeline

GitHub Actions cron job that fetches open PM roles from ATS APIs, scores them via Claude API, and upserts results into Supabase. The Lovable frontend at [watchlist-product-management.lovable.app](https://watchlist-product-management.lovable.app) reads from Supabase and displays the live board.

**Architecture:**

```
GitHub Actions (7 AM PT daily)
  └─ fetch_and_score.py
       ├─ pulls companies from Supabase
       ├─ fetches postings from Greenhouse / Ashby / Lever / Workday
       ├─ scores each new job via Claude Haiku
       └─ upserts jobs + matches into Supabase
            └─ Lovable reads v_watchlist view → public board

expand_companies.py (run manually, whenever you want to widen the list)
  ├─ reads data/{greenhouse,ashby,lever,workday}.csv (~12.5k companies, bundled locally)
  ├─ skips anything already in Supabase
  ├─ live-checks each remaining company's job board for an open PM role
  │  (no Claude calls — pure HTTP checks, free)
  └─ writes new_companies.sql for anything with a live match today
```

---

## Setup (one time)

### 1. Supabase

Run these SQL files in order in your Supabase SQL Editor:

```
sql/001_initial_schema.sql   — tables + v_watchlist view
sql/002_rls_policies.sql     — public read, no anon writes
sql/003_apply_rpc.sql        — password-gated mark_application() RPC
sql/seed.sql                 — initial company list
```

Then set your apply password (run in Supabase SQL Editor):
```sql
select set_apply_password('your-password-here');
```

### 2. GitHub repo

Create a new private repo (or use this one). Push this folder — including `data/`, it's ~830KB of CSVs and needed for `expand_companies.py`.

### 3. GitHub Secrets

Go to **Settings → Secrets → Actions** and add:

| Secret name           | Where to find it |
|-----------------------|-----------------|
| `SUPABASE_URL`        | Supabase → Project Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY`| Supabase → Project Settings → API → service_role key (not anon) |
| `ANTHROPIC_API_KEY`   | console.anthropic.com → API Keys |

### 4. Trigger a manual run

Go to **Actions → Watchlist — daily job fetch + score → Run workflow**.

Set **dry_run = true** first to validate the fetch without writing to DB. Check the logs. If companies and job counts look right, run again with dry_run = false.

### 5. Verify in Supabase

```sql
-- Check what got populated
select count(*) from jobs;
select count(*) from matches;
select * from v_watchlist order by score desc limit 10;
```

---

## Widening the company list

`scripts/expand_companies.py` reads a bundled local dataset (`data/*.csv`, ~12,500 companies across Greenhouse, Ashby, Lever, and Workday) — no external dependency, no cost, and about 6x the coverage of the old `--limit 2000` default.

This runs automatically, weekly, via **`.github/workflows/expand.yml`** (Mondays, 7 AM PT) — no manual step. It writes new matches straight into Supabase (`tier=explore`, `source=discovered`, `active=true`), so they're picked up by the very next daily `fetch_and_score` run. A company only gets written if it currently has a live posting matching your PM/location filters — nothing gets added on name alone.

Every run still produces `new_companies.sql` as an audit log — visible in the GitHub Actions run summary and attached as a downloadable artifact — purely so you can see what got added and why, or clean up a bad match later with a one-line `update companies set active = false where ...`. It's a paper trail, not a gate.

### Trigger it manually / adjust scope

Go to **Actions → Watchlist — discover new companies → Run workflow** any time you don't want to wait for Monday, or to scan a narrower slice:

- `ats`: which platforms to check (default: all 4)
- `limit`: cap candidates per ATS (default: 0 = full list)
- `tier`: what tier to tag new companies with (default: explore)
- `dry_run`: check this to skip the Supabase write and only produce the audit-log SQL for a one-off manual review

Expect a full 4-ATS scan (~12.5k companies) to take roughly 10-20 minutes — it's a lot of small HTTP requests, not an expensive operation, and it makes zero Claude calls either way.

### Or run it locally

```bash
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_KEY=your-service-role-key
pip install httpx

python scripts/expand_companies.py                      # writes straight to Supabase, all 4 ATS types
python scripts/expand_companies.py --dry-run             # SQL file only, nothing written
python scripts/expand_companies.py --ats workday         # just one ATS type
```

---

## Updating companies

Edit `sql/seed.sql` and re-run it in Supabase SQL Editor. The `ON CONFLICT` clause makes it idempotent — existing rows update, new ones insert. To disable a company without deleting it:

```sql
update companies set active = false where name = 'Acme Corp';
```

To add a new company inline (without editing seed.sql):

```sql
insert into companies (name, ats_type, ats_slug, tier, active, source, notes)
values ('Retool', 'greenhouse', 'retool', 'strong', true, 'manual', null)
on conflict (ats_type, ats_slug) do nothing;
```

### Finding ATS slugs

- **Greenhouse**: visit `boards.greenhouse.io/{slug}` — the slug is in the URL on their careers page
- **Ashby**: visit `jobs.ashbyhq.com/{slug}` — same pattern
- **Lever**: visit `jobs.lever.co/{slug}`
- **Workday**: visit their careers page, look at the URL: `{tenant}.wd{N}.myworkdayjobs.com/{site}` → slug = `wd{N}/{tenant}/{site}`
- Or just check `data/{ats}.csv` — it's a lot faster than hunting on the live site, and it's what `expand_companies.py` uses.

---

## Tuning the scorer

The candidate profile is in `profile/candidate_profile.md`. Update it as your experience changes.

`SCORE_THRESHOLD` (default 65) controls the minimum score stored as a match. Jobs below this are still stored in `jobs` but won't appear in `v_watchlist` (which requires a match row). Raise to 70 to keep the board cleaner; lower to 55 to see more.

The scorer uses **Claude Haiku** (fast, cheap). Daily cost scales with the number of *companies with active postings*, not total companies in the list — inactive/quiet companies cost nothing on a given day. A daily run across ~35 companies with 10-20 new jobs each costs roughly $0.01-0.05 in API tokens; expect that to scale roughly linearly as `expand_companies.py` grows the active list, since only genuinely new postings get scored (existing matches are never re-scored).

---

## Workday

Workday has no public API. The pipeline uses an undocumented JSON endpoint (`/wday/cxs/{tenant}/{site}/jobs`) that powers their own career-page search widget. Some tenants may still block or rate-limit it. Slugs in `data/workday.csv` were parsed directly from each tenant's live careers URL, so they should be accurate — but if a Workday company shows 0 jobs and you know they're hiring, double check the tenant/site against their current careers page; Workday tenants occasionally rename sites.

Not every big employer is on Workday, Greenhouse, Ashby, or Lever — Garmin, for instance, runs on iCIMS, and Hugging Face is on Workable. Both are left `active = false` in `seed.sql` with a note. Adding support for more ATS platforms is a bigger lift (a new fetcher function + parser per platform) and isn't included in this pass — flag it if it becomes worth the effort.

---

## Cron schedule

Runs at 7 AM PT daily (`0 14 * * *` UTC). To change it, edit `.github/workflows/main.yml`. GitHub Actions schedules can drift by up to 15 minutes under load.

---

## File structure

```
.github/
  workflows/
    main.yml             — daily cron: fetch + score (writes to Supabase)
    expand.yml           — weekly cron: company discovery (writes to Supabase)
data/
  greenhouse.csv          — ~4,970 companies
  ashby.csv                — ~2,860 companies
  lever.csv                 — ~2,110 companies
  workday.csv                — ~2,600 companies
scripts/
  fetch_and_score.py   — main daily pipeline
  expand_companies.py  — manual company-list widener
sql/
  001_initial_schema.sql
  002_rls_policies.sql
  003_apply_rpc.sql
  seed.sql
requirements.txt
README.md
```
