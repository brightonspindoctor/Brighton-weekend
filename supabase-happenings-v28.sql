-- Brighton Weekend v28
-- Happenings includes the current user's own Interested/Bought activity,
-- as well as activity from other members of the user's groups.
-- Run this in the Supabase SQL editor.

create or replace function public.bw_shared_happenings(p_user_id text)
returns table(group_id uuid, group_name text, event_id text, user_id text, user_name text, status text)
language sql
security definer
set search_path = public
as $$
  select distinct
    g.id,
    g.name,
    e.event_id,
    e.user_id,
    e.user_name,
    e.status
  from bw_group_members mine
  join bw_group_members other
    on other.group_id = mine.group_id
  join bw_groups g
    on g.id = mine.group_id
  join event_interest e
    on e.user_id = other.user_id
  where mine.user_id = p_user_id
    and e.status in ('interested','ticket_bought');
$$;

grant execute on function public.bw_shared_happenings(text) to anon, authenticated;
