-- v84: read-only views that show people's display names next to user IDs,
-- for browsing in the Supabase Table Editor. Names are looked up live from
-- bw_profiles, so nothing is copied and deleting an account needs no extra
-- clean-up. Tables that already keep a name (event_interest, bw_custom_events,
-- app_visitors, and the report's author) don't need one.
--
-- The views run with the permissions of whoever reads them (security_invoker),
-- and the app's roles (anon, authenticated) can't read them at all, so they're
-- only visible in the Supabase dashboard.
-- Safe to run more than once.

create or replace view public.crew_named with (security_invoker = on) as
  select a.display_name as user_a_name, a.handle as user_a_handle,
         b.display_name as user_b_name, b.handle as user_b_handle,
         c.created_at, c.user_a, c.user_b
  from public.bw_crew c
  left join public.bw_profiles a on a.user_id = c.user_a
  left join public.bw_profiles b on b.user_id = c.user_b;

create or replace view public.crew_requests_named with (security_invoker = on) as
  select f.display_name as from_name, f.handle as from_handle,
         t.display_name as to_name, t.handle as to_handle,
         r.created_at, r.declined_at, r.from_user, r.to_user
  from public.bw_crew_requests r
  left join public.bw_profiles f on f.user_id = r.from_user
  left join public.bw_profiles t on t.user_id = r.to_user;

create or replace view public.crew_lookups_named with (security_invoker = on) as
  select p.display_name as user_name, l.*
  from public.bw_crew_lookups l
  left join public.bw_profiles p on p.user_id = l.user_id;

create or replace view public.event_genres_named with (security_invoker = on) as
  select p.display_name as user_name, g.*
  from public.bw_event_genres g
  left join public.bw_profiles p on p.user_id = g.user_id;

create or replace view public.usage_events_named with (security_invoker = on) as
  select p.display_name as user_name, u.*
  from public.bw_usage_events u
  left join public.bw_profiles p on p.user_id::text = u.user_id;

create or replace view public.guest_visits_named with (security_invoker = on) as
  select p.display_name as converted_user_name, v.*
  from public.bw_guest_visits v
  left join public.bw_profiles p on p.user_id::text = v.converted_user_id;

create or replace view public.user_roles_named with (security_invoker = on) as
  select p.display_name as user_name, r.*
  from public.user_roles r
  left join public.bw_profiles p on p.user_id::text = r.user_id;

create or replace view public.reports_named with (security_invoker = on) as
  select p.display_name as reporter_name, r.*
  from public.bw_reports r
  left join public.bw_profiles p on p.user_id::text = r.reporter_id;

revoke all on public.crew_named, public.crew_requests_named, public.crew_lookups_named,
  public.event_genres_named, public.usage_events_named, public.guest_visits_named,
  public.user_roles_named, public.reports_named
  from public, anon, authenticated;
