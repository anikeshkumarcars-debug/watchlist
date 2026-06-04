-- 003_apply_rpc.sql
-- Adds the password-gated mark_application() RPC so Lovable can update
-- application status without exposing direct write access via the anon key.
--
-- After running this migration, set your password by running:
--
--   select set_apply_password('your-password-here');
--
-- The password is stored as a bcrypt hash. To rotate it, just call
-- set_apply_password() again with a new value.

create extension if not exists pgcrypto;

-- ============================================================
-- app_settings: simple key/value table for the password hash
-- ============================================================
create table if not exists app_settings (
  id    text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);

alter table app_settings enable row level security;

-- No policies → anon and authenticated cannot read or write this table.
-- Only service_role (n8n) and the SECURITY DEFINER functions below
-- can access it. This matters because the password hash must stay
-- private — anon can call mark_application() but cannot read the hash.

-- ============================================================
-- set_apply_password(text)
--   Hashes and stores the apply password. Run from Supabase SQL Editor
--   (which uses service_role) — not callable by anon.
-- ============================================================
create or replace function set_apply_password(p_password text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_password is null or length(p_password) < 4 then
    raise exception 'password must be at least 4 characters';
  end if;

  insert into app_settings (id, value, updated_at)
  values ('apply_password_hash', crypt(p_password, gen_salt('bf', 10)), now())
  on conflict (id) do update set
    value      = excluded.value,
    updated_at = excluded.updated_at;
end;
$$;

revoke all on function set_apply_password(text) from public, anon, authenticated;
grant execute on function set_apply_password(text) to service_role;

-- ============================================================
-- mark_application(password, job_id, status, notes)
--   Public-callable RPC. Checks password, then upserts the
--   applications row. Returns the resulting row.
-- ============================================================
create or replace function mark_application(
  p_password text,
  p_job_id   uuid,
  p_status   text,
  p_notes    text default null
)
returns applications
language plpgsql
security definer
set search_path = public
as $$
declare
  stored_hash text;
  result      applications;
begin
  -- 1. Verify password
  select value into stored_hash
  from app_settings
  where id = 'apply_password_hash';

  if stored_hash is null then
    raise exception 'apply password not configured — call set_apply_password() first';
  end if;

  if crypt(p_password, stored_hash) <> stored_hash then
    -- Same error for missing/wrong so we don't leak hash existence
    raise exception 'unauthorized' using errcode = '28000';
  end if;

  -- 2. Validate status against the CHECK constraint values
  if p_status not in ('interested', 'applied', 'screen', 'interview', 'offer', 'closed') then
    raise exception 'invalid status: %', p_status;
  end if;

  -- 3. Upsert
  insert into applications (job_id, status, applied_at, notes)
  values (
    p_job_id,
    p_status,
    case when p_status in ('applied', 'screen', 'interview', 'offer') then now() else null end,
    p_notes
  )
  on conflict (job_id) do update set
    status     = excluded.status,
    -- Preserve original applied_at once set, unless status moves backward to interested/closed
    applied_at = case
      when excluded.status in ('applied', 'screen', 'interview', 'offer')
        then coalesce(applications.applied_at, now())
      else applications.applied_at
    end,
    notes      = coalesce(excluded.notes, applications.notes)
  returning * into result;

  return result;
end;
$$;

revoke all on function mark_application(text, uuid, text, text) from public;
grant execute on function mark_application(text, uuid, text, text) to anon, authenticated;

-- ============================================================
-- clear_application(password, job_id)
--   Allows un-tracking a job (delete from applications)
-- ============================================================
create or replace function clear_application(
  p_password text,
  p_job_id   uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  stored_hash text;
begin
  select value into stored_hash from app_settings where id = 'apply_password_hash';
  if stored_hash is null or crypt(p_password, stored_hash) <> stored_hash then
    raise exception 'unauthorized' using errcode = '28000';
  end if;

  delete from applications where job_id = p_job_id;
end;
$$;

revoke all on function clear_application(text, uuid) from public;
grant execute on function clear_application(text, uuid) to anon, authenticated;
