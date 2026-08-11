-- 003_remove_applications.sql
-- Removes the application-tracking feature (the old "mark applied" flow).
-- Run this once against an existing database that was set up with the earlier
-- schema. Idempotent and safe to rerun. A fresh install from 001 + 002 never
-- creates these objects, so it can skip this file.
--
-- NOTE: the Lovable frontend must also be updated to stop reading the dropped
-- view columns (application_status / applied_at / application_notes) and to
-- remove the apply UI — otherwise the board will error after this runs.

-- Password-gated RPCs and their settings table
drop function if exists mark_application(text, uuid, text, text);
drop function if exists clear_application(text, uuid);
drop function if exists set_apply_password(text);
drop table if exists app_settings;

-- The applications table + its updated_at trigger/function
drop trigger if exists applications_updated_at on applications;
drop function if exists set_updated_at();
drop table if exists applications cascade;

-- Rebuild the watchlist view without the applications join
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
left join matches m on m.job_id = j.id
where j.status = 'open';

grant select on v_watchlist to anon, authenticated;
