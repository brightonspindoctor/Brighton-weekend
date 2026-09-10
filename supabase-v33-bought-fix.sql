-- Brighton Weekend v33
-- Use one database function for commitment writes so INSERT/UPDATE/DELETE
-- behave consistently from the browser. This avoids relying on separate
-- REST operations and gives the app a single confirmed write path.

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
    delete from public.event_interest
    where event_interest.event_id = p_event_id
      and event_interest.user_id = p_user_id;
  else
    insert into public.event_interest(event_id,user_id,user_name,status)
    values(p_event_id,p_user_id,trim(coalesce(p_user_name,'')),p_status)
    on conflict (event_id,user_id)
    do update set
      user_name = excluded.user_name,
      status = excluded.status;
  end if;

  return query
    select e.event_id,e.user_id,e.user_name,e.status
    from public.event_interest e
    where e.event_id = p_event_id
      and e.user_id = p_user_id;
end;
$$;

grant execute on function public.bw_set_event_interest(text,text,text,text)
to anon, authenticated;

-- Ensure the browser can still read the table for counts/activity refreshes.
alter table public.event_interest enable row level security;
grant select on public.event_interest to anon, authenticated;
drop policy if exists "bw_event_interest_read" on public.event_interest;
create policy "bw_event_interest_read"
on public.event_interest for select
to anon, authenticated using (true);

-- Required by the ON CONFLICT used above.
create unique index if not exists event_interest_event_user_unique
on public.event_interest(event_id,user_id);
