-- v80: group PIN guessing, and community genres that vanished early.
--
-- Run v77-reports-and-cleanup.sql first: this file replaces its account clean-up
-- function, and stops with a message if v77 hasn't been run yet.
--
-- 1. Group PINs (security review, 19 October 2026).
--    - Each group now accepts at most 10 wrong PINs in 24 hours, from everyone
--      together. Until now the only limit was 5 wrong tries per account every
--      15 minutes, so a few throwaway accounts could work through a 3-digit
--      PIN in hours. Once a group reaches 10, joining it by PIN (invite links
--      too) is paused until the oldest wrong try is 24 hours old.
--    - New groups get a 6-digit PIN. Existing groups keep their 3-digit PIN, so
--      invite links already sent still work. Both lengths are accepted.
--    - Wrong tries now record the group (when it exists), so they can be
--      counted per group. They are still deleted after 24 hours.
--    - Deleting an account blanks its ID on wrong tries instead of deleting
--      them, so deleting throwaway accounts can't reset a group's count.
-- 2. Community genres: bw_community_genres stopped returning a genre once the
--    date at the start of the event's id had passed. 45 listed events have the
--    day and month swapped in their id (made before the date-reading fix, and
--    kept so people's saved choices stay attached), e.g. Stand Up for Animals on
--    10 Nov has the id 2026-10-11-…, so its genre disappeared a month early. An
--    event's genre is now kept while either reading of its id's date is today
--    or later.
-- Safe to run more than once.

do $$
begin
  if to_regclass('public.bw_reports') is null then
    raise exception 'Please run v77-reports-and-cleanup.sql first, then this file.';
  end if;
end $$;

-- 1a. Wrong tries carry the group, and survive account deletion without an ID.
alter table public.bw_join_attempts add column if not exists group_id uuid;
alter table public.bw_join_attempts alter column user_id drop not null;
create index if not exists bw_join_attempts_group_time
  on public.bw_join_attempts (group_id, attempted_at) where group_id is not null;

-- 1b. 3- or 6-digit PINs.
alter table public.bw_groups drop constraint if exists bw_groups_join_pin_check;
alter table public.bw_groups drop constraint if exists bw_groups_join_pin_format;
alter table public.bw_groups add constraint bw_groups_join_pin_format
  check (join_pin ~ '^[0-9]{3}([0-9]{3})?$');

-- True when a group has had 10 or more wrong PINs in the last 24 hours.
create or replace function public.bw_group_pin_locked(p_group_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select p_group_id is not null and (
    select count(*) from public.bw_join_attempts a
     where a.group_id = p_group_id and a.attempted_at > now() - interval '24 hours') >= 10;
$$;
revoke all on function public.bw_group_pin_locked(uuid) from public, anon, authenticated;

-- 1c. New groups get a 6-digit PIN from a strong random source
--     (gen_random_uuid uses the server's secure random generator; random() doesn't).
create or replace function public.bw_create_group(p_user_id text, p_user_name text, p_name text, p_is_private boolean)
returns table(id uuid, name text, is_private boolean, join_pin text)
language plpgsql security definer set search_path = public as $$
declare gid uuid; pin text;
begin
  perform public.bw_require_caller(p_user_id);
  if char_length(trim(coalesce(p_name,''))) < 2 then raise exception 'Group name must be at least 2 characters'; end if;
  if char_length(trim(p_name)) > 50 then raise exception 'Group names can be up to 50 characters'; end if;
  if (select count(*) from bw_groups g0 where g0.created_by = p_user_id) >= 10 then
    raise exception 'You can create up to 10 groups.';
  end if;
  if exists(select 1 from bw_groups g0 where lower(g0.name) = lower(trim(p_name))) then raise exception 'A group with that name already exists'; end if;
  pin := lpad(((('x' || left(replace(gen_random_uuid()::text, '-', ''), 8))::bit(32)::bigint) % 1000000)::text, 6, '0');
  insert into bw_groups(name, is_private, join_pin, created_by)
    values (trim(p_name), true, pin, p_user_id) returning bw_groups.id into gid;
  insert into bw_group_members(group_id, user_id, user_name) values (gid, p_user_id, public.bw_caller_name(p_user_name));
  return query select g.id, g.name, g.is_private, g.join_pin from bw_groups g where g.id = gid;
end;
$$;
revoke all on function public.bw_create_group(text, text, text, boolean) from public, anon;
grant execute on function public.bw_create_group(text, text, text, boolean) to authenticated;

-- 1d. Joining checks the group's count as well as the person's.
create or replace function public.bw_join_group(p_user_id text, p_user_name text, p_group_id uuid, p_pin text, p_group_name text)
returns table(ok boolean, message text)
language plpgsql security definer set search_path = public as $$
declare
  gid uuid; stored_pin text; members int; nm text;
  max_members constant int := 25;
  max_failures constant int := 5;
begin
  perform public.bw_require_caller(p_user_id);
  nm := public.bw_caller_name(p_user_name);

  if (select count(*) from bw_join_attempts a
       where a.user_id = p_user_id and a.attempted_at > now() - interval '15 minutes') >= max_failures then
    return query select false, 'Too many incorrect attempts. Please wait 15 minutes and try again.'; return;
  end if;

  if p_group_id is not null then
    select g.id, g.join_pin into gid, stored_pin from bw_groups g where g.id = p_group_id;
  else
    select g.id, g.join_pin into gid, stored_pin from bw_groups g where lower(g.name) = lower(trim(coalesce(p_group_name,'')));
  end if;

  -- Paused after 10 wrong PINs for this group in a day, even with the right PIN,
  -- or the pause would tell a guesser when they'd found it.
  if public.bw_group_pin_locked(gid) then
    return query select false, 'This group has had too many incorrect PINs today. Please try again tomorrow.'; return;
  end if;

  -- Same message for "no such group" and "wrong PIN", so names can't be probed.
  if gid is null or p_pin is null or p_pin <> stored_pin then
    insert into bw_join_attempts(user_id, group_id) values (p_user_id, gid);
    return query select false, 'That group name and PIN don''t match.'; return;
  end if;

  if exists(select 1 from bw_group_members m where m.group_id = gid and m.user_id = p_user_id) then
    update bw_group_members set user_name = nm where group_id = gid and user_id = p_user_id;
    return query select true, 'You''re already in this group.'; return;
  end if;

  -- Lock the group row so two people can't both take the 25th place.
  perform 1 from bw_groups g where g.id = gid for update;
  select count(*) into members from bw_group_members m where m.group_id = gid;
  if members >= max_members then
    return query select false, 'This group is full (25 members).'; return;
  end if;

  insert into bw_group_members(group_id, user_id, user_name) values (gid, p_user_id, nm);
  -- Failed attempts are NOT cleared on success: they expire after 24 hours.
  delete from bw_join_attempts where attempted_at < now() - interval '1 day';  -- tidy old rows
  return query select true, 'Joined';
end;
$$;
revoke all on function public.bw_join_group(text, text, uuid, text, text) from public, anon;
grant execute on function public.bw_join_group(text, text, uuid, text, text) to authenticated;

-- 1e. The invite-link preview checks a PIN too, so it gets the same limits.
create or replace function public.bw_invite_preview(p_group_id uuid, p_pin text)
returns table(name text, member_count integer)
language plpgsql security definer set search_path = public as $$
declare uid text := auth.uid()::text; gname text; stored_pin text;
begin
  if uid is null then raise exception 'Not authorised' using errcode = '42501'; end if;
  if (select count(*) from bw_join_attempts a
       where a.user_id = uid and a.attempted_at > now() - interval '15 minutes') >= 5 then
    return;
  end if;
  select g.name, g.join_pin into gname, stored_pin from bw_groups g where g.id = p_group_id;
  if public.bw_group_pin_locked(case when gname is null then null else p_group_id end) then
    return;
  end if;
  if gname is null or p_pin is null or p_pin <> stored_pin then
    insert into bw_join_attempts(user_id, group_id) values (uid, case when gname is null then null else p_group_id end);
    return;
  end if;
  return query select gname, (select count(*)::int from bw_group_members m where m.group_id = p_group_id);
end;
$$;
revoke all on function public.bw_invite_preview(uuid, text) from public, anon;
grant execute on function public.bw_invite_preview(uuid, text) to authenticated;

-- 1f. Deleting an account blanks its ID on wrong tries rather than deleting them.
create or replace function public.bw_delete_my_account()
returns table(ok boolean, message text)
language plpgsql security definer set search_path = public, auth as $$
declare me uuid := auth.uid(); me_text text;
begin
  if me is null then
    return query select false, 'Not signed in.'; return;
  end if;
  me_text := me::text;

  delete from public.event_interest where event_interest.user_id = me_text;

  delete from public.bw_group_members where bw_group_members.user_id = me_text;
  delete from public.bw_groups g
   where not exists (select 1 from public.bw_group_members m where m.group_id = g.id);

  delete from public.bw_custom_events where bw_custom_events.created_by = me_text;

  update public.bw_join_attempts set user_id = null where bw_join_attempts.user_id = me_text;
  delete from public.app_visitors where user_id::text = me_text;
  delete from public.bw_profiles where user_id::text = me_text;

  delete from auth.users where id = me;  -- bw_cleanup_deleted_user tidies the rest

  return query select true, 'Your account has been deleted.';
end;
$$;
revoke all on function public.bw_delete_my_account() from public, anon;
grant execute on function public.bw_delete_my_account() to authenticated;

create or replace function public.bw_cleanup_deleted_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare uid text := old.id::text;
begin
  delete from public.event_interest   where user_id = uid;
  delete from public.bw_group_members where user_id = uid;
  delete from public.bw_groups g
   where not exists (select 1 from public.bw_group_members m where m.group_id = g.id);
  delete from public.bw_custom_events where created_by = uid;
  update public.bw_join_attempts set user_id = null where user_id = uid;
  delete from public.app_visitors     where user_id = uid;
  delete from public.user_roles       where user_id = uid;
  update public.bw_guest_visits set converted_user_id = null where converted_user_id = uid;
  update public.bw_usage_events set user_id = null where user_id = uid;
  update public.bw_reports set reporter_id = null where reporter_id = uid;
  update public.bw_reports set author_id = null, author_name = null where author_id = uid;
  delete from public.bw_profiles      where user_id::text = uid;
  return old;
end;
$$;
revoke all on function public.bw_cleanup_deleted_user() from public, anon, authenticated;

-- 2. Community genres: keep an event's genre while either reading of its id's
--    date (year-month-day, or year-day-month when the day is 12 or under) is
--    yesterday or later.
create or replace function public.bw_community_genres()
returns table(event_id text, genre text, my_genre text)
language sql stable security definer set search_path = public as $$
  with since as (
    select to_char((now() at time zone 'Europe/London')::date - 1, 'YYYY-MM-DD') as d
  ), counts as (
    select g.event_id, g.genre, count(*) as n, min(g.created_at) as first_at
    from public.bw_event_genres g, since
    where (g.event_id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}-'
           and (left(g.event_id, 10) >= since.d
                or (substr(g.event_id, 9, 2) <= '12'
                    and left(g.event_id, 4) || '-' || substr(g.event_id, 9, 2) || '-' || substr(g.event_id, 6, 2) >= since.d)))
       or exists (select 1 from public.bw_custom_events c where c.id::text = g.event_id and c.date >= since.d)
    group by g.event_id, g.genre
  ), ranked as (
    select c.event_id, c.genre,
           row_number() over (partition by c.event_id order by c.n desc, c.first_at asc) as rk
    from counts c
  )
  select r.event_id, r.genre,
         (select m.genre from public.bw_event_genres m where m.event_id = r.event_id and m.user_id = auth.uid())
  from ranked r
  where r.rk = 1;
$$;
revoke all on function public.bw_community_genres() from public;
grant execute on function public.bw_community_genres() to anon, authenticated;
