-- v72: count guests (people browsing without a login).
-- Each guest's device keeps a random ID (no name, email or other details).
-- bw_track_guest records a visit; bw_link_guest marks that ID as converted
-- when the person signs up, so the admin page can show guest-to-user
-- conversion. Rows not seen for 13 months are removed.

create table if not exists public.bw_guest_visits (
  guest_id          uuid primary key,
  first_seen_at     timestamptz not null default now(),
  last_seen_at      timestamptz not null default now(),
  visit_days        int not null default 1,
  converted_user_id text,
  converted_at      timestamptz
);
alter table public.bw_guest_visits enable row level security;
-- No policies: only the functions below (and admin_usage_stats) touch it.
revoke all on table public.bw_guest_visits from public, anon, authenticated;
create index if not exists bw_guest_visits_last_seen on public.bw_guest_visits(last_seen_at);

create or replace function public.bw_track_guest(p_guest_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_guest_id is null or auth.uid() is not null then return; end if; -- signed-in visits are tracked by bw_track_visit
  update bw_guest_visits
     set visit_days = visit_days + case when last_seen_at::date < now()::date then 1 else 0 end,
         last_seen_at = now()
   where guest_id = p_guest_id;
  if not found then
    -- Simple flood guard: ignore new IDs beyond 500 an hour.
    if (select count(*) from bw_guest_visits where first_seen_at > now() - interval '1 hour') >= 500 then return; end if;
    insert into bw_guest_visits(guest_id) values (p_guest_id) on conflict (guest_id) do nothing;
  end if;
  delete from bw_guest_visits where last_seen_at < now() - interval '13 months';
end;
$$;
revoke all on function public.bw_track_guest(uuid) from public;
grant execute on function public.bw_track_guest(uuid) to anon, authenticated;

create or replace function public.bw_link_guest(p_guest_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare uid text := auth.uid()::text;
begin
  if uid is null or p_guest_id is null then return; end if;
  update bw_guest_visits
     set converted_user_id = uid, converted_at = now()
   where guest_id = p_guest_id and converted_at is null;
end;
$$;
revoke all on function public.bw_link_guest(uuid) from public, anon;
grant execute on function public.bw_link_guest(uuid) to authenticated;

-- Deleting an account unlinks it from any guest row (the anonymous count stays).
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
  delete from public.bw_profiles      where user_id::text = uid;
  return old;
end;
$$;

-- Admin dashboard: add guest figures.
create or replace function public.admin_usage_stats()
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  total_count bigint; recent_count bigint; last_seen timestamptz;
  guests_total bigint; guests_recent bigint; guests_converted bigint;
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

  return json_build_object(
    'total_users', total_count,
    'recent_users', recent_count,
    'last_seen', last_seen,
    'total_guests', guests_total,
    'recent_guests', guests_recent,
    'converted_guests', guests_converted
  );
end;
$$;
