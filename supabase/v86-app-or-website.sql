-- v86: tell the installed app apart from the website.
--
-- One more kind of row in bw_usage_events (v76, v78):
--   web_open  Brighton Weekend was opened as a website in a browser (not from
--             the home screen). At most once a day per person or device, like
--             app_open. detail is the kind of device, as for app_open.
-- The app only sends it when Count my visits is on. Rows are removed after
-- 13 months, and deleting an account removes the user ID from its rows (v76).
--
-- admin_usage_stats() gains 'modes': people or devices that opened the
-- installed app and the website, in the last 30 days and today, and how many
-- used both. Everything else it returns is unchanged from v78.
-- Safe to run more than once.

alter table public.bw_usage_events drop constraint if exists bw_usage_events_kind_check;
alter table public.bw_usage_events add constraint bw_usage_events_kind_check
  check (kind in ('avatar_change', 'ticket_click', 'app_install', 'app_open', 'web_open'));

create or replace function public.bw_track_app(
  p_kind text, p_platform text default null, p_guest_id uuid default null)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  uid text := auth.uid()::text;
  gid uuid;
  plat text;
  today_start timestamptz := (date_trunc('day', now() at time zone 'Europe/London')) at time zone 'Europe/London';
begin
  if p_kind is null or p_kind not in ('app_install', 'app_open', 'web_open') then return; end if;
  plat := case when p_platform in ('ios', 'android', 'desktop') then p_platform else 'other' end;
  gid := case when uid is null then p_guest_id else null end;
  if uid is null and gid is null then return; end if;  -- nothing to count it against
  -- Flood guards: 500 an hour for installs and app opens, 2,000 an hour for
  -- website opens (there are more of them).
  if p_kind = 'web_open' then
    if (select count(*) from bw_usage_events
         where kind = 'web_open' and created_at > now() - interval '1 hour') >= 2000 then return; end if;
  elsif (select count(*) from bw_usage_events
          where kind in ('app_install', 'app_open') and created_at > now() - interval '1 hour') >= 500 then return;
  end if;
  -- An install once per person or device and platform; an open once a day.
  if p_kind = 'app_install' and exists (
       select 1 from bw_usage_events
        where kind = 'app_install' and detail = plat and (user_id = uid or guest_id = gid)) then return; end if;
  if p_kind in ('app_open', 'web_open') and exists (
       select 1 from bw_usage_events
        where kind = p_kind and created_at >= today_start and (user_id = uid or guest_id = gid)) then return; end if;
  insert into bw_usage_events(kind, user_id, guest_id, detail) values (p_kind, uid, gid, plat);
  delete from bw_usage_events where created_at < now() - interval '13 months';
end;
$$;
revoke all on function public.bw_track_app(text, text, uuid) from public;
grant execute on function public.bw_track_app(text, text, uuid) to anon, authenticated;

create or replace function public.admin_usage_stats()
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  total_count bigint; recent_count bigint; last_seen timestamptz;
  guests_total bigint; guests_recent bigint; guests_converted bigint;
  av json; tk json; ins json; md json;
  today_start timestamptz := (date_trunc('day', now() at time zone 'Europe/London')) at time zone 'Europe/London';
begin
  if not exists (
    select 1 from public.user_roles ur
    where ur.user_id::text = (select auth.uid())::text and ur.role = 'admin'
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

  select json_build_object(
    'total',        count(*) filter (where kind = 'app_install'),
    'recent',       count(*) filter (where kind = 'app_install' and created_at >= now() - interval '30 days'),
    'today',        count(*) filter (where kind = 'app_install' and created_at >= today_start),
    'signed_in',    count(*) filter (where kind = 'app_install' and user_id is not null),
    'platforms',    (select coalesce(json_object_agg(detail, n), '{}'::json) from (
                       select detail, count(*) as n from public.bw_usage_events
                       where kind = 'app_install' group by 1) x),
    'open_devices', count(distinct coalesce(user_id, guest_id::text)) filter (where kind = 'app_open' and created_at >= now() - interval '30 days'),
    'open_today',   count(*) filter (where kind = 'app_open' and created_at >= today_start),
    'since',        min(created_at) filter (where kind = 'app_install')
  ) into ins
  from public.bw_usage_events where kind in ('app_install', 'app_open');

  -- App or website (v86). A person or device is their user ID if signed in,
  -- otherwise their guest ID.
  with o as (
    select kind, coalesce(user_id, guest_id::text) as who, created_at
    from public.bw_usage_events
    where kind in ('app_open', 'web_open') and created_at >= now() - interval '30 days'
  )
  select json_build_object(
    'app_30',    count(distinct who) filter (where kind = 'app_open'),
    'web_30',    count(distinct who) filter (where kind = 'web_open'),
    'app_today', count(distinct who) filter (where kind = 'app_open' and created_at >= today_start),
    'web_today', count(distinct who) filter (where kind = 'web_open' and created_at >= today_start),
    'both_30',   (select count(*) from (select who from o group by who having count(distinct kind) = 2) b),
    'web_since', (select min(created_at) from public.bw_usage_events where kind = 'web_open')
  ) into md
  from o;

  return json_build_object(
    'total_users', total_count,
    'recent_users', recent_count,
    'last_seen', last_seen,
    'total_guests', guests_total,
    'recent_guests', guests_recent,
    'converted_guests', guests_converted,
    'avatars', av,
    'tickets', tk,
    'installs', ins,
    'modes', md
  );
end;
$$;
revoke all on function public.admin_usage_stats() from public, anon;
grant execute on function public.admin_usage_stats() to authenticated;
