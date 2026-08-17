-- 004_filter_v_watchlist_by_score.sql
-- View hygiene: hide sub-threshold scores from v_watchlist.
--
-- Context: fetch_and_score.py now stores EVERY score (even <65) as a match row
-- so we don't re-score rejects every day (the biggest cost leak we had). But
-- that means the raw v_watchlist would now surface hundreds of rejects. This
-- filter keeps the view showing only real matches, exactly as before.
--
-- Idempotent: safe to rerun. Run once in the Supabase SQL editor.

drop view if exists v_watchlist;
create view v_watchlist with (security_invoker = on) as
select
  j.id              as job_id,
  c.id              as company_id,
  c.name            as company_name,
  c.tier            as company_tier,
  c.ats_type        as ats_type,
  j.title           as job_title,
  j.location        as location,
  j.url             as job_url,
  j.posted_at       as posted_at,
  j.first_seen_at   as first_seen_at,
  j.status          as job_status,
  m.score           as score,
  m.role_fit        as role_fit,
  m.level_fit       as level_fit,
  m.location_fit    as location_fit,
  m.reasoning       as reasoning,
  m.scored_at       as scored_at
from jobs j
join companies c on c.id = j.company_id
join matches m on m.job_id = j.id       -- inner join: must have a score
where j.status = 'open'
  and m.score >= 65;                     -- match threshold (mirrors SCORE_THRESHOLD default)

-- No grant to anon/authenticated here — this view is queried via the
-- Supabase dashboard (your own session), not the public API. See
-- 002_rls_policies.sql for why anon/authenticated are locked out by default.
