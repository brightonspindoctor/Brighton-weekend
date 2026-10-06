-- ============================================================================
-- Brighton Weekend v60 — new avatars need no database change
-- Run once in the Supabase SQL Editor, after v59. Safe to re-run.
--
-- bw_profiles.profile_icon was limited to a fixed list of avatar ids, so every
-- new avatar also needed this list edited before anyone could choose it
-- ("Could not save your icon yet"). The app decides which avatars exist and
-- only ever displays ids from its own list, so the database now just checks
-- that an id is well formed: lowercase words joined by hyphens, e.g. red-fox.
-- (The separate 40-character length limit stays.)
-- ============================================================================
alter table public.bw_profiles drop constraint if exists bw_profiles_profile_icon_check;
alter table public.bw_profiles add constraint bw_profiles_profile_icon_check
  check (profile_icon is null or profile_icon ~ '^[a-z0-9]+(-[a-z0-9]+)*$');
