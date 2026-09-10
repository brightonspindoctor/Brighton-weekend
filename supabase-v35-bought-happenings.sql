-- Brighton Weekend v35
-- Canonical fix for Bought/Interested + Happenings.
-- IMPORTANT: preserves the existing function return types/names so CREATE OR REPLACE works.

create or replace function public.bw_set_event_interest(
  p_user_id text,
  p_user_name text,
  p_event_id text,
  p_status text
)
returns table(event_id text, user_id text, user_name text, status text)
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_user_id is null or btrim(p_user_id) = '' then
    raise exception 'User ID is required';
  end if;
  if p_event_id is null or btrim(p_event_id) = '' then
    raise exception 'Event ID is required';
  end if;
  if p_status is not null and p_status not in ('not_interested','interested','ticket_bought') then
    raise exception 'Invalid commitment status';
  end if;

  if p_status is null then
    delete from public.event_interest AS ei
    where ei.event_id = p_event_id
      and ei.user_id = p_user_id;
  else
    insert into public.event_interest AS ei (event_id, user_id, user_name, status)
    values (p_event_id, p_user_id, btrim(coalesce(p_user_name,'')), p_status)
    on conflict (event_id, user_id) do update
      set user_name = excluded.user_name,
          status = excluded.status;
  end if;

  return query
  select ei.event_id, ei.user_id, ei.user_name, ei.status
  from public.event_interest AS ei
  where ei.event_id = p_event_id
    and ei.user_id = p_user_id;
end;
$$;

grant execute on function public.bw_set_event_interest(text,text,text,text) to anon, authenticated;

create or replace function public.bw_shared_happenings(p_user_id text)
returns table(group_id uuid, group_name text, event_id text, user_id text, user_name text, status text)
language sql
security definer
set search_path = public
as $$
  select distinct
    g.id AS group_id,
    g.name AS group_name,
    ei.event_id AS event_id,
    ei.user_id AS user_id,
    ei.user_name AS user_name,
    ei.status AS status
  from public.bw_group_members AS mine
  join public.bw_group_members AS member_row
    on member_row.group_id = mine.group_id
  join public.bw_groups AS g
    on g.id = mine.group_id
  join public.event_interest AS ei
    on ei.user_id = member_row.user_id
  where mine.user_id = p_user_id
    and ei.status in ('interested','ticket_bought');
$$;

grant execute on function public.bw_shared_happenings(text) to anon, authenticated;

alter table public.event_interest enable row level security;
grant select on public.event_interest to anon, authenticated;
drop policy if exists "bw_event_interest_read" on public.event_interest;
create policy "bw_event_interest_read"
on public.event_interest for select to anon, authenticated using (true);

create unique index if not exists event_interest_event_user_unique
on public.event_interest(event_id,user_id);
