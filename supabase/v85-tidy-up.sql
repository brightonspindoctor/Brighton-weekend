-- v85: tidy-up from the 5 November 2026 review. Safe to run now (it doesn't
-- touch groups; v83 still removes those from 4 December) and safe to run more
-- than once.
--
-- 1. The hourly clean-up now also clears crew lookups after a day and declined
--    crew requests after 6 months, as the privacy policy says. Until now
--    lookups were only cleared when the same person looked someone up again,
--    and declined requests were never cleared.
-- 2. Handles can only be changed through bw_set_handle (Settings), not by
--    writing to bw_profiles directly. Signed-in users keep insert and update on
--    the columns the app writes: user_id, email, display_name, profile_icon.
-- 3. Removes bw_set_profile_icon (the app saves icons to bw_profiles directly)
--    and an index that is never used.
-- 4. bw_clean_handle gets a fixed search_path and is no longer callable
--    from the app (only the crew functions use it).
-- 5. Policies call auth.uid() once per query rather than once per row
--    (Supabase performance advisor), and bw_event_genres.user_id gets the
--    index that deleting an account uses.

-- 1. Hourly clean-up (keeps clearing group PIN tries until v83 drops them)
select cron.unschedule(jobid) from cron.job where jobname = 'bw-hourly-cleanup';
select cron.schedule('bw-hourly-cleanup', '23 * * * *', $job$
  delete from public.bw_join_attempts where attempted_at < now() - interval '1 day';
  delete from public.bw_crew_lookups  where at < now() - interval '1 day';
  delete from public.bw_crew_requests where declined_at < now() - interval '6 months';
  delete from public.bw_guest_visits  where last_seen_at < now() - interval '13 months';
  delete from public.bw_usage_events  where created_at < now() - interval '13 months';
  delete from public.bw_reports       where created_at < now() - interval '12 months';
$job$);

-- 2. Profile columns the app may write
revoke insert, update on public.bw_profiles from authenticated;
grant insert (user_id, email, display_name, profile_icon) on public.bw_profiles to authenticated;
grant update (user_id, email, display_name, profile_icon) on public.bw_profiles to authenticated;

-- 3. Unused
drop function if exists public.bw_set_profile_icon(text, text);
drop index if exists public.bw_custom_events_venue_idx;

-- 4. bw_clean_handle
alter function public.bw_clean_handle(text) set search_path = public;
revoke execute on function public.bw_clean_handle(text) from public, anon, authenticated;

-- 5. Policies and index
alter policy bw_profiles_select_own on public.bw_profiles
  using ((select auth.uid()) = user_id);
alter policy bw_profiles_insert_own on public.bw_profiles
  with check ((select auth.uid()) = user_id
              and lower(email) = lower(coalesce((select auth.jwt()) ->> 'email', '')));
alter policy bw_profiles_update_own on public.bw_profiles
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id
              and lower(email) = lower(coalesce((select auth.jwt()) ->> 'email', '')));
alter policy bw_event_interest_select_own on public.event_interest
  using (user_id = (select auth.uid())::text);
alter policy bw_custom_events_insert_own on public.bw_custom_events
  with check (created_by = (select auth.uid())::text);
alter policy bw_custom_events_delete_own on public.bw_custom_events
  using (created_by = (select auth.uid())::text);

create index if not exists bw_event_genres_user_id_idx on public.bw_event_genres (user_id);
