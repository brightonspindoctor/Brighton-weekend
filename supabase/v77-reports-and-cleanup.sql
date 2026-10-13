-- v77: reporting community events (Online Safety Act) and scheduled clean-up.
--
-- 1. bw_reports: anyone can report a community event from its ⋯ menu
--    (bw_report_event); guests too, as they can see community events. Reports
--    show on the admin page (admin_reports), where the admin removes the event
--    or keeps it (admin_resolve_report). Guest reports carry no ID, so they are
--    capped overall instead. Deleting an account removes its ID (and, for an
--    author, the name) from reports.
-- 2. An hourly pg_cron job deletes failed group-PIN attempts after 24 hours
--    (as the privacy policy says, even when nobody tries to join a group),
--    guest visits and usage counts after 13 months (until now only removed when
--    someone opened the app), and reports after 12 months.
-- Safe to run more than once.

create table if not exists public.bw_reports (
  id           uuid primary key default gen_random_uuid(),
  event_id     uuid not null,     -- bw_custom_events.id; the event may since have been removed
  event_title  text not null,
  event_date   text,
  author_id    text,              -- who added the event (null once their account is deleted)
  author_name  text,
  reporter_id  text,              -- null for guests, and once the reporter's account is deleted
  reason       text not null check (reason in ('illegal','scam','harmful','spam','wrong','other')),
  details      text check (char_length(details) <= 1000),
  status       text not null default 'open' check (status in ('open','removed','kept')),
  created_at   timestamptz not null default now(),
  resolved_at  timestamptz
);
alter table public.bw_reports enable row level security;
-- No policies: only the functions below touch it.
revoke all on table public.bw_reports from public, anon, authenticated;
create index if not exists bw_reports_status_time on public.bw_reports(status, created_at);
create index if not exists bw_reports_event on public.bw_reports(event_id);

create or replace function public.bw_is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.user_roles ur
                 where ur.user_id::text = auth.uid()::text and ur.role = 'admin');
$$;
revoke all on function public.bw_is_admin() from public, anon, authenticated;

-- Report a community event. Returns nothing; raises a readable message on a problem.
create or replace function public.bw_report_event(p_event_id uuid, p_reason text, p_details text default null)
returns void language plpgsql security definer set search_path = public as $$
declare
  me text := auth.uid()::text;
  ev record;
  d text := nullif(left(btrim(coalesce(p_details, '')), 1000), '');
begin
  if p_reason is null or p_reason not in ('illegal','scam','harmful','spam','wrong','other') then
    raise exception 'Please choose a reason.';
  end if;
  select e.id, e.title, e.date, e.created_by, e.created_by_name into ev
    from public.bw_custom_events e where e.id = p_event_id;
  if not found then
    raise exception 'That event has already been removed.';
  end if;
  if me is not null and ev.created_by = me then
    raise exception 'This is your event: you can remove it from its menu instead.';
  end if;
  if me is not null then
    -- One open report per person per event; a second just confirms the first.
    if exists (select 1 from public.bw_reports r
               where r.event_id = p_event_id and r.reporter_id = me and r.status = 'open') then
      return;
    end if;
    if (select count(*) from public.bw_reports r
        where r.reporter_id = me and r.created_at > now() - interval '1 day') >= 10 then
      raise exception 'You''ve sent a lot of reports today. Please email privacy@brightonweekend.co.uk instead.';
    end if;
  else
    -- Guests: at most 5 open reports per event and 30 a day in all.
    if (select count(*) from public.bw_reports r
        where r.event_id = p_event_id and r.reporter_id is null and r.status = 'open') >= 5 then
      return;
    end if;
    if (select count(*) from public.bw_reports r
        where r.reporter_id is null and r.created_at > now() - interval '1 day') >= 30 then
      raise exception 'Reports are busy right now. Please email privacy@brightonweekend.co.uk instead.';
    end if;
  end if;
  insert into public.bw_reports(event_id, event_title, event_date, author_id, author_name, reporter_id, reason, details)
  values (ev.id, left(ev.title, 150), ev.date, ev.created_by, left(ev.created_by_name, 60), me, p_reason, d);
end;
$$;
revoke all on function public.bw_report_event(uuid, text, text) from public;
grant execute on function public.bw_report_event(uuid, text, text) to anon, authenticated;

-- Admin: open reports, and those resolved in the last 30 days.
create or replace function public.admin_reports()
returns json language plpgsql security definer set search_path = public as $$
begin
  if not public.bw_is_admin() then
    raise exception 'Not authorised';
  end if;
  return (
    select coalesce(json_agg(x order by (x.status <> 'open'), x.created_at desc), '[]'::json)
    from (
      select r.id, r.event_id, r.event_title, r.event_date, r.author_name, r.reason, r.details,
             r.status, r.created_at, r.resolved_at, (r.reporter_id is null) as from_guest,
             exists (select 1 from public.bw_custom_events e where e.id = r.event_id) as event_live,
             (select count(*) from public.bw_reports r2 where r2.event_id = r.event_id) as reports_for_event
      from public.bw_reports r
      where r.status = 'open' or r.resolved_at > now() - interval '30 days'
      order by r.created_at desc
      limit 200
    ) x
  );
end;
$$;
revoke all on function public.admin_reports() from public, anon;
grant execute on function public.admin_reports() to authenticated;

-- Admin: remove the reported event (closing every open report on it), or keep it.
create or replace function public.admin_resolve_report(p_report_id uuid, p_remove_event boolean)
returns void language plpgsql security definer set search_path = public as $$
declare ev uuid;
begin
  if not public.bw_is_admin() then
    raise exception 'Not authorised';
  end if;
  select r.event_id into ev from public.bw_reports r where r.id = p_report_id;
  if not found then
    raise exception 'Report not found';
  end if;
  if p_remove_event then
    delete from public.bw_custom_events where id = ev;
    update public.bw_reports set status = 'removed', resolved_at = now()
     where event_id = ev and status = 'open';
  else
    update public.bw_reports set status = 'kept', resolved_at = now() where id = p_report_id;
  end if;
end;
$$;
revoke all on function public.admin_resolve_report(uuid, boolean) from public, anon;
grant execute on function public.admin_resolve_report(uuid, boolean) to authenticated;

-- Deleting an account (in Settings or in the dashboard) also clears it from reports.
create or replace function public.bw_cleanup_deleted_user()
returns trigger language plpgsql security definer set search_path = public as $$
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
  update public.bw_reports set reporter_id = null where reporter_id = uid;
  update public.bw_reports set author_id = null, author_name = null where author_id = uid;
  delete from public.bw_profiles      where user_id::text = uid;
  return old;
end;
$$;

-- 2. Hourly clean-up.
create extension if not exists pg_cron with schema pg_catalog;
grant usage on schema cron to postgres;
grant all privileges on all tables in schema cron to postgres;
select cron.unschedule(jobid) from cron.job where jobname = 'bw-hourly-cleanup';
select cron.schedule('bw-hourly-cleanup', '23 * * * *', $job$
  delete from public.bw_join_attempts where attempted_at < now() - interval '1 day';
  delete from public.bw_guest_visits  where last_seen_at < now() - interval '13 months';
  delete from public.bw_usage_events  where created_at < now() - interval '13 months';
  delete from public.bw_reports       where created_at < now() - interval '12 months';
$job$);
