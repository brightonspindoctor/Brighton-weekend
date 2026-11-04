-- v82: Crew replaces groups.
--
-- People now add each other one to one, instead of joining groups with a PIN.
--   - Everyone gets a unique @handle (3-20 characters: a-z, 0-9, dot, dash,
--     underscore; starts and ends with a letter or number). Existing profiles
--     get one made from their name (e.g. jonny-4821); new profiles get one the
--     same way when they're created. People can change theirs in Settings.
--   - You send a crew request by typing someone's exact handle. They accept or
--     decline. Looking someone up shows only their name, handle and icon.
--   - A declined request stays on the sender's side as "sent", so they aren't
--     told it was declined and can't keep re-sending it.
--   - If both people request each other, the second request accepts the first.
--   - Lookups and requests are limited to 30 an hour per person.
--   - Everyone who shares a group today is put in each other's crew.
--   - Happenings and avatars (bw_shared_happenings, bw_profile_icons_for_user)
--     now come from your crew. They keep their old signatures; group_id is
--     null and group_name is 'Your crew'.
--   - The group functions stop working (they say groups have been replaced).
--     The group tables are left untouched for 30 days in case the conversion
--     needs redoing; v83-drop-groups.sql removes them.
--
-- Run after v81. Safe to run more than once (the conversion only adds pairs
-- that aren't there yet).

-- ---------------------------------------------------------------------------
-- 1. Handles
-- ---------------------------------------------------------------------------
alter table public.bw_profiles add column if not exists handle text;

-- Makes a free handle from a name: letters and numbers from the name (up to
-- 14), a dash and 4 random digits.
create or replace function public.bw_make_handle(p_name text)
 returns text
 language plpgsql
 volatile security definer
 set search_path to 'public'
as $$
declare base text; h text; tries int := 0;
begin
  base := left(lower(regexp_replace(translate(coalesce(p_name, ''),
    'àáâãäåçèéêëìíîïñòóôõöùúûüýÿÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝ',
    'aaaaaaceeeeiiiinooooouuuuyyAAAAAACEEEEIIIINOOOOOUUUUY'), '[^A-Za-z0-9]+', '', 'g')), 14);
  if char_length(base) < 2 then base := 'crew'; end if;
  loop
    h := base || '-' || lpad((floor(random() * 10000))::int::text, 4, '0');
    exit when not exists (select 1 from public.bw_profiles p where p.handle = h);
    tries := tries + 1;
    if tries > 40 then
      h := base || '-' || substr(md5(random()::text || clock_timestamp()::text), 1, 5);
      exit when not exists (select 1 from public.bw_profiles p where p.handle = h);
    end if;
  end loop;
  return h;
end $$;
revoke all on function public.bw_make_handle(text) from public, anon, authenticated;

-- Handles are stored lower case. A new profile without one gets one; an
-- update that blanks it keeps the old one.
create or replace function public.bw_profiles_handle()
 returns trigger
 language plpgsql
 security definer
 set search_path to 'public'
as $$
begin
  new.handle := nullif(lower(btrim(regexp_replace(coalesce(new.handle, ''), '^@+', ''))), '');
  if new.handle is null then
    if tg_op = 'UPDATE' and old.handle is not null then
      new.handle := old.handle;
    else
      new.handle := public.bw_make_handle(new.display_name);
    end if;
  end if;
  return new;
end $$;
revoke all on function public.bw_profiles_handle() from public, anon, authenticated;

drop trigger if exists bw_profiles_handle on public.bw_profiles;
create trigger bw_profiles_handle before insert or update of handle on public.bw_profiles
  for each row execute function public.bw_profiles_handle();

-- Backfill, one row at a time so each handle sees the ones before it.
do $$
declare r record;
begin
  for r in select user_id, display_name from public.bw_profiles where handle is null order by created_at loop
    update public.bw_profiles set handle = public.bw_make_handle(r.display_name) where user_id = r.user_id;
  end loop;
end $$;

alter table public.bw_profiles alter column handle set not null;
alter table public.bw_profiles drop constraint if exists bw_profiles_handle_format;
alter table public.bw_profiles add constraint bw_profiles_handle_format
  check (handle ~ '^[a-z0-9][a-z0-9._-]{1,18}[a-z0-9]$');
create unique index if not exists bw_profiles_handle_unique on public.bw_profiles (handle);

-- ---------------------------------------------------------------------------
-- 2. Crew and requests (no policies: only the functions below touch them)
-- ---------------------------------------------------------------------------
create table if not exists public.bw_crew (
  user_a uuid not null references auth.users(id) on delete cascade,
  user_b uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_a, user_b),
  constraint bw_crew_ordered check (user_a < user_b)
);
create index if not exists bw_crew_user_b on public.bw_crew (user_b);

create table if not exists public.bw_crew_requests (
  from_user uuid not null references auth.users(id) on delete cascade,
  to_user uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  declined_at timestamptz,
  primary key (from_user, to_user),
  constraint bw_crew_requests_not_self check (from_user <> to_user)
);
create index if not exists bw_crew_requests_to_user on public.bw_crew_requests (to_user);

-- Handle lookups and requests, for the 30-an-hour limit. Rows older than a
-- day are deleted by bw_crew_rate_ok itself.
create table if not exists public.bw_crew_lookups (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  at timestamptz not null default now()
);
create index if not exists bw_crew_lookups_user_at on public.bw_crew_lookups (user_id, at);

alter table public.bw_crew          enable row level security;
alter table public.bw_crew_requests enable row level security;
alter table public.bw_crew_lookups  enable row level security;
revoke all on public.bw_crew, public.bw_crew_requests, public.bw_crew_lookups from public, anon, authenticated;

-- The people in someone's crew.
create or replace function public.bw_crew_ids(p_me uuid)
 returns setof uuid
 language sql
 stable security definer
 set search_path to 'public'
as $$
  select case when c.user_a = p_me then c.user_b else c.user_a end
  from public.bw_crew c where c.user_a = p_me or c.user_b = p_me;
$$;
revoke all on function public.bw_crew_ids(uuid) from public, anon, authenticated;

-- Records a lookup and says whether the caller is still under 30 in the hour.
create or replace function public.bw_crew_rate_ok(p_me uuid)
 returns boolean
 language plpgsql
 security definer
 set search_path to 'public'
as $$
begin
  delete from public.bw_crew_lookups l where l.user_id = p_me and l.at < now() - interval '1 day';
  if (select count(*) from public.bw_crew_lookups l where l.user_id = p_me and l.at > now() - interval '1 hour') >= 30 then
    return false;
  end if;
  insert into public.bw_crew_lookups(user_id) values (p_me);
  return true;
end $$;
revoke all on function public.bw_crew_rate_ok(uuid) from public, anon, authenticated;

create or replace function public.bw_clean_handle(p text)
 returns text
 language sql
 immutable
as $$ select lower(btrim(regexp_replace(btrim(coalesce(p, '')), '^@+', ''))); $$;

-- ---------------------------------------------------------------------------
-- 3. Functions the app calls
-- ---------------------------------------------------------------------------

-- Change your handle.
create or replace function public.bw_set_handle(p_handle text)
 returns table(ok boolean, message text, handle text)
 language plpgsql
 security definer
 set search_path to 'public'
as $$
declare me uuid := auth.uid(); h text := public.bw_clean_handle(p_handle);
begin
  if me is null then return query select false, 'Not signed in.', null::text; return; end if;
  if h !~ '^[a-z0-9][a-z0-9._-]{1,18}[a-z0-9]$' then
    return query select false, 'Handles are 3 to 20 letters or numbers, and can use . - or _ in the middle.', null::text; return;
  end if;
  if exists (select 1 from public.bw_profiles p where p.handle = h and p.user_id <> me) then
    return query select false, 'Someone already has @' || h || '.', null::text; return;
  end if;
  update public.bw_profiles p set handle = h where p.user_id = me;
  if not found then return query select false, 'Profile not found.', null::text; return; end if;
  return query select true, 'Your handle is now @' || h || '.', h;
exception when unique_violation then
  return query select false, 'Someone already has @' || h || '.', null::text;
end $$;
revoke all on function public.bw_set_handle(text) from public, anon;
grant execute on function public.bw_set_handle(text) to authenticated;

-- Look someone up by their exact handle. Shows only name, handle and icon,
-- and how they relate to you: self, crew, sent, received or none.
create or replace function public.bw_find_crew(p_handle text)
 returns table(user_id uuid, display_name text, handle text, profile_icon text, relation text, message text)
 language plpgsql
 security definer
 set search_path to 'public'
as $$
declare me uuid := auth.uid(); h text := public.bw_clean_handle(p_handle); them public.bw_profiles%rowtype;
begin
  if me is null then raise exception 'Not authorised' using errcode = '42501'; end if;
  if not public.bw_crew_rate_ok(me) then
    return query select null::uuid, null::text, null::text, null::text, 'limit', 'Too many lookups. Please try again in an hour.'; return;
  end if;
  select * into them from public.bw_profiles p where p.handle = h;
  if them.user_id is null then
    return query select null::uuid, null::text, null::text, null::text, 'none', 'No one has the handle @' || h || '.'; return;
  end if;
  return query select them.user_id, them.display_name, them.handle, them.profile_icon,
    case
      when them.user_id = me then 'self'
      when them.user_id in (select public.bw_crew_ids(me)) then 'crew'
      when exists (select 1 from public.bw_crew_requests r where r.from_user = me and r.to_user = them.user_id) then 'sent'
      when exists (select 1 from public.bw_crew_requests r where r.from_user = them.user_id and r.to_user = me and r.declined_at is null) then 'received'
      else 'none'
    end, null::text;
end $$;
revoke all on function public.bw_find_crew(text) from public, anon;
grant execute on function public.bw_find_crew(text) to authenticated;

-- Send a crew request by handle. If they've already asked you, you're both
-- in each other's crew straight away.
create or replace function public.bw_crew_request(p_handle text)
 returns table(ok boolean, message text)
 language plpgsql
 security definer
 set search_path to 'public'
as $$
declare me uuid := auth.uid(); h text := public.bw_clean_handle(p_handle); them uuid; nm text;
begin
  if me is null then return query select false, 'Not signed in.'; return; end if;
  if not public.bw_crew_rate_ok(me) then
    return query select false, 'Too many requests. Please try again in an hour.'; return;
  end if;
  select p.user_id, p.display_name into them, nm from public.bw_profiles p where p.handle = h;
  if them is null then return query select false, 'No one has the handle @' || h || '.'; return; end if;
  if them = me then return query select false, 'That''s you.'; return; end if;
  if them in (select public.bw_crew_ids(me)) then
    return query select true, nm || ' is already in your crew.'; return;
  end if;
  if (select count(*) from public.bw_crew_ids(me)) >= 250 then
    return query select false, 'Your crew is full (250 people).'; return;
  end if;
  -- They asked first (and you haven't declined): accept it.
  if exists (select 1 from public.bw_crew_requests r where r.from_user = them and r.to_user = me) then
    delete from public.bw_crew_requests r where (r.from_user = them and r.to_user = me) or (r.from_user = me and r.to_user = them);
    insert into public.bw_crew(user_a, user_b) values (least(me, them), greatest(me, them)) on conflict do nothing;
    return query select true, nm || ' is now in your crew.'; return;
  end if;
  if exists (select 1 from public.bw_crew_requests r where r.from_user = me and r.to_user = them) then
    return query select true, 'You''ve already asked ' || nm || '.'; return;
  end if;
  if (select count(*) from public.bw_crew_requests r where r.from_user = me and r.declined_at is null) >= 50 then
    return query select false, 'You have 50 requests waiting. Cancel some in Settings first.'; return;
  end if;
  insert into public.bw_crew_requests(from_user, to_user) values (me, them);
  return query select true, 'Request sent to ' || nm || '.';
end $$;
revoke all on function public.bw_crew_request(text) from public, anon;
grant execute on function public.bw_crew_request(text) to authenticated;

-- Accept or decline a request someone sent you.
create or replace function public.bw_crew_respond(p_from uuid, p_accept boolean)
 returns table(ok boolean, message text)
 language plpgsql
 security definer
 set search_path to 'public'
as $$
declare me uuid := auth.uid();
begin
  if me is null then return query select false, 'Not signed in.'; return; end if;
  if not exists (select 1 from public.bw_crew_requests r where r.from_user = p_from and r.to_user = me and r.declined_at is null) then
    return query select false, 'That request is no longer there.'; return;
  end if;
  if p_accept then
    if (select count(*) from public.bw_crew_ids(me)) >= 250 then
      return query select false, 'Your crew is full (250 people).'; return;
    end if;
    delete from public.bw_crew_requests r where (r.from_user = p_from and r.to_user = me) or (r.from_user = me and r.to_user = p_from);
    insert into public.bw_crew(user_a, user_b) values (least(me, p_from), greatest(me, p_from)) on conflict do nothing;
    return query select true, 'Added to your crew.';
  else
    update public.bw_crew_requests r set declined_at = now() where r.from_user = p_from and r.to_user = me;
    return query select true, 'Request declined.';
  end if;
end $$;
revoke all on function public.bw_crew_respond(uuid, boolean) from public, anon;
grant execute on function public.bw_crew_respond(uuid, boolean) to authenticated;

-- Cancel a request you sent.
create or replace function public.bw_crew_cancel(p_to uuid)
 returns table(ok boolean, message text)
 language plpgsql
 security definer
 set search_path to 'public'
as $$
declare me uuid := auth.uid();
begin
  if me is null then return query select false, 'Not signed in.'; return; end if;
  delete from public.bw_crew_requests r where r.from_user = me and r.to_user = p_to;
  return query select true, 'Request cancelled.';
end $$;
revoke all on function public.bw_crew_cancel(uuid) from public, anon;
grant execute on function public.bw_crew_cancel(uuid) to authenticated;

-- Remove someone from your crew (they leave yours and you leave theirs).
create or replace function public.bw_crew_remove(p_other uuid)
 returns table(ok boolean, message text)
 language plpgsql
 security definer
 set search_path to 'public'
as $$
declare me uuid := auth.uid();
begin
  if me is null then return query select false, 'Not signed in.'; return; end if;
  delete from public.bw_crew c where c.user_a = least(me, p_other) and c.user_b = greatest(me, p_other);
  return query select true, 'Removed from your crew.';
end $$;
revoke all on function public.bw_crew_remove(uuid) from public, anon;
grant execute on function public.bw_crew_remove(uuid) to authenticated;

-- Your crew and your requests in one list. relation is crew, received or sent
-- (declined requests you received are left out; ones you sent stay as sent).
create or replace function public.bw_my_crew()
 returns table(user_id uuid, display_name text, handle text, profile_icon text, relation text, since timestamptz)
 language sql
 stable security definer
 set search_path to 'public'
as $$
  select p.user_id, p.display_name, p.handle, p.profile_icon, x.relation, x.since
  from (
    select case when c.user_a = auth.uid() then c.user_b else c.user_a end as other, 'crew'::text as relation, c.created_at as since
      from public.bw_crew c where auth.uid() in (c.user_a, c.user_b)
    union all
    select r.from_user, 'received', r.created_at from public.bw_crew_requests r
      where r.to_user = auth.uid() and r.declined_at is null
    union all
    select r.to_user, 'sent', r.created_at from public.bw_crew_requests r
      where r.from_user = auth.uid()
  ) x
  join public.bw_profiles p on p.user_id = x.other
  where auth.uid() is not null
  order by x.relation, lower(p.display_name);
$$;
revoke all on function public.bw_my_crew() from public, anon;
grant execute on function public.bw_my_crew() to authenticated;

-- Happenings: your crew's responses (and your own), same shape as before.
create or replace function public.bw_shared_happenings(p_user_id text)
 returns table(group_id uuid, group_name text, event_id text, user_id text, user_name text, status text)
 language sql
 stable security definer
 set search_path to 'public'
as $$
  select null::uuid, 'Your crew'::text, ei.event_id, ei.user_id, ei.user_name, ei.status
  from public.event_interest ei
  where p_user_id = auth.uid()::text
    and ei.status in ('interested','ticket_bought','not_interested')
    and (ei.user_id = p_user_id
         or ei.user_id in (select x::text from public.bw_crew_ids(auth.uid()) x));
$$;

-- Avatars of your crew (and you).
create or replace function public.bw_profile_icons_for_user(p_user_id text)
 returns table(user_id text, profile_icon text)
 language sql
 stable security definer
 set search_path to 'public'
as $$
  select p.user_id::text, p.profile_icon
  from public.bw_profiles p
  where p_user_id = auth.uid()::text
    and p.profile_icon is not null
    and (p.user_id = auth.uid() or p.user_id in (select public.bw_crew_ids(auth.uid())));
$$;

-- ---------------------------------------------------------------------------
-- 4. Groups are retired. Older copies of the app get a clear message or an
--    empty list. (Dropped with the tables in v83.)
-- ---------------------------------------------------------------------------
create or replace function public.bw_my_groups(p_user_id text)
 returns table(id uuid, name text, is_private boolean, member_count bigint, join_pin text)
 language sql security definer set search_path to 'public'
as $$ select null::uuid, null::text, null::boolean, null::bigint, null::text where false; $$;

create or replace function public.bw_group_members_for_user(p_user_id text)
 returns table(group_id uuid, group_name text, user_id text, user_name text)
 language sql security definer set search_path to 'public'
as $$ select null::uuid, null::text, null::text, null::text where false; $$;

create or replace function public.bw_create_group(p_user_id text, p_user_name text, p_name text, p_is_private boolean)
 returns table(id uuid, name text, is_private boolean, join_pin text)
 language plpgsql security definer set search_path to 'public'
as $$ begin raise exception 'Groups have been replaced by Crew. Please close and reopen the app.'; end $$;

create or replace function public.bw_join_group(p_user_id text, p_user_name text, p_group_id uuid, p_pin text, p_group_name text)
 returns table(ok boolean, message text)
 language sql security definer set search_path to 'public'
as $$ select false, 'Groups have been replaced by Crew. Please close and reopen the app.'::text; $$;

create or replace function public.bw_leave_group(p_user_id text, p_group_id uuid)
 returns table(ok boolean, message text)
 language sql security definer set search_path to 'public'
as $$ select false, 'Groups have been replaced by Crew. Please close and reopen the app.'::text; $$;

create or replace function public.bw_invite_preview(p_group_id uuid, p_pin text)
 returns table(name text, member_count integer)
 language sql security definer set search_path to 'public'
as $$ select null::text, null::integer where false; $$;

-- ---------------------------------------------------------------------------
-- 5. Everyone who shares a group joins each other's crew.
-- ---------------------------------------------------------------------------
insert into public.bw_crew(user_a, user_b)
select distinct least(a.user_id::uuid, b.user_id::uuid), greatest(a.user_id::uuid, b.user_id::uuid)
from public.bw_group_members a
join public.bw_group_members b on b.group_id = a.group_id and a.user_id < b.user_id
where exists (select 1 from auth.users u where u.id = a.user_id::uuid)
  and exists (select 1 from auth.users u where u.id = b.user_id::uuid)
on conflict do nothing;
