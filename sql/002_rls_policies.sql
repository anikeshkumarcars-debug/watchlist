-- 002_rls_policies.sql
-- No public frontend — this is a private pipeline read via the Supabase
-- dashboard only. RLS is enabled with NO policies, so anon/authenticated
-- (the API-facing roles) are denied by default. The pipeline itself writes
-- with the service_role key, which always bypasses RLS regardless of what's
-- configured here — this file only locks down the anon/PostgREST path.
--
-- Deliberately no policies and no grants: enabling RLS with zero policies is
-- safer than leaving RLS off, since it still blocks anon/authenticated even
-- if a future migration accidentally grants table privileges to those roles.
-- You can always browse data directly in the Supabase Table Editor / SQL
-- Editor — those use your dashboard session, not this RLS path.

alter table companies enable row level security;
alter table jobs enable row level security;
alter table matches enable row level security;
