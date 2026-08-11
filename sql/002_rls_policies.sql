-- 002_rls_policies.sql
-- Public read for the watchlist board; writes happen only via the
-- service_role key used by the pipeline (which bypasses RLS).

alter table companies enable row level security;
alter table jobs enable row level security;
alter table matches enable row level security;

-- ============================================================
-- Public read on everything (watchlist is a public page)
-- ============================================================
drop policy if exists "public read companies" on companies;
create policy "public read companies"
  on companies for select
  to anon, authenticated
  using (true);

drop policy if exists "public read jobs" on jobs;
create policy "public read jobs"
  on jobs for select
  to anon, authenticated
  using (true);

drop policy if exists "public read matches" on matches;
create policy "public read matches"
  on matches for select
  to anon, authenticated
  using (true);

-- ============================================================
-- NO write policies — writes are blocked for anon/authenticated.
-- The pipeline writes with the service_role key, which bypasses RLS.
-- ============================================================

-- ============================================================
-- Grant view access
-- ============================================================
grant select on v_watchlist to anon, authenticated;
