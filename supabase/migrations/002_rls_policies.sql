-- 002_rls_policies.sql
-- Public read for the watchlist; only service_role can write.

alter table companies enable row level security;
alter table jobs enable row level security;
alter table matches enable row level security;
alter table applications enable row level security;

-- ============================================================
-- Public read on everything (the watchlist is a public page)
-- ============================================================
create policy "public read companies"
  on companies for select
  to anon
  using (true);

create policy "public read jobs"
  on jobs for select
  to anon
  using (true);

create policy "public read matches"
  on matches for select
  to anon
  using (true);

create policy "public read applications"
  on applications for select
  to anon
  using (true);

-- ============================================================
-- Writes only via service_role (n8n) or authenticated user (Lovable form)
-- ============================================================
-- n8n uses the service_role key, which bypasses RLS entirely.
-- The Lovable status-update form should use an authenticated session.
-- If you want only YOU to update applications, restrict by user_id.
-- For v1, authenticated users can update applications:

create policy "authenticated can update applications"
  on applications for all
  to authenticated
  using (true)
  with check (true);

-- Companies/jobs/matches: no policy for anon/authenticated writes.
-- Without a policy, writes are blocked unless using service_role.

-- ============================================================
-- Grant view access
-- ============================================================
grant select on v_watchlist to anon, authenticated;
