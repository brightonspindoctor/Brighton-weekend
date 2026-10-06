-- ============================================================================
-- Brighton Weekend — live database schema (public schema)
-- Exported from the live Supabase project on 2026-10-05, after v58 and v59; v60 (avatar ids) applied on top.
--
-- This file is the reference for what is actually running. The numbered
-- files (v48, v49, v58) are the change history. When you change the database,
-- add a new numbered file AND update this file, so the two never drift apart.
--
-- Security model in one paragraph: RLS is on for every table. The browser
-- can read only its own profile and its own Interested/Going rows, can read
-- community events, and can insert/delete only its own community events.
-- Everything else (groups, members, happenings, joining with a PIN, account
-- deletion, visit tracking, admin stats) goes through the SECURITY DEFINER
-- functions below, each of which checks the caller with auth.uid().
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Tables (RLS is enabled on all of them)
-- ---------------------------------------------------------------------------
create table if not exists public.app_visitors (
  user_id text not null,
  display_name text,
  first_seen_at timestamp with time zone not null default now(),
  last_seen_at timestamp with time zone not null default now()
);

create table if not exists public.bw_custom_events (
  id uuid not null default gen_random_uuid(),
  title text not null,
  date text not null,
  venue text not null,
  venue_detail text,
  "time" text,
  finish_time text,
  price text,
  status text not null default ''::text,
  ticket_url text,
  category text not null default 'Other'::text,
  description text,
  created_by text not null,
  created_by_name text not null,
  created_at timestamp with time zone not null default now()
);

create table if not exists public.bw_group_members (
  group_id uuid not null,
  user_id text not null,
  user_name text not null,
  joined_at timestamp with time zone not null default now()
);

create table if not exists public.bw_groups (
  id uuid not null default gen_random_uuid(),
  name text not null,
  is_private boolean not null default true,
  join_pin text,
  created_by text not null,
  created_at timestamp with time zone not null default now()
);

create table if not exists public.bw_join_attempts (
  user_id text not null,
  attempted_at timestamp with time zone not null default now()
);

create table if not exists public.bw_profiles (
  user_id uuid not null,
  email text not null,
  display_name text not null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  profile_icon text
);

create table if not exists public.event_interest (
  id bigint not null generated always as identity,
  event_id text not null,
  user_name text not null,
  status text not null,
  created_at timestamp with time zone not null default now(),
  user_id text,
  plus_one integer not null default 0
);

create table if not exists public.user_roles (
  user_id text not null,
  role text not null
);

alter table public.app_visitors     enable row level security;
alter table public.bw_custom_events enable row level security;
alter table public.bw_group_members enable row level security;
alter table public.bw_groups        enable row level security;
alter table public.bw_join_attempts enable row level security;
alter table public.bw_profiles      enable row level security;
alter table public.event_interest   enable row level security;
alter table public.user_roles       enable row level security;

-- ---------------------------------------------------------------------------
-- Constraints
-- ---------------------------------------------------------------------------
alter table public.app_visitors add constraint app_visitors_pkey PRIMARY KEY (user_id);

alter table public.bw_custom_events add constraint bw_custom_events_pkey PRIMARY KEY (id);
alter table public.bw_custom_events add constraint bw_custom_events_category_length CHECK ((char_length(category) <= 40)) NOT VALID;
alter table public.bw_custom_events add constraint bw_custom_events_check CHECK ((((venue = 'Other'::text) AND ((char_length(TRIM(BOTH FROM COALESCE(venue_detail, ''::text))) >= 2) AND (char_length(TRIM(BOTH FROM COALESCE(venue_detail, ''::text))) <= 100))) OR ((venue <> 'Other'::text) AND (venue_detail IS NULL))));
alter table public.bw_custom_events add constraint bw_custom_events_created_by_name_length CHECK ((char_length(created_by_name) <= 60)) NOT VALID;
alter table public.bw_custom_events add constraint bw_custom_events_date_check CHECK ((date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'::text));
alter table public.bw_custom_events add constraint bw_custom_events_description_length CHECK ((char_length(description) <= 600)) NOT VALID;
alter table public.bw_custom_events add constraint bw_custom_events_price_length CHECK ((char_length(price) <= 60)) NOT VALID;
alter table public.bw_custom_events add constraint bw_custom_events_ticket_url_http CHECK (((ticket_url IS NULL) OR (ticket_url ~* '^https?://'::text))) NOT VALID;
alter table public.bw_custom_events add constraint bw_custom_events_title_check CHECK (((char_length(TRIM(BOTH FROM title)) >= 2) AND (char_length(TRIM(BOTH FROM title)) <= 120)));
alter table public.bw_custom_events add constraint bw_custom_events_title_length CHECK ((char_length(title) <= 150)) NOT VALID;
alter table public.bw_custom_events add constraint bw_custom_events_venue_detail_length CHECK ((char_length(venue_detail) <= 120)) NOT VALID;
alter table public.bw_custom_events add constraint bw_custom_events_time_format CHECK (((time IS NULL) OR (time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'::text)));
alter table public.bw_custom_events add constraint bw_custom_events_finish_time_format CHECK (((finish_time IS NULL) OR (finish_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'::text)));
alter table public.bw_custom_events add constraint bw_custom_events_status_allowed CHECK ((status = ANY (ARRAY[''::text, 'SOLD OUT'::text])));
-- Must match VENUES in index.html.
alter table public.bw_custom_events add constraint bw_custom_events_venue_allowed CHECK ((venue = ANY (ARRAY[
  'Brighton Centre'::text, 'Brighton Dome'::text, 'CHALK'::text, 'Concorde 2'::text, 'The Old Market'::text,
  'Green Door Store'::text, 'Volks'::text, 'Quarters'::text, 'Patterns'::text, 'DUST'::text, 'Komedia'::text,
  'The Forge Comedy Club'::text, 'Theatre Royal Brighton'::text, 'The Hope & Ruin'::text, 'The Prince Albert'::text,
  'A L P H A B E T'::text, 'The Pipeline'::text, 'Brighton Racecourse'::text, 'The Gladstone'::text, 'Babble'::text,
  'Old Albion'::text, 'Amex Stadium'::text, 'Shelter Hall'::text, 'Other'::text])));

alter table public.bw_group_members add constraint bw_group_members_pkey PRIMARY KEY (group_id, user_id);
alter table public.bw_group_members add constraint bw_group_members_group_id_fkey FOREIGN KEY (group_id) REFERENCES bw_groups(id) ON DELETE CASCADE;
alter table public.bw_group_members add constraint bw_group_members_user_name_length CHECK ((char_length(user_name) <= 60)) NOT VALID;

alter table public.bw_groups add constraint bw_groups_pkey PRIMARY KEY (id);
alter table public.bw_groups add constraint bw_groups_join_pin_check CHECK (((join_pin IS NULL) OR (join_pin ~ '^[0-9]{3}$'::text)));
alter table public.bw_groups add constraint bw_groups_join_pin_format CHECK ((join_pin ~ '^[0-9]{3}$'::text));
alter table public.bw_groups add constraint bw_groups_name_check CHECK (((char_length(TRIM(BOTH FROM name)) >= 2) AND (char_length(TRIM(BOTH FROM name)) <= 50)));
alter table public.bw_groups add constraint bw_groups_name_length CHECK ((char_length(name) <= 60)) NOT VALID;

alter table public.bw_profiles add constraint bw_profiles_pkey PRIMARY KEY (user_id);
alter table public.bw_profiles add constraint bw_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
alter table public.bw_profiles add constraint bw_profiles_display_name_check CHECK (((char_length(TRIM(BOTH FROM display_name)) >= 1) AND (char_length(TRIM(BOTH FROM display_name)) <= 40)));
alter table public.bw_profiles add constraint bw_profiles_display_name_length CHECK ((char_length(display_name) <= 60)) NOT VALID;
alter table public.bw_profiles add constraint bw_profiles_profile_icon_length CHECK ((char_length(profile_icon) <= 40)) NOT VALID;
-- Any well-formed avatar id (v60); the app's PROFILE_ICONS list decides which exist.
alter table public.bw_profiles add constraint bw_profiles_profile_icon_check CHECK (((profile_icon IS NULL) OR (profile_icon ~ '^[a-z0-9]+(-[a-z0-9]+)*$'::text)));

alter table public.event_interest add constraint event_interest_pkey PRIMARY KEY (id);
alter table public.event_interest add constraint event_interest_event_id_length CHECK ((char_length(event_id) <= 300)) NOT VALID;
alter table public.event_interest add constraint event_interest_plus_one_check CHECK (((plus_one >= 0) AND (plus_one <= 1)));
alter table public.event_interest add constraint event_interest_status_check CHECK ((status = ANY (ARRAY['not_interested'::text, 'interested'::text, 'ticket_bought'::text])));
alter table public.event_interest add constraint event_interest_user_name_length CHECK ((char_length(user_name) <= 60)) NOT VALID;

alter table public.user_roles add constraint user_roles_pkey PRIMARY KEY (user_id);
alter table public.user_roles add constraint user_roles_role_check CHECK ((role = 'admin'::text));

-- ---------------------------------------------------------------------------
-- Indexes (besides primary keys)
-- ---------------------------------------------------------------------------
CREATE INDEX bw_custom_events_date_idx ON public.bw_custom_events USING btree (date);
CREATE INDEX bw_custom_events_venue_idx ON public.bw_custom_events USING btree (venue);
CREATE UNIQUE INDEX bw_groups_name_unique ON public.bw_groups USING btree (lower(name));
CREATE INDEX bw_join_attempts_user_time ON public.bw_join_attempts USING btree (user_id, attempted_at);
CREATE UNIQUE INDEX bw_profiles_email_unique ON public.bw_profiles USING btree (lower(email));
CREATE UNIQUE INDEX event_interest_event_user_unique ON public.event_interest USING btree (event_id, user_id);

-- ---------------------------------------------------------------------------
-- Table permissions and RLS policies
-- (app_visitors, bw_groups, bw_group_members, bw_join_attempts and user_roles
--  have NO grants or policies: only the functions below can touch them.)
-- ---------------------------------------------------------------------------
-- Signed-out visitors can't see who added an event (no created_by / created_by_name).
grant select (id, title, date, venue, venue_detail, time, finish_time, price, status,
              ticket_url, category, description, created_at) on public.bw_custom_events to anon;
grant select, insert, delete on public.bw_custom_events to authenticated;
grant select, insert, update on public.bw_profiles to authenticated;
grant select on public.event_interest to authenticated;

create policy bw_custom_events_read on public.bw_custom_events for SELECT to anon, authenticated using (true);
create policy bw_custom_events_insert_own on public.bw_custom_events for INSERT to authenticated with check ((created_by = (auth.uid())::text));
create policy bw_custom_events_delete_own on public.bw_custom_events for DELETE to authenticated using ((created_by = (auth.uid())::text));

create policy bw_profiles_select_own on public.bw_profiles for SELECT to authenticated using ((auth.uid() = user_id));
create policy bw_profiles_insert_own on public.bw_profiles for INSERT to authenticated with check (((auth.uid() = user_id) AND (lower(email) = lower(COALESCE((auth.jwt() ->> 'email'::text), ''::text)))));
create policy bw_profiles_update_own on public.bw_profiles for UPDATE to authenticated using ((auth.uid() = user_id)) with check (((auth.uid() = user_id) AND (lower(email) = lower(COALESCE((auth.jwt() ->> 'email'::text), ''::text)))));

create policy bw_event_interest_select_own on public.event_interest for SELECT to authenticated using ((user_id = (auth.uid())::text));

-- ---------------------------------------------------------------------------
-- Functions
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.bw_require_caller(p_user_id text)
 RETURNS void
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'public'
AS $function$
begin
  if auth.uid() is null or p_user_id is distinct from auth.uid()::text then
    raise exception 'Not authorised' using errcode = '42501';
  end if;
end;
$function$;

-- The signed-in caller's profile name (falls back to what the browser sent).
CREATE OR REPLACE FUNCTION public.bw_caller_name(p_fallback text)
 RETURNS text
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select left(btrim(coalesce(
    (select p.display_name from public.bw_profiles p where p.user_id = auth.uid()),
    p_fallback, '')), 60);
$function$;

CREATE OR REPLACE FUNCTION public.admin_usage_stats()
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
  total_count bigint;
  recent_count bigint;
  last_seen timestamptz;
begin
  if not exists (
    select 1 from public.user_roles ur
    where ur.user_id::text = auth.uid()::text
      and ur.role = 'admin'
  ) then
    raise exception 'Not authorised';
  end if;

  select count(*) into total_count from public.app_visitors;
  select count(*) into recent_count
  from public.app_visitors
  where last_seen_at >= now() - interval '30 days';
  select max(last_seen_at) into last_seen from public.app_visitors;

  return json_build_object(
    'total_users', total_count,
    'recent_users', recent_count,
    'last_seen', last_seen
  );
end;
$function$;

CREATE OR REPLACE FUNCTION public.bw_create_group(p_user_id text, p_user_name text, p_name text, p_is_private boolean)
 RETURNS TABLE(id uuid, name text, is_private boolean, join_pin text)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare gid uuid; pin text;
begin
  perform public.bw_require_caller(p_user_id);
  if char_length(trim(coalesce(p_name,''))) < 2 then raise exception 'Group name must be at least 2 characters'; end if;
  if char_length(trim(p_name)) > 50 then raise exception 'Group names can be up to 50 characters'; end if;
  if (select count(*) from bw_groups g0 where g0.created_by = p_user_id) >= 10 then
    raise exception 'You can create up to 10 groups.';
  end if;
  if exists(select 1 from bw_groups g0 where lower(g0.name) = lower(trim(p_name))) then raise exception 'A group with that name already exists'; end if;
  pin := lpad((floor(random()*1000))::int::text, 3, '0');
  insert into bw_groups(name, is_private, join_pin, created_by)
    values (trim(p_name), true, pin, p_user_id) returning bw_groups.id into gid;
  insert into bw_group_members(group_id, user_id, user_name) values (gid, p_user_id, public.bw_caller_name(p_user_name));
  return query select g.id, g.name, g.is_private, g.join_pin from bw_groups g where g.id = gid;
end;
$function$;

CREATE OR REPLACE FUNCTION public.bw_join_group(p_user_id text, p_user_name text, p_group_id uuid, p_pin text, p_group_name text)
 RETURNS TABLE(ok boolean, message text)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
  gid uuid; stored_pin text; members int; nm text;
  max_members constant int := 25;
  max_failures constant int := 5;
begin
  perform public.bw_require_caller(p_user_id);
  nm := public.bw_caller_name(p_user_name);

  if (select count(*) from bw_join_attempts a
       where a.user_id = p_user_id and a.attempted_at > now() - interval '15 minutes') >= max_failures then
    return query select false, 'Too many incorrect attempts. Please wait 15 minutes and try again.'; return;
  end if;

  if p_group_id is not null then
    select g.id, g.join_pin into gid, stored_pin from bw_groups g where g.id = p_group_id;
  else
    select g.id, g.join_pin into gid, stored_pin from bw_groups g where lower(g.name) = lower(trim(coalesce(p_group_name,'')));
  end if;

  -- Same message for "no such group" and "wrong PIN", so names can't be probed.
  if gid is null or p_pin is null or p_pin <> stored_pin then
    insert into bw_join_attempts(user_id) values (p_user_id);
    return query select false, 'That group name and PIN don''t match.'; return;
  end if;

  if exists(select 1 from bw_group_members m where m.group_id = gid and m.user_id = p_user_id) then
    update bw_group_members set user_name = nm where group_id = gid and user_id = p_user_id;
    return query select true, 'You''re already in this group.'; return;
  end if;

  -- Lock the group row so two people can't both take the 25th place.
  perform 1 from bw_groups g where g.id = gid for update;
  select count(*) into members from bw_group_members m where m.group_id = gid;
  if members >= max_members then
    return query select false, 'This group is full (25 members).'; return;
  end if;

  insert into bw_group_members(group_id, user_id, user_name) values (gid, p_user_id, nm);
  -- Failed attempts are NOT cleared on success: they expire after 15 minutes.
  delete from bw_join_attempts where attempted_at < now() - interval '1 day';  -- tidy old rows
  return query select true, 'Joined';
end;
$function$;

CREATE OR REPLACE FUNCTION public.bw_leave_group(p_user_id text, p_group_id uuid)
 RETURNS TABLE(ok boolean, message text)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
begin
  if auth.uid() is null or auth.uid()::text <> p_user_id then
    return query select false, 'Not authorised.'; return;
  end if;
  if p_group_id is null then
    return query select false, 'Invalid group.'; return;
  end if;

  delete from public.bw_group_members
  where user_id = p_user_id and group_id = p_group_id;

  if found then
    delete from public.bw_groups g
    where g.id = p_group_id
      and not exists (select 1 from public.bw_group_members m where m.group_id = g.id);
    return query select true, 'You have left the group.';
  else
    return query select false, 'You are not a member of that group.';
  end if;
end;
$function$;

CREATE OR REPLACE FUNCTION public.bw_my_groups(p_user_id text)
 RETURNS TABLE(id uuid, name text, is_private boolean, member_count bigint, join_pin text)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select g.id, g.name, true, count(m2.user_id)::bigint, g.join_pin
  from bw_groups g
  join bw_group_members m on m.group_id = g.id and m.user_id = p_user_id
  left join bw_group_members m2 on m2.group_id = g.id
  where p_user_id = auth.uid()::text
  group by g.id, g.name, g.join_pin;
$function$;

-- Kept so older installed copies of the app don't error; returns nothing.
CREATE OR REPLACE FUNCTION public.bw_public_groups(p_user_id text)
 RETURNS TABLE(id uuid, name text, member_count bigint)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$ select null::uuid, null::text, null::bigint where false; $function$;

CREATE OR REPLACE FUNCTION public.bw_group_members_for_user(p_user_id text)
 RETURNS TABLE(group_id uuid, group_name text, user_id text, user_name text)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select distinct g.id, g.name, m.user_id, m.user_name
  from bw_group_members mine
  join bw_group_members m on m.group_id = mine.group_id
  join bw_groups g on g.id = mine.group_id
  where mine.user_id = p_user_id
    and p_user_id = auth.uid()::text
  order by g.name, m.user_name;
$function$;

CREATE OR REPLACE FUNCTION public.bw_profile_icons_for_user(p_user_id text)
 RETURNS TABLE(user_id text, profile_icon text)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  select distinct
    gm.user_id::text as user_id,
    p.profile_icon as profile_icon
  from public.bw_group_members as mine
  join public.bw_group_members as gm
    on gm.group_id = mine.group_id
  join public.bw_profiles as p
    on p.user_id::text = gm.user_id
  where mine.user_id = p_user_id
    and p_user_id = auth.uid()::text
    and p.profile_icon is not null;
$function$;

CREATE OR REPLACE FUNCTION public.bw_set_profile_icon(p_user_id text, p_profile_icon text)
 RETURNS TABLE(user_id uuid, profile_icon text)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
begin
  if auth.uid() is null or p_user_id is null or p_user_id::uuid <> auth.uid() then raise exception 'Not authorised'; end if;
  if p_profile_icon is null or btrim(p_profile_icon) = '' then raise exception 'Profile icon is required'; end if;
  update public.bw_profiles p set profile_icon=btrim(p_profile_icon), updated_at=now() where p.user_id=auth.uid();
  if not found then raise exception 'Profile not found'; end if;
  return query select p.user_id,p.profile_icon from public.bw_profiles p where p.user_id=auth.uid();
end; $function$;

CREATE OR REPLACE FUNCTION public.bw_set_event_interest(p_user_id text, p_user_name text, p_event_id text, p_status text)
 RETURNS TABLE(event_id text, user_id text, user_name text, status text)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare nm text;
begin
  perform public.bw_require_caller(p_user_id);
  if p_event_id is null or btrim(p_event_id) = '' then
    raise exception 'Event ID is required';
  end if;
  if p_status is not null and p_status not in ('not_interested','interested','ticket_bought') then
    raise exception 'Invalid commitment status';
  end if;
  nm := public.bw_caller_name(p_user_name);

  if p_status is null then
    delete from public.event_interest as ei
    where ei.event_id = p_event_id and ei.user_id = p_user_id;
  else
    update public.event_interest as ei
       set user_name = nm, status = p_status
     where ei.event_id = p_event_id and ei.user_id = p_user_id;
    if not found then
      insert into public.event_interest as ei (event_id, user_id, user_name, status)
      values (p_event_id, p_user_id, nm, p_status);
    end if;
  end if;

  return query
  select ei.event_id, ei.user_id, ei.user_name, ei.status
  from public.event_interest as ei
  where ei.event_id = p_event_id and ei.user_id = p_user_id;
end;
$function$;

CREATE OR REPLACE FUNCTION public.bw_shared_happenings(p_user_id text)
 RETURNS TABLE(group_id uuid, group_name text, event_id text, user_id text, user_name text, status text)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION public.bw_track_visit()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare me uuid := auth.uid(); nm text;
begin
  if me is null then return; end if;
  select left(p.display_name, 60) into nm from public.bw_profiles p where p.user_id = me;
  update public.app_visitors set display_name = nm, last_seen_at = now() where user_id::text = me::text;
  if not found then
    insert into public.app_visitors(user_id, display_name, last_seen_at) values (me, nm, now());
  end if;
end;
$function$;

CREATE OR REPLACE FUNCTION public.bw_delete_my_account()
 RETURNS TABLE(ok boolean, message text)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'auth'
AS $function$
declare me uuid := auth.uid(); me_text text;
begin
  if me is null then
    return query select false, 'Not signed in.'; return;
  end if;
  me_text := me::text;

  delete from public.event_interest where event_interest.user_id = me_text;

  delete from public.bw_group_members where bw_group_members.user_id = me_text;
  delete from public.bw_groups g
   where not exists (select 1 from public.bw_group_members m where m.group_id = g.id);

  delete from public.bw_custom_events where bw_custom_events.created_by = me_text;

  if to_regclass('public.bw_join_attempts') is not null then
    delete from public.bw_join_attempts where bw_join_attempts.user_id = me_text;
  end if;
  if to_regclass('public.app_visitors') is not null then
    execute 'delete from public.app_visitors where user_id::text = $1' using me_text;
  end if;
  if to_regclass('public.bw_profiles') is not null then
    execute 'delete from public.bw_profiles where user_id::text = $1' using me_text;
  end if;

  delete from auth.users where id = me;

  return query select true, 'Your account has been deleted.';
end;
$function$;

-- ---------------------------------------------------------------------------
-- Trigger functions and triggers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.bw_custom_events_limit()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare d date; today date := (now() at time zone 'Europe/London')::date;
begin
  begin
    d := to_date(new.date, 'YYYY-MM-DD');
  exception when others then
    raise exception 'Please choose a valid date.';
  end;
  if to_char(d, 'YYYY-MM-DD') <> new.date then
    raise exception 'Please choose a valid date.';
  end if;
  if d < today or d > today + 730 then
    raise exception 'Events can be added from today up to two years ahead.';
  end if;

  if (select count(*) from public.bw_custom_events e
       where e.created_by = new.created_by
         and e.date >= to_char(today, 'YYYY-MM-DD')) >= 20 then
    raise exception 'You''ve added the maximum of 20 upcoming events. Please try again once some have passed.';
  end if;
  new.created_by_name := public.bw_caller_name(new.created_by_name);
  return new;
end;
$function$;

-- Removes all app data when an auth user is deleted (in the app or the dashboard).
CREATE OR REPLACE FUNCTION public.bw_cleanup_deleted_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare uid text := old.id::text;
begin
  delete from public.event_interest   where user_id = uid;
  delete from public.bw_group_members where user_id = uid;
  delete from public.bw_groups g
   where not exists (select 1 from public.bw_group_members m where m.group_id = g.id);
  delete from public.bw_custom_events where created_by = uid;
  delete from public.bw_join_attempts where user_id = uid;
  delete from public.app_visitors     where user_id = uid;
  delete from public.user_roles       where user_id = uid;
  delete from public.bw_profiles      where user_id::text = uid;
  return old;
end;
$function$;

CREATE OR REPLACE FUNCTION public.bw_profiles_touch_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
begin
  new.updated_at = now();
  return new;
end;
$function$;

CREATE OR REPLACE FUNCTION public.bw_profiles_propagate_name()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare nm text := left(btrim(new.display_name), 60);
begin
  if new.display_name is distinct from old.display_name then
    update public.bw_group_members set user_name = nm where user_id = new.user_id::text;
    update public.event_interest   set user_name = nm where user_id = new.user_id::text;
    update public.bw_custom_events set created_by_name = nm where created_by = new.user_id::text;
    update public.app_visitors     set display_name = nm where user_id::text = new.user_id::text;
  end if;
  return new;
end;
$function$;

CREATE TRIGGER bw_custom_events_limit BEFORE INSERT ON public.bw_custom_events FOR EACH ROW EXECUTE FUNCTION bw_custom_events_limit();
CREATE TRIGGER bw_profiles_touch_updated_at BEFORE UPDATE ON public.bw_profiles FOR EACH ROW EXECUTE FUNCTION bw_profiles_touch_updated_at();
CREATE TRIGGER bw_profiles_propagate_name AFTER UPDATE OF display_name ON public.bw_profiles FOR EACH ROW EXECUTE FUNCTION bw_profiles_propagate_name();
CREATE TRIGGER bw_cleanup_deleted_user AFTER DELETE ON auth.users FOR EACH ROW EXECUTE FUNCTION public.bw_cleanup_deleted_user();

-- ---------------------------------------------------------------------------
-- Function permissions: signed-in users only; helpers not callable at all
-- ---------------------------------------------------------------------------
do $$
declare f record;
begin
  for f in
    select p.oid::regprocedure as sig, p.proname
    from pg_proc p where p.pronamespace = 'public'::regnamespace
  loop
    execute format('revoke all on function %s from public, anon', f.sig);
    if f.proname in ('admin_usage_stats','bw_create_group','bw_delete_my_account','bw_group_members_for_user',
                     'bw_join_group','bw_leave_group','bw_my_groups','bw_profile_icons_for_user','bw_public_groups',
                     'bw_require_caller','bw_set_event_interest','bw_set_profile_icon','bw_shared_happenings',
                     'bw_track_visit') then
      execute format('grant execute on function %s to authenticated', f.sig);
    else
      execute format('revoke all on function %s from authenticated', f.sig);
    end if;
  end loop;
end;
$$;
