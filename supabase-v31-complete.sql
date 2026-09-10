-- Brighton Weekend v31 — complete Supabase setup/repair
-- Run this ONE file in Supabase SQL Editor.
-- It is safe to run after earlier Brighton Weekend migrations because it uses
-- CREATE IF NOT EXISTS / CREATE OR REPLACE and refreshes the relevant policies.

-- ============================================================
-- GROUPS
-- ============================================================
create table if not exists public.bw_groups (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(trim(name)) between 2 and 50),
  is_private boolean not null default false,
  join_pin text check (join_pin is null or join_pin ~ '^[0-9]{3}$'),
  created_by text not null,
  created_at timestamptz not null default now()
);
create unique index if not exists bw_groups_name_unique
on public.bw_groups (lower(name));

create table if not exists public.bw_group_members (
  group_id uuid not null references public.bw_groups(id) on delete cascade,
  user_id text not null,
  user_name text not null,
  joined_at timestamptz not null default now(),
  primary key (group_id, user_id)
);

alter table public.bw_groups enable row level security;
alter table public.bw_group_members enable row level security;
revoke all on public.bw_groups from anon, authenticated;
revoke all on public.bw_group_members from anon, authenticated;

create or replace function public.bw_my_groups(p_user_id text)
returns table(id uuid, name text, is_private boolean, member_count bigint, join_pin text)
language sql security definer set search_path = public
as $$
  select g.id,g.name,g.is_private,count(m2.user_id)::bigint,
    case when g.created_by=p_user_id and g.is_private then g.join_pin else null end
  from bw_groups g
  join bw_group_members m on m.group_id=g.id and m.user_id=p_user_id
  left join bw_group_members m2 on m2.group_id=g.id
  group by g.id,g.name,g.is_private,g.join_pin,g.created_by;
$$;

create or replace function public.bw_public_groups(p_user_id text)
returns table(id uuid, name text, member_count bigint)
language sql security definer set search_path = public
as $$
  select g.id,g.name,count(m.user_id)::bigint
  from bw_groups g left join bw_group_members m on m.group_id=g.id
  where g.is_private=false
    and not exists (select 1 from bw_group_members mine where mine.group_id=g.id and mine.user_id=p_user_id)
  group by g.id,g.name
  order by lower(g.name);
$$;

create or replace function public.bw_create_group(
  p_user_id text,p_user_name text,p_name text,p_is_private boolean
)
returns table(id uuid, name text, is_private boolean, join_pin text)
language plpgsql security definer set search_path = public
as $$
declare gid uuid; pin text;
begin
  if char_length(trim(coalesce(p_name,''))) < 2 then raise exception 'Group name must be at least 2 characters'; end if;
  if exists(select 1 from bw_groups g0 where lower(g0.name)=lower(trim(p_name))) then raise exception 'A group with that name already exists'; end if;
  if p_is_private then
    loop
      pin:=lpad((floor(random()*1000))::int::text,3,'0');
      exit when not exists(select 1 from bw_groups g0 where g0.join_pin=pin and g0.is_private);
    end loop;
  else pin:=null; end if;
  insert into bw_groups(name,is_private,join_pin,created_by)
    values(trim(p_name),p_is_private,pin,p_user_id) returning bw_groups.id into gid;
  insert into bw_group_members(group_id,user_id,user_name) values(gid,p_user_id,trim(p_user_name));
  return query select g.id,g.name,g.is_private,g.join_pin from bw_groups g where g.id=gid;
end;
$$;

create or replace function public.bw_join_group(
  p_user_id text,p_user_name text,p_group_id uuid,p_pin text,p_group_name text
)
returns table(ok boolean, message text)
language plpgsql security definer set search_path = public
as $$
declare gid uuid; private_group boolean; stored_pin text;
begin
  if p_group_id is not null then
    select g.id,g.is_private,g.join_pin into gid,private_group,stored_pin from bw_groups g where g.id=p_group_id;
  else
    select g.id,g.is_private,g.join_pin into gid,private_group,stored_pin
    from bw_groups g where lower(g.name)=lower(trim(p_group_name)) and g.is_private=true;
  end if;
  if gid is null then return query select false,'Group not found'; return; end if;
  if private_group and (p_pin is null or p_pin<>stored_pin) then return query select false,'Incorrect PIN'; return; end if;
  insert into bw_group_members(group_id,user_id,user_name) values(gid,p_user_id,trim(p_user_name))
  on conflict(group_id,user_id) do update set user_name=excluded.user_name;
  return query select true,'Joined';
end;
$$;

create or replace function public.bw_group_members_for_user(p_user_id text)
returns table(group_id uuid, group_name text, user_id text, user_name text)
language sql security definer set search_path = public
as $$
  select distinct g.id, g.name, m.user_id, m.user_name
  from bw_group_members mine
  join bw_group_members m on m.group_id = mine.group_id
  join bw_groups g on g.id = mine.group_id
  where mine.user_id = p_user_id
  order by g.name, m.user_name;
$$;

create or replace function public.bw_shared_happenings(p_user_id text)
returns table(group_id uuid, group_name text, event_id text, user_id text, user_name text, status text)
language sql security definer set search_path = public
as $$
  select distinct g.id, g.name, e.event_id, e.user_id, e.user_name, e.status
  from bw_group_members mine
  join bw_group_members other on other.group_id = mine.group_id
  join bw_groups g on g.id = mine.group_id
  join event_interest e on e.user_id = other.user_id
  where mine.user_id = p_user_id
    and e.status in ('interested','ticket_bought');
$$;

grant execute on function public.bw_my_groups(text) to anon, authenticated;
grant execute on function public.bw_public_groups(text) to anon, authenticated;
grant execute on function public.bw_create_group(text,text,text,boolean) to anon, authenticated;
grant execute on function public.bw_join_group(text,text,uuid,text,text) to anon, authenticated;
grant execute on function public.bw_group_members_for_user(text) to anon, authenticated;
grant execute on function public.bw_shared_happenings(text) to anon, authenticated;

-- ============================================================
-- EVENT COMMITMENTS (Interested / Bought)
-- ============================================================
alter table public.event_interest enable row level security;

drop policy if exists "bw_event_interest_read" on public.event_interest;
drop policy if exists "bw_event_interest_insert" on public.event_interest;
drop policy if exists "bw_event_interest_update" on public.event_interest;
drop policy if exists "bw_event_interest_delete" on public.event_interest;

grant select, insert, update, delete on public.event_interest to anon, authenticated;

create policy "bw_event_interest_read"
on public.event_interest for select to anon, authenticated using (true);
create policy "bw_event_interest_insert"
on public.event_interest for insert to anon, authenticated with check (true);
create policy "bw_event_interest_update"
on public.event_interest for update to anon, authenticated using (true) with check (true);
create policy "bw_event_interest_delete"
on public.event_interest for delete to anon, authenticated using (true);

create unique index if not exists event_interest_event_user_unique
on public.event_interest(event_id, user_id);

-- ============================================================
-- COMMUNITY EVENTS
-- ============================================================
create table if not exists public.bw_custom_events (
  id uuid primary key default gen_random_uuid(),
  title text not null check (char_length(trim(title)) between 2 and 120),
  date text not null check (date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  venue text not null check (venue in (
    'Brighton Centre','Brighton Dome','CHALK','Concorde 2','The Old Market',
    'Green Door Store','Volks','Quarters','Patterns','DUST','Komedia',
    'The Forge Comedy Club','Theatre Royal Brighton','Other'
  )),
  venue_detail text,
  time text,
  finish_time text,
  price text,
  status text not null default '',
  ticket_url text,
  category text not null default 'Other',
  description text,
  created_by text not null,
  created_by_name text not null,
  created_at timestamptz not null default now(),
  check ((venue = 'Other' and char_length(trim(coalesce(venue_detail,''))) between 2 and 100)
      or (venue <> 'Other' and venue_detail is null))
);

create index if not exists bw_custom_events_date_idx on public.bw_custom_events(date);
create index if not exists bw_custom_events_venue_idx on public.bw_custom_events(venue);

alter table public.bw_custom_events enable row level security;
revoke all on public.bw_custom_events from anon, authenticated;

drop policy if exists "bw_custom_events_read" on public.bw_custom_events;
drop policy if exists "bw_custom_events_insert" on public.bw_custom_events;
create policy "bw_custom_events_read" on public.bw_custom_events for select to anon, authenticated using (true);
create policy "bw_custom_events_insert" on public.bw_custom_events for insert to anon, authenticated with check (true);
grant select, insert on public.bw_custom_events to anon, authenticated;
