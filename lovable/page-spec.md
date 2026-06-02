# Lovable Page Spec — Watchlist

Single page at `/watchlist`. Public read-only.

## Page header

```
Where I'm applying
Last updated: <relative timestamp from max(scored_at) in matches>
```

Subtitle (small, muted): "Live view of the companies I'm tracking and the roles I'm pursuing."

## Section 1: Companies tracked

Visual: horizontal logo grid. Pull `companies` rows where `active = true`. For each company, display the name as a pill (logo optional v2).

Group by `tier`:
- **Dream** (small label) — pills in coral/red tone
- **Strong** — pills in teal tone
- **Explore** — pills in gray tone

Count at the section header: "Tracking 17 companies across 3 tiers"

Supabase query:
```sql
select id, name, tier from companies where active = true order by tier, name;
```

## Section 2: Open matches

Sortable list of jobs with `match.score >= 70` and `job.status = 'open'` and no row in `applications` yet (or `application_status = 'untracked'`).

Each row:
```
[Score badge: 87]  Senior Product Manager, AI Platform
                   Anthropic · San Francisco · 3 days ago
                   <reasoning text, italic, 1 line>
                   [Apply →] [Mark interested]
```

Sort by score desc by default. Filter chips at top: All / Score 90+ / Score 75-89 / Score 70-74.

Supabase view: `v_watchlist` filtered to `application_status = 'untracked'` and `score >= 70`.

```sql
select * from v_watchlist
where application_status = 'untracked'
  and score >= 70
order by score desc;
```

## Section 3: Application pipeline

Kanban-style columns or vertical stacked groups, in this order:
1. **Interested** (yellow)
2. **Applied** (blue)
3. **Screen** (purple)
4. **Interview** (coral)
5. **Offer** (green)
6. **Closed** (gray, collapsed by default)

Each card:
```
Senior Product Manager
Anthropic · 89
Applied 5 days ago
<truncated notes>
```

Query:
```sql
select * from v_watchlist
where application_status != 'untracked'
order by
  case application_status
    when 'offer' then 1
    when 'interview' then 2
    when 'screen' then 3
    when 'applied' then 4
    when 'interested' then 5
    else 6
  end,
  updated_at desc;
```

## Status update form (auth-gated)

Behind your Lovable auth, a small modal triggered by clicking any job row:

```
Status: [dropdown: interested / applied / screen / interview / offer / closed]
Applied date: [date picker, only if status >= applied]
Notes: [textarea]
[Save]
```

On submit, upsert into `applications` keyed by `job_id`. The RLS policy in `002_rls_policies.sql` permits any authenticated user; restrict further if you want only your account.

## Empty states

- No companies active: "Set up your target list to start tracking."
- No matches yet: "First run hasn't completed. Daily updates begin tomorrow morning."
- No applications: "Nothing in flight yet. Open matches above are waiting."

## Visual style notes

Per the broader portfolio aesthetic (Stripe/Notion minimal, white background, bold typography):
- Score badges: filled rounded rect, score number in semibold
- Tier pills: 1px border, no fill, name + small bullet color marker
- Section headers: 24px semibold, 32px top margin between sections
- Job rows: thin bottom border, hover state lifts the row slightly
- Color use: minimal. Score badges and pipeline column headers are the only places color is used to encode meaning.

## Not in v1

- Logos on company pills (use names only)
- Search/full-text filter (sort and tier filter only)
- Realtime updates via Supabase subscriptions (page refresh works fine)
- Public commenting or interaction
- Analytics on page views
