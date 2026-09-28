-- ============================================================================
-- Brighton Weekend v48 — security hardening
-- Run ONCE in the Supabase SQL Editor, after the v37 auth migration.
-- Safe to re-run.
--
-- WHY
-- Every group / commitment function was SECURITY DEFINER, callable by the
-- anonymous role, and trusted the p_user_id argument sent by the browser.
-- Because the publishable key is (necessarily) in index.html, anyone could:
--   * read any user's groups, private PINs and group activity,
--   * mark Interested/Going or join/leave groups as any other user,
--   * read every user's name and plans from event_interest, and
--   * insert, change or DELETE any row in event_interest (open RLS policies).
--
-- WHAT THIS DOES
--   1. Each function now only works for the signed-in caller:
--      p_user_id must equal auth.uid(). Signatures and return types are
--      unchanged, so the app needs no changes to keep working.
--   2. The anonymous role (and PUBLIC) lose EXECUTE on these functions.
--   3. event_interest: users can read only their own rows; all writes go
--      through bw_set_event_interest. Group activity still comes through
--      bw_shared_happenings, which only returns people who share a group.
--   4. bw_custom_events: only signed-in users can add events, created_by
--      must be the caller, ticket links must be http(s), and the venue list
--      matches the venues offered in the app.
--
-- NOT COVERED (their SQL is not in the repository)
--   bw_leave_group, bw_profile_icons_for_user, app_visitors, admin_usage_stats.
--   This file removes anonymous access to the two functions. Please open
--   them in Supabase and add the same check used below:
--       perform public.bw_require_caller(p_user_id);
--
-- AFTER RUNNING: sign in to the app and check that you can mark an event
-- Interested/Going, see Happenings, create/join/leave a group and add an
-- event. Signed-out visitors can still browse events.json listings.
-- ============================================================================

-- Helper: raise unless the argument is the signed-in user's id.
create or replace function public.bw_require_caller(p_user_id text)
returns void
language plpgsql stable
set search_path = public
as $$
begin
  if auth.uid() is null or p_user_id is distinct from auth.uid()::text then
    raise exception 'Not authorised' using errcode = '42501';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Group functions
-- ---------------------------------------------------------------------------
create or replace function public.bw_my_groups(p_user_id text)
returns table(id uuid, name text, is_private boolean, member_count bigint, join_pin text)
language sql security definer set search_path = public
as $$
  select g.id, g.name, g.is_private, count(m2.user_id)::bigint,
    case when g.created_by = p_user_id and g.is_private then g.join_pin else null end
  from bw_groups g
  join bw_group_members m on m.group_id = g.id and m.user_id = p_user_id
  left join bw_group_members m2 on m2.group_id = g.id
  where p_user_id = auth.uid()::text
  group by g.id, g.name, g.is_private, g.join_pin, g.created_by;
$$;

create or replace function public.bw_public_groups(p_user_id text)
returns table(id uuid, name text, member_count bigint)
language sql security definer set search_path = public
as $$
  select g.id, g.name, count(m.user_id)::bigint
  from bw_groups g left join bw_group_members m on m.group_id = g.id
  where g.is_private = false
    and p_user_id = auth.uid()::text
    and not exists (select 1 from bw_group_members mine where mine.group_id = g.id and mine.user_id = p_user_id)
  group by g.id, g.name
  order by lower(g.name);
$$;

create or replace function public.bw_create_group(
  p_user_id text, p_user_name text, p_name text, p_is_private boolean
)
returns table(id uuid, name text, is_private boolean, join_pin text)
language plpgsql security definer set search_path = public
as $$
declare gid uuid; pin text;
begin
  perform public.bw_require_caller(p_user_id);
  if char_length(trim(coalesce(p_name,''))) < 2 then raise exception 'Group name must be at least 2 characters'; end if;
  if exists(select 1 from bw_groups g0 where lower(g0.name) = lower(trim(p_name))) then raise exception 'A group with that name already exists'; end if;
  if p_is_private then
    loop
      pin := lpad((floor(random()*1000))::int::text, 3, '0');
      exit when not exists(select 1 from bw_groups g0 where g0.join_pin = pin and g0.is_private);
    end loop;
  else pin := null; end if;
  insert into bw_groups(name, is_private, join_pin, created_by)
    values (trim(p_name), p_is_private, pin, p_user_id) returning bw_groups.id into gid;
  insert into bw_group_members(group_id, user_id, user_name) values (gid, p_user_id, trim(p_user_name));
  return query select g.id, g.name, g.is_private, g.join_pin from bw_groups g where g.id = gid;
end;
$$;

create or replace function public.bw_join_group(
  p_user_id text, p_user_name text, p_group_id uuid, p_pin text, p_group_name text
)
returns table(ok boolean, message text)
language plpgsql security definer set search_path = public
as $$
declare gid uuid; private_group boolean; stored_pin text;
begin
  perform public.bw_require_caller(p_user_id);
  if p_group_id is not null then
    select g.id, g.is_private, g.join_pin into gid, private_group, stored_pin from bw_groups g where g.id = p_group_id;
  else
    select g.id, g.is_private, g.join_pin into gid, private_group, stored_pin
    from bw_groups g where lower(g.name) = lower(trim(p_group_name)) and g.is_private = true;
  end if;
  if gid is null then return query select false, 'Group not found'; return; end if;
  if private_group and (p_pin is null or p_pin <> stored_pin) then return query select false, 'Incorrect PIN'; return; end if;
  insert into bw_group_members(group_id, user_id, user_name) values (gid, p_user_id, trim(p_user_name))
  on conflict (group_id, user_id) do update set user_name = excluded.user_name;
  return query select true, 'Joined';
end;
$$;

create or replace function public.bw_group_members_for_user(p_user_id text)
returns table(group_id uuid, group_name text, user_id text, user_name text)
language sql security definer set search_path = public
as $$
  select distinct g.id, g.name, m.user_id, m.user_name
  from bw_group_members mine
  join bw_group_members m on m.group_id = mine.group_id
  join bw_groups g on g.id = mine.group_id
  where mine.user_id = p_user_id
    and p_user_id = auth.uid()::text
  order by g.name, m.user_name;
$$;

-- ---------------------------------------------------------------------------
-- 2. Commitments (Interested / Going) and Happenings — from v36, plus caller check
-- ---------------------------------------------------------------------------
create or replace function public.bw_set_event_interest(
  p_user_id text, p_user_name text, p_event_id text, p_status text
)
returns table(event_id text, user_id text, user_name text, status text)
language plpgsql security definer set search_path = public
as $$
begin
  perform public.bw_require_caller(p_user_id);
  if p_event_id is null or btrim(p_event_id) = '' then
    raise exception 'Event ID is required';
  end if;
  if p_status is not null and p_status not in ('not_interested','interested','ticket_bought') then
    raise exception 'Invalid commitment status';
  end if;

  if p_status is null then
    delete from public.event_interest as ei
    where ei.event_id = p_event_id and ei.user_id = p_user_id;
  else
    update public.event_interest as ei
       set user_name = btrim(coalesce(p_user_name,'')), status = p_status
     where ei.event_id = p_event_id and ei.user_id = p_user_id;
    if not found then
      insert into public.event_interest as ei (event_id, user_id, user_name, status)
      values (p_event_id, p_user_id, btrim(coalesce(p_user_name,'')), p_status);
    end if;
  end if;

  return query
  select ei.event_id, ei.user_id, ei.user_name, ei.status
  from public.event_interest as ei
  where ei.event_id = p_event_id and ei.user_id = p_user_id;
end;
$$;

create or replace function public.bw_shared_happenings(p_user_id text)
returns table(group_id uuid, group_name text, event_id text, user_id text, user_name text, status text)
language sql security definer set search_path = public
as $$
  select distinct
    g.id as group_id, g.name as group_name, ei.event_id as event_id,
    ei.user_id as user_id, ei.user_name as user_name, ei.status as status
  from public.bw_group_members as mine
  join public.bw_group_members as member_row on member_row.group_id = mine.group_id
  join public.bw_groups as g on g.id = mine.group_id
  join public.event_interest as ei on ei.user_id = member_row.user_id
  where mine.user_id = p_user_id
    and p_user_id = auth.uid()::text
    and ei.status in ('interested','ticket_bought');
$$;

-- ---------------------------------------------------------------------------
-- 3. Execute permissions: signed-in users only
--    (Postgres grants EXECUTE to PUBLIC by default, so revoke from PUBLIC too.)
-- ---------------------------------------------------------------------------
do $$
declare f record;
begin
  -- Matches every overload by name, so it also covers bw_leave_group and
  -- bw_profile_icons_for_user whatever their exact argument types are.
  for f in
    select p.oid::regprocedure as sig
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname in (
      'bw_require_caller','bw_my_groups','bw_public_groups','bw_create_group','bw_join_group',
      'bw_group_members_for_user','bw_set_event_interest','bw_shared_happenings',
      'bw_leave_group','bw_profile_icons_for_user')
  loop
    execute format('revoke all on function %s from public, anon', f.sig);
    execute format('grant execute on function %s to authenticated', f.sig);
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- 4. event_interest: own rows only; writes only via bw_set_event_interest
-- ---------------------------------------------------------------------------
alter table public.event_interest enable row level security;

do $$
declare p record;
begin
  for p in select policyname from pg_policies where schemaname = 'public' and tablename = 'event_interest' loop
    execute format('drop policy %I on public.event_interest', p.policyname);
  end loop;
end;
$$;

revoke all on public.event_interest from anon, authenticated;
grant select on public.event_interest to authenticated;

create policy "bw_event_interest_select_own"
on public.event_interest for select to authenticated
using (user_id = auth.uid()::text);

create unique index if not exists event_interest_event_user_unique
on public.event_interest(event_id, user_id);

-- ---------------------------------------------------------------------------
-- 5. Community events
-- ---------------------------------------------------------------------------
alter table public.bw_custom_events enable row level security;

-- Replace the old venue whitelist (it rejected most venues the app offers).
do $$
declare c record;
begin
  for c in
    select conname from pg_constraint
    where conrelid = 'public.bw_custom_events'::regclass and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%venue%any%array%'
  loop
    execute format('alter table public.bw_custom_events drop constraint %I', c.conname);
  end loop;
end;
$$;

alter table public.bw_custom_events drop constraint if exists bw_custom_events_venue_allowed;
alter table public.bw_custom_events add constraint bw_custom_events_venue_allowed check (venue in (
  'Brighton Centre','Brighton Dome','CHALK','Concorde 2','The Old Market','Green Door Store',
  'Volks','Quarters','Patterns','DUST','Komedia','The Forge Comedy Club','Theatre Royal Brighton',
  'The Hope & Ruin','The Prince Albert','A L P H A B E T','The Pipeline','Brighton Racecourse',
  'The Gladstone','Babble','Amex Stadium','Shelter Hall','Other'
));

alter table public.bw_custom_events drop constraint if exists bw_custom_events_ticket_url_http;
alter table public.bw_custom_events add constraint bw_custom_events_ticket_url_http
  check (ticket_url is null or ticket_url ~* '^https?://') not valid;  -- existing rows are not re-checked

do $$
declare p record;
begin
  for p in select policyname from pg_policies where schemaname = 'public' and tablename = 'bw_custom_events' loop
    execute format('drop policy %I on public.bw_custom_events', p.policyname);
  end loop;
end;
$$;

revoke all on public.bw_custom_events from anon, authenticated;
grant select on public.bw_custom_events to anon, authenticated;
grant insert on public.bw_custom_events to authenticated;

create policy "bw_custom_events_read"
on public.bw_custom_events for select to anon, authenticated using (true);

create policy "bw_custom_events_insert_own"
on public.bw_custom_events for insert to authenticated
with check (created_by = auth.uid()::text);
