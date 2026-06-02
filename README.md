# Watchlist

A live, public view of where I'm applying and which roles I'm tracking this week.

## Stack

- **GitHub** — source of truth for company list, prompts, schema, workflow
- **Supabase** — runtime data: jobs, scores, application status
- **n8n** — daily cron that fetches jobs, scores them with Claude, upserts to Supabase
- **Lovable** — public frontend that reads from Supabase
- **Anthropic API** — Claude scores each posting against my profile

## How it works

Once a day, n8n:
1. Reads the active company list from Supabase
2. Hits each company's ATS API (Greenhouse, Lever, Ashby)
3. For every new or changed posting, calls Claude to score role/level/location fit against my master context doc
4. Upserts jobs and matches to Supabase
5. Flips `status` to `closed` for postings that disappeared

Lovable reads from Supabase and renders three sections: companies tracked, open matches above threshold, and the application pipeline grouped by status.

## Repo layout

```
.
├── README.md
├── companies.json              # Source list; also seeded to Supabase
├── supabase/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql
│   │   └── 002_rls_policies.sql
│   └── seed.sql                # Inserts companies.json into Supabase
├── n8n/
│   ├── workflow-greenhouse.json  # Importable workflow (Greenhouse branch only)
│   └── WORKFLOW.md               # Full workflow spec including Lever and Ashby
├── prompts/
│   └── scoring-prompt.md       # Claude API prompt template
└── lovable/
    └── page-spec.md            # Page sections, components, data bindings
```

## Setup order

### 1. Supabase

1. Create a new Supabase project
2. In the SQL editor, run `supabase/migrations/001_initial_schema.sql`
3. Run `supabase/migrations/002_rls_policies.sql`
4. Update `supabase/seed.sql` with your `companies.json` rows, then run it
5. Save the project URL and the `service_role` key (for n8n) and `anon` key (for Lovable)

### 2. n8n

1. Add credentials: Supabase (service_role key), Anthropic API
2. Import `n8n/workflow-greenhouse.json`
3. Verify the credential references resolve
4. Test-run once manually before enabling the daily cron
5. Extend with Lever and Ashby branches per `n8n/WORKFLOW.md`

### 3. Lovable

1. Connect your Supabase project
2. Build the page per `lovable/page-spec.md`
3. For the protected status-update form, gate it behind your Lovable auth (or skip and update via Supabase Studio for v1)

## Adding a company

1. Visit their careers page
2. Identify the ATS:
   - URL contains `boards.greenhouse.io/{slug}` or `job-boards.greenhouse.io/{slug}` → Greenhouse
   - URL contains `jobs.lever.co/{slug}` → Lever
   - URL contains `jobs.ashbyhq.com/{slug}` → Ashby
   - URL contains `*.myworkdayjobs.com` → Workday (v2, not yet supported)
3. Add the entry to `companies.json`
4. Insert the row into Supabase `companies` table (or rerun seed.sql)

## Updating application status

Two options:
- **Supabase Studio** — edit the `applications` row directly. Fine for v1.
- **Lovable form** — add a small auth-gated form that POSTs to Supabase. Recommended once the basics work.

Status values: `interested | applied | screen | interview | offer | closed`

## Cost estimate

- Supabase: free tier covers this easily
- n8n: free if self-hosted, or your existing plan
- Anthropic API: ~200 jobs/day × ~1500 tokens each (with cached system prompt) ≈ under $1/day. Prompt caching cuts this further once the master context doc is cached.

## Open items

- [ ] Verify each company's ATS slug against their actual careers page before going live
- [ ] Decide on match threshold (default 70)
- [ ] Decide if public page redacts anything (currently fully public)
- [ ] Workday support (v2)
- [ ] Realtime updates via Supabase subscriptions (v2)
