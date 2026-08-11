# Lovable prompt — paste this whole thing in

Build a single-page public job board that reads from my connected Supabase project. This page is linked from my Framer portfolio and resume; visitors should be able to see exactly what I'm tracking. The page is fully read-only — there is no write path and no login.

---

## Connect Supabase

Use my Project URL and anon (public) key. All reads use the anon key. The board is read-only: it only ever runs `select` against the `v_watchlist` view — no writes, no RPCs.

---

## Brand and aesthetic

This is the most important part — get this right.

- **Background**: pure white (#FFFFFF)
- **Primary text**: #0A0A0A
- **Secondary text** (labels, metadata): #6B6B6B
- **Subtle borders / dividers**: #EEEEEE
- **Accent / interactive**: #0066FF (links, hover states)
- **Score colors**:
  - 90+: #0A7F3F (green)
  - 80–89: #0066FF (blue — matches accent)
  - 70–79: #876600 (amber)
  - below 70: #6B6B6B (gray)
- **Font**: Inter (load from Google Fonts if not available natively). Weights: 400, 500, 600. No serifs anywhere.
- **Sentence case everywhere.** Never title case. "where i'm applying", not "Where I'm Applying".
- **Tone**: minimal, designer-quality, Linear / Stripe / Notion aesthetic. Generous whitespace. No emoji, no decorative chrome, no gradients, no shadows except very subtle hover lifts.

---

## Layout — single column, max width 1100px, centered

### Section 1: Header

- Page title: **"where i'm applying"** — 32px, weight 600, color #0A0A0A
- Subtitle below: "a live view of every role i'm tracking. updated daily." — 14px, color #6B6B6B
- Right-aligned on the same line as the subtitle: tiny meta block showing "tracking N companies · last scored M ago" where N is `count(*) from companies where active = true` and M is the relative time since `max(scored_at) from matches`.

40px space below the header.

### Section 2: Filter bar (sticky on scroll)

A single horizontal row containing five filter groups, separated by a thin vertical divider (1px #EEEEEE, 16px tall):

1. **Score**: pill buttons in a row — `all` `90+` `80+` `70+`. Active state: black background, white text. Inactive: white background, #0A0A0A text, #EEEEEE border. Mutually exclusive.

2. **Tier**: pill buttons — `all` `dream` `strong` `explore`. Same styling.

3. **When**: pill buttons — `all time` `new today` `this week`. Same styling.

4. **Search**: small text input, 200px wide, placeholder "search company or role". Filters in real-time.

Default state: all filters set to "all" / first option, search empty. Active filters should also show a small "x" affordance to clear, OR the user can just click the "all" pill. Whichever is cleaner.

The filter bar should stick to the top of the viewport when scrolled past, with a subtle bottom border so it stays visually anchored.

### Section 3: Table of jobs

This is the main content. Query:

```sql
select * from v_watchlist
where job_status = 'open'
order by score desc nulls last, first_seen_at desc
```

Then apply filters client-side.

Columns (left to right):

| Width      | Header     | Content                                                                     |
|------------|------------|-----------------------------------------------------------------------------|
| 64px       | _empty_    | Score badge (rounded rect, white text on score-color background, integer)   |
| flex 2     | role       | Job title (semibold 15px, link styled but neutral color, hover → #0066FF)  |
| flex 1     | company    | Company name + tier tag                                                    |
| 160px      | location   | Location (#6B6B6B 13px)                                                    |
| 90px       | posted     | Relative time ("today", "3d", "1w") — right-aligned, #6B6B6B 12px          |

Header row: small caps, 11px, #6B6B6B, letter-spacing 0.5px. Subtle 1px bottom border.

Body rows:
- 56px tall
- 1px bottom border #F5F5F5 between rows
- Hover state: background #FAFAFA
- Clicking anywhere in the row opens the job URL in a new tab
- Show a small **NEW** pill (8px font, #FFE082 background, #876600 text, padded 2x4px, rounded 3px) next to the job title if `first_seen_at` is within the last 24 hours
- The tier tag next to the company name is a tiny uppercase label, 10px, #6B6B6B, letter-spaced 0.4px — like "DREAM" or "STRONG" or "EXPLORE"

### Section 4: Empty state

If filters produce no rows: centered text "no matches for this filter — try widening." in #6B6B6B 14px, 96px vertical padding.

### Section 5: Footer

After the table, a thin horizontal rule (#EEEEEE) and below it a small line:

"Built by Shay. Code → [github link if you have one, else omit]. See my [portfolio →]" — 12px, #6B6B6B, links in #0066FF.

---

## Behavior details

- The board is **read-only**. No write path, no "mark applied", no login, no password.
- **No drag-and-drop**, no kanban, no application pipeline section. Just the one table.
- All filters are client-side (no Supabase round-trip per filter change). Apply against the initial query result.
- Filters compose with AND — score=80+ AND tier=dream AND search="anthropic" intersects to a smaller list.
- On page load, no flash-of-empty-state — show a subtle skeleton (gray rows) until data arrives.
- "Posted" formatting:
  - <24h → "today"
  - 1–7d → "Nd"
  - 7–28d → "Nw"
  - 28d+ → "Nmo"
- Mobile: stack the filter bar into two rows, drop the location and posted columns into a stacked secondary line under each row's title.

## Out of scope (do NOT build these)

- Any write path, status tracking, or "mark applied" flow
- Kanban / pipeline view
- Company logos
- Drag-and-drop
- Real-time subscriptions
- Authentication / login / passwords
- Bulk actions
