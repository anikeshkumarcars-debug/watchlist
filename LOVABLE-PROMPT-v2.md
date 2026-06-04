# Lovable prompt — paste this whole thing in

Build a single-page public job board that reads from my connected Supabase project. This page is linked from my Framer portfolio and resume; visitors should be able to see exactly what I'm tracking. The page is read-only for visitors. The one write path is gated behind a password that only I know.

---

## Connect Supabase

Use my Project URL and anon (public) key. All reads use the anon key. Writes happen exclusively through Postgres RPCs `mark_application` and `clear_application`, which check a password server-side.

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

4. **Status**: pill buttons — `all` `untracked` `applied`. Same styling.

5. **Search**: small text input, 200px wide, placeholder "search company or role". Filters in real-time.

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
| 100px      | status     | Status pill (only if status is not "untracked")                            |
| 48px       | _empty_    | Action button (only visible on row hover, see below)                        |

Header row: small caps, 11px, #6B6B6B, letter-spacing 0.5px. Subtle 1px bottom border.

Body rows:
- 56px tall
- 1px bottom border #F5F5F5 between rows
- Hover state: background #FAFAFA
- Clicking anywhere in the row that isn't the action button opens the job URL in a new tab
- Show a small **NEW** pill (8px font, #FFE082 background, #876600 text, padded 2x4px, rounded 3px) next to the job title if `first_seen_at` is within the last 24 hours
- The tier tag next to the company name is a tiny uppercase label, 10px, #6B6B6B, letter-spaced 0.4px — like "DREAM" or "STRONG" or "EXPLORE"
- The status pill (when shown) is small rounded pill: applied = #0066FF bg / white text; screen/interview/offer = #0A7F3F bg / white text; closed = #6B6B6B bg / white text; interested = white bg / #0A0A0A text / #EEEEEE border

### Section 4: Empty state

If filters produce no rows: centered text "no matches for this filter — try widening." in #6B6B6B 14px, 96px vertical padding.

### Section 5: Footer

After the table, a thin horizontal rule (#EEEEEE) and below it a small line:

"Built by Shay. Code → [github link if you have one, else omit]. See my [portfolio →]" — 12px, #6B6B6B, links in #0066FF.

---

## The "mark applied" action — the only write path

Each row has a tiny action button that appears on hover at the far right, 48px wide column. Render it as a small circle button (24px diameter, white background, #EEEEEE border, "···" inside). It exists in the row markup always; it's just invisible until hover.

Clicking opens a small popover menu (anchored to the button, 200px wide, white card, subtle shadow):
- "mark as interested"
- "mark as applied"
- "mark as screen"
- "mark as interview"
- "mark as offer"
- "mark as closed"
- (divider)
- "untrack" (if currently tracked)

Hovering any option highlights it #FAFAFA. Clicking one fires the write flow:

1. If no password is cached this session, show a small modal (centered, 380px wide):
   - Title: "enter password to edit" (15px, semibold)
   - Subtitle: "this is read-only for visitors. the owner can update status here." (12px, #6B6B6B)
   - Password input (focused on open)
   - Checkbox: "remember on this device" — checked by default
   - "Cancel" / "Submit" buttons (Submit is #0A0A0A bg, white text)

2. On submit, call the appropriate RPC:
   - For status changes: `supabase.rpc('mark_application', { p_password, p_job_id: row.job_id, p_status: 'applied', p_notes: null })`
   - For untrack: `supabase.rpc('clear_application', { p_password, p_job_id: row.job_id })`

3. Cache the password in `localStorage` (if "remember" checked) or `sessionStorage` (otherwise), key `watchlist_pwd`.

4. On RPC success: close modal, optimistically update the row, then refetch the view.

5. On RPC failure with "unauthorized" in error message: clear cached password, show modal again with inline error "wrong password — try again" in #C0392B.

For subsequent edits in the same session, the modal is skipped and the action runs directly using the cached password. If that fails (e.g. password was rotated), fall back to modal.

**Important**: visitors who don't know the password should still have a perfectly functional read-only experience. They can hover, see the action button exists, click it, see the modal — and the modal copy explicitly tells them it's read-only for visitors. No confusion.

---

## Behavior details

- **No drag-and-drop**, no kanban, no separate application pipeline section. Just the one table.
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

- Kanban / pipeline view
- Company logos
- Notes editor inline (notes are managed in Supabase Studio)
- Drag-and-drop
- Real-time subscriptions
- Authentication beyond the single password
- Bulk actions
