-- ============================================================================
-- Brighton Weekend v49 — Happenings shows every response from your groups
-- Run ONCE in the Supabase SQL Editor, after v48-security-hardening.sql.
-- Safe to re-run.
--
-- bw_shared_happenings previously returned only Interested and Going. The
-- Happenings page now also shows who in your groups said "Not for me", so the
-- function returns all three statuses. It keeps the v48 rule that it only works
-- for the signed-in user, and it still only returns people who share a group
-- with you.
-- ============================================================================
create or replace function public.bw_shared_happenings(p_user_id text)
returns table(group_id uuid, group_name text, event_id text, user_id text, user_name text, status text)
language sql security definer set search_path = public
as $$
  select distinct
    g.id as group_id, g.name as group_name, ei.event_id as event_id,
    ei.user_id as user_id, ei.user_name as user_name, ei.status as status
  from public.bw_group_members as mine
  join public.bw_group_members as member_row on member_row.group_id = mine.group_id
  join public.bw_groups as g on g.id = mine.group_id
  join public.event_interest as ei on ei.user_id = member_row.user_id
  where mine.user_id = p_user_id
    and p_user_id = auth.uid()::text
    and ei.status in ('interested','ticket_bought','not_interested');
$$;

revoke all on function public.bw_shared_happenings(text) from public, anon;
grant execute on function public.bw_shared_happenings(text) to authenticated;
