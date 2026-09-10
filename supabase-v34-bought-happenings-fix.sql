-- Brighton Weekend v34
-- Definitive repair for Interested/Bought writes and Happenings.
-- Run this in Supabase SQL Editor.
-- It deliberately avoids PL/pgSQL output-column name ambiguity.

create or replace function public.bw_set_event_interest(
  p_user_id text,
  p_user_name text,
  p_event_id text,
  p_status text
)
returns table(result_event_id text, result_user_id text, result_user_name text, result_status text)
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_user_id is null or trim(p_user_id) = '' then
    raise exception 'User ID is required';
  end if;
  if p_event_id is null or trim(p_event_id) = '' then
    raise exception 'Event ID is required';
  end if;
  if p_status is not null and p_status not in ('not_interested','interested','ticket_bought') then
    raise exception 'Invalid commitment status';
  end if;

  if p_status is null then
    delete from public.event_interest ei
    where ei.event_id = p_event_id
      and ei.user_id = p_user_id;
  else
    insert into public.event_interest(event_id,user_id,user_name,status)
    values(p_event_id,p_user_id,trim(coalesce(p_user_name,'')),p_status)
    on conflict do update set
      user_name = excluded.user_name,
      status = excluded.status;
  end if;

  return query
    select ei.event_id, ei.user_id, ei.user_name, ei.status
    from public.event_interest ei
    where ei.event_id = p_event_id
      and ei.user_id = p_user_id;
end;
$$;

grant execute on function public.bw_set_event_interest(text,text,text,text)
to anon, authenticated;

-- Make the activity function unambiguous and include the current user's own activity.
create or replace function public.bw_shared_happenings(p_user_id text)
returns table(result_group_id uuid, result_group_name text, result_event_id text, result_user_id text, result_user_name text, result_status text)
language sql
security definer
set search_path = public
as $$
  select distinct
    g.id,
    g.name,
    ei.event_id,
    ei.user_id,
    ei.user_name,
    ei.status
  from public.bw_group_members mine
  join public.bw_group_members member_row
    on member_row.group_id = mine.group_id
  join public.bw_groups g
    on g.id = mine.group_id
  join public.event_interest ei
    on ei.user_id = member_row.user_id
  where mine.user_id = p_user_id
    and ei.status in ('interested','ticket_bought');
$$;

grant execute on function public.bw_shared_happenings(text) to anon, authenticated;

-- Ensure the browser can read the commitments used for counts and verification.
alter table public.event_interest enable row level security;
grant select on public.event_interest to anon, authenticated;
drop policy if exists "bw_event_interest_read" on public.event_interest;
create policy "bw_event_interest_read"
on public.event_interest
for select to anon, authenticated
using (true);

-- The app expects one commitment per user per event.
create unique index if not exists event_interest_event_user_unique
on public.event_interest(event_id,user_id);
