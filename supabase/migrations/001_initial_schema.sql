-- 001_initial_schema.sql
-- Watchlist schema: companies, jobs, matches, applications

-- ============================================================
-- Companies: the target list
-- ============================================================
create table companies (
  id              uuid primary key default gen_random_uuid(),
  name            text not null,
  ats_type        text not null check (ats_type in ('greenhouse', 'lever', 'ashby', 'workday')),
  ats_slug        text not null,
  tier            text not null check (tier in ('dream', 'strong', 'explore')),
  active          boolean not null default true,
  notes           text,
  created_at      timestamptz not null default now(),
  unique (ats_type, ats_slug)
);

create index idx_companies_active on companies (active) where active = true;

-- ============================================================
-- Jobs: every posting we've ever seen
-- ============================================================
create table jobs (
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

create index idx_jobs_company on jobs (company_id);
create index idx_jobs_status on jobs (status);
create index idx_jobs_last_seen on jobs (last_seen_at desc);

-- ============================================================
-- Matches: Claude scoring output, one row per job
-- ============================================================
create table matches (
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

create index idx_matches_score on matches (score desc);

-- ============================================================
-- Applications: the watchlist state — manual edits
-- ============================================================
create table applications (
  id              uuid primary key default gen_random_uuid(),
  job_id          uuid not null references jobs(id) on delete cascade,
  status          text not null check (status in ('interested', 'applied', 'screen', 'interview', 'offer', 'closed')),
  applied_at      timestamptz,
  updated_at      timestamptz not null default now(),
  notes           text,
  unique (job_id)
);

create index idx_applications_status on applications (status);

-- ============================================================
-- Auto-update updated_at on applications
-- ============================================================
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger applications_updated_at
  before update on applications
  for each row execute function set_updated_at();

-- ============================================================
-- View: open matches above threshold, joined with company info
-- Lovable reads from this for the main watchlist display
-- ============================================================
create or replace view v_watchlist as
select
  j.id              as job_id,
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
  coalesce(a.status, 'untracked') as application_status,
  a.applied_at      as applied_at,
  a.notes           as application_notes
from jobs j
join companies c on c.id = j.company_id
left join matches m on m.job_id = j.id
left join applications a on a.job_id = j.id
where j.status = 'open';
