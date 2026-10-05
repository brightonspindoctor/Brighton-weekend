-- ============================================================================
-- Brighton Weekend v59 — account clean-up, community-event limits, privacy
-- Run once in the Supabase SQL Editor, after v58. Safe to re-run.
--
--   1. Deleting a user anywhere (in the app OR in the Supabase dashboard)
--      now removes all of their app data. Before, dashboard deletions left
--      their Interested/Going rows behind; the 3 orphaned rows are removed.
--   2. Community events: start/finish times must be HH:MM, status can only be
--      blank or SOLD OUT, the date must be a real date from today up to two
--      years ahead (so past-dated events can't be added without limit).
--   3. Signed-out visitors can no longer read who added a community event
--      (created_by / created_by_name). Signed-in users still see "added by".
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Clean up app data whenever an auth user is deleted
-- ---------------------------------------------------------------------------
create or replace function public.bw_cleanup_deleted_user()
returns trigger
language plpgsql security definer set search_path = public
as $$
declare uid text := old.id::text;
begin
  delete from public.event_interest   where user_id = uid;
  delete from public.bw_group_members where user_id = uid;
  delete from public.bw_groups g
   where not exists (select 1 from public.bw_group_members m where m.group_id = g.id);
  delete from public.bw_custom_events where created_by = uid;
  delete from public.bw_join_attempts where user_id = uid;
  delete from public.app_visitors     where user_id = uid;
  delete from public.user_roles       where user_id = uid;
  delete from public.bw_profiles      where user_id::text = uid;
  return old;
end;
$$;
revoke all on function public.bw_cleanup_deleted_user() from public, anon, authenticated;

drop trigger if exists bw_cleanup_deleted_user on auth.users;
create trigger bw_cleanup_deleted_user
after delete on auth.users
for each row execute function public.bw_cleanup_deleted_user();

-- Data left behind by accounts that were already deleted
delete from public.event_interest e
 where e.user_id is not null and not exists (select 1 from auth.users u where u.id::text = e.user_id);
delete from public.bw_group_members m
 where not exists (select 1 from auth.users u where u.id::text = m.user_id);
delete from public.bw_custom_events c
 where not exists (select 1 from auth.users u where u.id::text = c.created_by);
delete from public.app_visitors a
 where not exists (select 1 from auth.users u where u.id::text = a.user_id);
delete from public.bw_groups g
 where not exists (select 1 from public.bw_group_members m where m.group_id = g.id);

-- ---------------------------------------------------------------------------
-- 2. Community-event field limits
-- ---------------------------------------------------------------------------
alter table public.bw_custom_events drop constraint if exists bw_custom_events_time_format;
alter table public.bw_custom_events add constraint bw_custom_events_time_format
  check (time is null or time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$');
alter table public.bw_custom_events drop constraint if exists bw_custom_events_finish_time_format;
alter table public.bw_custom_events add constraint bw_custom_events_finish_time_format
  check (finish_time is null or finish_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$');
alter table public.bw_custom_events drop constraint if exists bw_custom_events_status_allowed;
alter table public.bw_custom_events add constraint bw_custom_events_status_allowed
  check (status in ('', 'SOLD OUT'));

-- The insert trigger now also checks the date is real and within range.
create or replace function public.bw_custom_events_limit()
returns trigger
language plpgsql security definer set search_path = public
as $$
declare d date; today date := (now() at time zone 'Europe/London')::date;
begin
  begin
    d := to_date(new.date, 'YYYY-MM-DD');
  exception when others then
    raise exception 'Please choose a valid date.';
  end;
  if to_char(d, 'YYYY-MM-DD') <> new.date then
    raise exception 'Please choose a valid date.';
  end if;
  if d < today or d > today + 730 then
    raise exception 'Events can be added from today up to two years ahead.';
  end if;

  if (select count(*) from public.bw_custom_events e
       where e.created_by = new.created_by
         and e.date >= to_char(today, 'YYYY-MM-DD')) >= 20 then
    raise exception 'You''ve added the maximum of 20 upcoming events. Please try again once some have passed.';
  end if;
  new.created_by_name := public.bw_caller_name(new.created_by_name);
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- 3. Signed-out visitors can't see who added an event
-- ---------------------------------------------------------------------------
revoke select on public.bw_custom_events from anon;
grant select (id, title, date, venue, venue_detail, time, finish_time, price, status,
              ticket_url, category, description, created_at)
  on public.bw_custom_events to anon;
