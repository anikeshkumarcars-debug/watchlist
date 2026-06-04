-- 002_rls_policies.sql
-- Public read for watchlist; writes happen only through mark_application() RPC
-- (defined in 003) or via the service_role key (used by n8n).

alter table companies enable row level security;
alter table jobs enable row level security;
alter table matches enable row level security;
alter table applications enable row level security;

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

drop policy if exists "public read applications" on applications;
create policy "public read applications"
  on applications for select
  to anon, authenticated
  using (true);

-- ============================================================
-- NO write policies — writes are blocked for anon/authenticated.
-- n8n writes use the service_role key, which bypasses RLS.
-- The Lovable "mark applied" button writes via mark_application()
-- RPC, defined in 003. The RPC is SECURITY DEFINER and gates
-- writes behind a password check, so the anon role can call it
-- but cannot write to the table directly.
-- ============================================================

-- Drop the legacy "authenticated can update applications" policy
-- if it exists from an earlier setup.
drop policy if exists "authenticated can update applications" on applications;

-- ============================================================
-- Grant view access
-- ============================================================
grant select on v_watchlist to anon, authenticated;
