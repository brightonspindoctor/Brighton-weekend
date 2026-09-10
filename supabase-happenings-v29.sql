-- Brighton Weekend v29
-- Happenings now shows every member of every group the current user belongs to,
-- plus Interested/Bought activity (including the current user).

create or replace function public.bw_group_members_for_user(p_user_id text)
returns table(group_id uuid, group_name text, user_id text, user_name text)
language sql
security definer
set search_path = public
as $$
  select distinct g.id, g.name, m.user_id, m.user_name
  from bw_group_members mine
  join bw_group_members m on m.group_id = mine.group_id
  join bw_groups g on g.id = mine.group_id
  where mine.user_id = p_user_id
  order by g.name, m.user_name;
$$;

grant execute on function public.bw_group_members_for_user(text) to anon, authenticated;

-- Keep the v28 activity function: it includes the current user's own activity.
create or replace function public.bw_shared_happenings(p_user_id text)
returns table(group_id uuid, group_name text, event_id text, user_id text, user_name text, status text)
language sql
security definer
set search_path = public
as $$
  select distinct g.id, g.name, e.event_id, e.user_id, e.user_name, e.status
  from bw_group_members mine
  join bw_group_members other on other.group_id = mine.group_id
  join bw_groups g on g.id = mine.group_id
  join event_interest e on e.user_id = other.user_id
  where mine.user_id = p_user_id
    and e.status in ('interested','ticket_bought');
$$;

grant execute on function public.bw_shared_happenings(text) to anon, authenticated;
