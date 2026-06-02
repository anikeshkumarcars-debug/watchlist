# Watchlist

A live, public view of where I'm applying and which roles I'm tracking this week.

## Stack

- **GitHub** — source of truth for schema, prompts, workflow, company list
- **Supabase** — runtime data: jobs, scores, application status
- **n8n** — daily cron that fetches jobs, scores them with Claude, upserts to Supabase
- **Lovable** — public frontend that reads from Supabase
- **Google Docs** — master context (resume + historical context) fetched live each run

## How it works

Once daily, n8n:
1. Pulls the latest resume and master context from Google Docs (always fresh, no hardcoding)
2. Reads the active company list from Supabase
3. Hits each company's ATS API
4. For every new posting, calls Claude to score role/level/location fit
5. Upserts jobs and matches into Supabase
6. Closes postings that disappeared

Lovable reads from Supabase and renders three sections: companies tracked, open matches, application pipeline.

## Repo layout

```
.
├── README.md
├── companies.json              # source list
├── supabase/
│   ├── migrations/             # schema + RLS policies
│   └── seed.sql                # inserts companies.json
├── n8n/
│   └── watchlist-workflow.json # importable workflow with Google Docs fetching
├── prompts/
│   └── scoring-prompt.md       # documentation of the prompt (live version is in workflow)
└── lovable/
    └── PROMPT.md               # paste this into Lovable
```

## Setup

### Supabase (done)
SQL files in `supabase/migrations/` ran in the SQL Editor. `seed.sql` populated the companies table.

### n8n
1. Create two credentials (must use these exact names):
   - `Supabase (service_role)` — Host = Project URL, key = service_role secret
   - `Anthropic API` — API key from console.anthropic.com
2. Workflows → Import → `n8n/watchlist-workflow.json`
3. Click each red-flagged node and re-pick the credential from the dropdown
4. Supabase → companies → set `active=false` everywhere except Anthropic for first test
5. Execute Workflow manually, verify rows in jobs and matches
6. Re-activate companies, toggle workflow Active

### Lovable
1. Connect Supabase (Project URL + anon key)
2. Paste contents of `lovable/PROMPT.md`
3. Iterate, publish

## Updating things

- **New company**: add row to companies table in Supabase (or update companies.json and re-run seed.sql)
- **Updated context**: just edit the Google Doc. Next run picks it up automatically.
- **Application status**: edit the applications table in Supabase Studio (form coming later)
- **Status enum**: interested → applied → screen → interview → offer / closed

## Cost

- Supabase: free tier
- n8n: existing plan
- Anthropic API: ~$0.50/day with prompt caching enabled
