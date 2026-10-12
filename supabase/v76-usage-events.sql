-- v76: count avatar switches and "Get tickets" taps for the admin dashboard.
--
-- bw_usage_events keeps one row per avatar switch or ticket-link tap:
--   avatar_change  written by a trigger on bw_profiles when someone changes an
--                  avatar they already had. The app's automatic first avatar
--                  (null → something) is not counted. detail = 'old>new'.
--   ticket_click   written by bw_track_ticket_click from the app or the
--                  shareable event pages. detail = where the tap happened
--                  ('app', 'festival', 'event_page').
-- Signed-in taps store the user ID; guest taps store the guest's random device
-- ID (v72) if it has one. Deleting an account removes the user ID from its rows
-- (the anonymous count stays). Rows are removed after 13 months.
-- Safe to run more than once.

create table if not exists public.bw_usage_events (
  id          bigserial primary key,
  kind        text not null check (kind in ('avatar_change','ticket_click')),
  user_id     text,
  guest_id    uuid,
  event_id    text,
  detail      text,
  created_at  timestamptz not null default now()
);
alter table public.bw_usage_events enable row level security;
-- No policies: only the functions below (and admin_usage_stats) touch it.
revoke all on table public.bw_usage_events from public, anon, authenticated;
revoke all on sequence public.bw_usage_events_id_seq from public, anon, authenticated;
create index if not exists bw_usage_events_kind_time on public.bw_usage_events(kind, created_at);

-- 1. Avatar switches
create or replace function public.bw_log_avatar_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.profile_icon is not null and new.profile_icon is not null
     and new.profile_icon is distinct from old.profile_icon then
    insert into bw_usage_events(kind, user_id, detail)
    values ('avatar_change', new.user_id::text, left(old.profile_icon || '>' || new.profile_icon, 90));
  end if;
  return new;
end;
$$;
revoke all on function public.bw_log_avatar_change() from public, anon, authenticated;

drop trigger if exists bw_profiles_log_avatar_change on public.bw_profiles;
create trigger bw_profiles_log_avatar_change
  after update of profile_icon on public.bw_profiles
  for each row execute function public.bw_log_avatar_change();

-- 2. Get tickets taps
create or replace function public.bw_track_ticket_click(
  p_event_id text, p_source text default 'app', p_guest_id uuid default null)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare uid text := auth.uid()::text; gid uuid; src text;
begin
  if p_event_id is null or not public.bw_valid_event_id(left(p_event_id, 200)) then return; end if;
  src := case when p_source in ('app','festival','event_page') then p_source else 'app' end;
  gid := case when uid is null then p_guest_id else null end;
  -- Flood guards: 200 taps a day per person/device, 2,000 an hour overall.
  if (select count(*) from bw_usage_events
       where kind = 'ticket_click' and created_at > now() - interval '1 hour') >= 2000 then return; end if;
  if (uid is not null or gid is not null) and (select count(*) from bw_usage_events
       where kind = 'ticket_click' and created_at > now() - interval '1 day'
         and (user_id = uid or guest_id = gid)) >= 200 then return; end if;
  insert into bw_usage_events(kind, user_id, guest_id, event_id, detail)
  values ('ticket_click', uid, gid, left(p_event_id, 200), src);
  delete from bw_usage_events where created_at < now() - interval '13 months';
end;
$$;
revoke all on function public.bw_track_ticket_click(text, text, uuid) from public;
grant execute on function public.bw_track_ticket_click(text, text, uuid) to anon, authenticated;

-- 3. Deleting an account unlinks it from its usage events.
create or replace function public.bw_cleanup_deleted_user()
returns trigger
language plpgsql
security definer
set search_path = public
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
  update public.bw_guest_visits set converted_user_id = null where converted_user_id = uid;
  update public.bw_usage_events set user_id = null where user_id = uid;
  delete from public.bw_profiles      where user_id::text = uid;
  return old;
end;
$$;

-- 4. Admin dashboard: add avatar and ticket figures.
create or replace function public.admin_usage_stats()
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  total_count bigint; recent_count bigint; last_seen timestamptz;
  guests_total bigint; guests_recent bigint; guests_converted bigint;
  av json; tk json;
begin
  if not exists (
    select 1 from public.user_roles ur
    where ur.user_id::text = auth.uid()::text and ur.role = 'admin'
  ) then
    raise exception 'Not authorised';
  end if;

  select count(*) into total_count from public.app_visitors;
  select count(*) into recent_count from public.app_visitors where last_seen_at >= now() - interval '30 days';
  select max(last_seen_at) into last_seen from public.app_visitors;
  select count(*) into guests_total from public.bw_guest_visits;
  select count(*) into guests_recent from public.bw_guest_visits where last_seen_at >= now() - interval '30 days';
  select count(*) into guests_converted from public.bw_guest_visits where converted_at is not null;

  select json_build_object(
    'total',      count(*),
    'people',     count(distinct user_id),
    'recent',     count(*) filter (where created_at >= now() - interval '30 days'),
    'since',      min(created_at),
    'profiles',   (select count(*) from public.bw_profiles),
    'popular',    (select coalesce(json_agg(x), '[]'::json) from (
                     select split_part(detail, '>', 2) as icon, count(*) as n
                     from public.bw_usage_events where kind = 'avatar_change'
                     group by 1 order by 2 desc, 1 limit 5) x)
  ) into av
  from public.bw_usage_events where kind = 'avatar_change';

  select json_build_object(
    'total',        count(*),
    'recent',       count(*) filter (where created_at >= now() - interval '30 days'),
    'recent_people',count(distinct coalesce(user_id, guest_id::text)) filter (where created_at >= now() - interval '30 days'),
    'recent_users', count(*) filter (where created_at >= now() - interval '30 days' and user_id is not null),
    'recent_pages', count(*) filter (where created_at >= now() - interval '30 days' and detail = 'event_page'),
    'since',        min(created_at),
    'top',          (select coalesce(json_agg(x), '[]'::json) from (
                       select event_id, count(*) as n
                       from public.bw_usage_events
                       where kind = 'ticket_click' and created_at >= now() - interval '30 days'
                       group by 1 order by 2 desc, 1 limit 5) x)
  ) into tk
  from public.bw_usage_events where kind = 'ticket_click';

  return json_build_object(
    'total_users', total_count,
    'recent_users', recent_count,
    'last_seen', last_seen,
    'total_guests', guests_total,
    'recent_guests', guests_recent,
    'converted_guests', guests_converted,
    'avatars', av,
    'tickets', tk
  );
end;
$$;
