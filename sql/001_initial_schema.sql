-- 001_initial_schema.sql
-- Watchlist schema: companies, jobs, matches
-- Idempotent: safe to rerun via DROP IF EXISTS guards.
-- If you're starting fresh, run this. If you already have data, skip to 003.

-- ============================================================
-- Companies: the target list
--   ats_slug format by ats_type:
--     greenhouse: 'anthropic'           (boards-api.greenhouse.io/v1/boards/{slug})
--     ashby:      'mistral'             (api.ashbyhq.com/posting-api/job-board/{slug})
--     lever:      'spotify'             (api.lever.co/v0/postings/{slug})
--     workday:    'wd5/garmin/External' (host_subdomain / tenant / site)
-- ============================================================
create table if not exists companies (
  id              uuid primary key default gen_random_uuid(),
  name            text not null,
  ats_type        text not null check (ats_type in ('greenhouse', 'lever', 'ashby', 'workday')),
  ats_slug        text not null,
  tier            text not null check (tier in ('dream', 'strong', 'explore')),
  active          boolean not null default true,
  source          text not null default 'manual' check (source in ('manual', 'discovered')),
  notes           text,
  created_at      timestamptz not null default now(),
  unique (ats_type, ats_slug)
);

create index if not exists idx_companies_active on companies (active) where active = true;

-- ============================================================
-- Jobs: every posting we've ever seen
-- ============================================================
create table if not exists jobs (
  id              uuid primary key default gen_random_uuid(),
  company_id      uuid not null references companies(id) on delete cascade,
  ats_job_id      text not null,
  title           text not null,
  location        text,
  url             text not null,
  posted_at       timestamptz,
  first_seen_at   timestamptz not null default now(),
  last_seen_at    timestamptz not null default now(),
  status          text not null default 'open' check (status in ('open', 'closed')),
  raw_jd          text,
  unique (company_id, ats_job_id)
);

create index if not exists idx_jobs_company on jobs (company_id);
create index if not exists idx_jobs_status on jobs (status);
create index if not exists idx_jobs_last_seen on jobs (last_seen_at desc);
create index if not exists idx_jobs_first_seen on jobs (first_seen_at desc);

-- ============================================================
-- Matches: Claude scoring output, one row per job
-- ============================================================
create table if not exists matches (
  id              uuid primary key default gen_random_uuid(),
  job_id          uuid not null references jobs(id) on delete cascade,
  score           integer not null check (score >= 0 and score <= 100),
  role_fit        text check (role_fit in ('strong', 'moderate', 'weak')),
  level_fit       text check (level_fit in ('strong', 'moderate', 'weak')),
  location_fit    text check (location_fit in ('strong', 'moderate', 'weak')),
  reasoning       text,
  scored_at       timestamptz not null default now(),
  unique (job_id)
);

create index if not exists idx_matches_score on matches (score desc);

-- ============================================================
-- View: open matches above threshold, joined with company info
-- Lovable reads from this for the main watchlist display.
-- security_invoker = on ensures RLS policies are evaluated as the
-- caller (anon), not the view owner (postgres). Without this, anon
-- could see rows that RLS should hide.
-- ============================================================
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
