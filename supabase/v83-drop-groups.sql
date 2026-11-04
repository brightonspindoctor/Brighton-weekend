-- v83: remove groups for good. Run 30 days after v82 (from 4 December 2026),
-- once Crew has been checked. This can't be undone, so take a backup first
-- (BACKUPS.md) if the nightly backup isn't running yet.
--
-- 1. Drops the group functions, bw_groups, bw_group_members and
--    bw_join_attempts (wrong PIN tries).
-- 2. Takes groups out of account deletion and name changes.
-- 3. The hourly clean-up stops clearing PIN tries, and also clears crew
--    lookups after a day and declined crew requests after 6 months.

do $$
begin
  if to_regclass('public.bw_crew') is null then
    raise exception 'Please run v82-crew.sql first.';
  end if;
end $$;

-- 1. Groups
drop function if exists public.bw_create_group(text, text, text, boolean);
drop function if exists public.bw_join_group(text, text, uuid, text, text);
drop function if exists public.bw_leave_group(text, uuid);
drop function if exists public.bw_my_groups(text);
drop function if exists public.bw_public_groups(text);
drop function if exists public.bw_group_members_for_user(text);
drop function if exists public.bw_invite_preview(uuid, text);
drop function if exists public.bw_group_pin_locked(uuid);

-- 2. Account deletion and name changes
create or replace function public.bw_cleanup_deleted_user()
 returns trigger
 language plpgsql
 security definer
 set search_path to 'public'
as $$
declare uid text := old.id::text;
begin
  delete from public.event_interest   where user_id = uid;
  delete from public.bw_custom_events where created_by = uid;
  delete from public.app_visitors     where user_id = uid;
  delete from public.user_roles       where user_id = uid;
  update public.bw_guest_visits set converted_user_id = null where converted_user_id = uid;
  update public.bw_usage_events set user_id = null where user_id = uid;
  update public.bw_reports set reporter_id = null where reporter_id = uid;
  update public.bw_reports set author_id = null, author_name = null where author_id = uid;
  delete from public.bw_profiles      where user_id::text = uid;
  -- bw_crew, bw_crew_requests and bw_crew_lookups go with auth.users (on delete cascade).
  return old;
end;
$$;

create or replace function public.bw_delete_my_account()
 returns table(ok boolean, message text)
 language plpgsql
 security definer
 set search_path to 'public', 'auth'
as $$
declare me uuid := auth.uid(); me_text text;
begin
  if me is null then
    return query select false, 'Not signed in.'; return;
  end if;
  me_text := me::text;
  delete from public.event_interest where event_interest.user_id = me_text;
  delete from public.bw_custom_events where bw_custom_events.created_by = me_text;
  delete from public.app_visitors where user_id::text = me_text;
  delete from public.bw_profiles where user_id::text = me_text;
  delete from auth.users where id = me;  -- bw_cleanup_deleted_user and the crew tables' cascades tidy the rest
  return query select true, 'Your account has been deleted.';
end;
$$;

create or replace function public.bw_profiles_propagate_name()
 returns trigger
 language plpgsql
 security definer
 set search_path to 'public'
as $$
declare nm text := left(btrim(new.display_name), 60);
begin
  if new.display_name is distinct from old.display_name then
    update public.event_interest   set user_name = nm where user_id = new.user_id::text;
    update public.bw_custom_events set created_by_name = nm where created_by = new.user_id::text;
    update public.app_visitors     set display_name = nm where user_id::text = new.user_id::text;
  end if;
  return new;
end;
$$;

-- 3. Hourly clean-up
select cron.unschedule(jobid) from cron.job where jobname = 'bw-hourly-cleanup';
select cron.schedule('bw-hourly-cleanup', '23 * * * *', $job$
  delete from public.bw_crew_lookups  where at < now() - interval '1 day';
  delete from public.bw_crew_requests where declined_at < now() - interval '6 months';
  delete from public.bw_guest_visits  where last_seen_at < now() - interval '13 months';
  delete from public.bw_usage_events  where created_at < now() - interval '13 months';
  delete from public.bw_reports       where created_at < now() - interval '12 months';
$job$);

drop table if exists public.bw_group_members;
drop table if exists public.bw_groups;
drop table if exists public.bw_join_attempts;
