-- Brighton Weekend v20: Groups
-- Run this once in Supabase SQL Editor.
-- This deliberately leaves your existing event_interest data untouched.

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

-- No direct browser access: the app uses controlled RPC functions below.
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
  if exists(select 1 from bw_groups where lower(name)=lower(trim(p_name))) then raise exception 'A group with that name already exists'; end if;
  if p_is_private then
    loop
      pin:=lpad((floor(random()*1000))::int::text,3,'0');
      exit when not exists(select 1 from bw_groups where join_pin=pin and is_private);
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
    select id,is_private,join_pin into gid,private_group,stored_pin from bw_groups where id=p_group_id;
  else
    select id,is_private,join_pin into gid,private_group,stored_pin
    from bw_groups where lower(name)=lower(trim(p_group_name)) and is_private=true;
  end if;
  if gid is null then return query select false,'Group not found'; return; end if;
  if private_group and (p_pin is null or p_pin<>stored_pin) then return query select false,'Incorrect PIN'; return; end if;
  insert into bw_group_members(group_id,user_id,user_name) values(gid,p_user_id,trim(p_user_name))
  on conflict(group_id,user_id) do update set user_name=excluded.user_name;
  return query select true,'Joined';
end;
$$;

create or replace function public.bw_shared_happenings(p_user_id text)
returns table(group_id uuid, group_name text, event_id text, user_id text, user_name text, status text)
language sql security definer set search_path = public
as $$
  select distinct g.id,g.name,e.event_id,e.user_id,e.user_name,e.status
  from bw_group_members mine
  join bw_group_members other on other.group_id=mine.group_id and other.user_id<>p_user_id
  join bw_groups g on g.id=mine.group_id
  join event_interest e on e.user_id=other.user_id
  where mine.user_id=p_user_id
    and e.status in ('interested','ticket_bought');
$$;

grant execute on function public.bw_my_groups(text) to anon, authenticated;
grant execute on function public.bw_public_groups(text) to anon, authenticated;
grant execute on function public.bw_create_group(text,text,text,boolean) to anon, authenticated;
grant execute on function public.bw_join_group(text,text,uuid,text,text) to anon, authenticated;
grant execute on function public.bw_shared_happenings(text) to anon, authenticated;
