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

Create a new private repo (or use this one). Push this folder.

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
- **Workday**: trickier — visit their careers page, look at the URL: `{tenant}.wd{N}.myworkdayjobs.com/en-US/{site}` → slug = `wd{N}/{tenant}/{site}`

---

## Tuning the scorer

The candidate profile is in `scripts/fetch_and_score.py` at the top (`CANDIDATE_PROFILE`). Update it as your experience changes.

`SCORE_THRESHOLD` (default 60) controls the minimum score stored as a match. Jobs below this are still stored in `jobs` but won't appear in `v_watchlist` (which requires a match row). Raise to 70 to keep the board cleaner; lower to 50 to see more.

The scorer uses **Claude Haiku** (fast, cheap). A full daily run across ~35 companies with 10-20 new jobs each costs roughly $0.01-0.05 in API tokens.

---

## Workday note

Workday has no public API. The pipeline uses an undocumented endpoint that powers their own career pages. Some tenants block this. If a Workday company shows 0 jobs and you know they're hiring, check the slug in seed.sql — tenant names and site names vary. The `active = false` flag in seed.sql on Garmin and Google is intentional until slugs are verified.

---

## Cron schedule

Runs at 7 AM PT daily (`0 14 * * *` UTC). To change it, edit `.github/workflows/daily.yml`. GitHub Actions schedules can drift by up to 15 minutes under load.

---

## File structure

```
.github/
  workflows/
    daily.yml           — cron + manual trigger
scripts/
  fetch_and_score.py   — main pipeline
sql/
  001_initial_schema.sql
  002_rls_policies.sql
  003_apply_rpc.sql
  seed.sql
requirements.txt
README.md
```
