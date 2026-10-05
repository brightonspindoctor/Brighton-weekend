-- ============================================================================
-- Brighton Weekend v58 — security and data fixes
-- Applied to the live project on 2026-10-05 (run in the SQL Editor).
-- Safe to re-run.
--
--   1. PIN guessing: a successful join no longer wipes the failed-attempt
--      counter. Before, someone could guess 4 PINs, rejoin a group of their own
--      to reset the counter, and repeat. Failed attempts now simply expire
--      after 15 minutes.
--   2. Leaving a group deletes it once nobody is left (as the privacy policy
--      says). Groups that are already empty are removed.
--   3. Community events: Old Albion is an allowed venue, matching the app.
--   4. Names shown to others come from the person's profile, not from
--      whatever the browser sends, and a name change updates them everywhere.
--   5. People can delete community events they added.
--   6. The 20-upcoming-events limit compares dates as text, so one badly
--      formed date can't block someone from adding events.
--   7. Removes a duplicate index on event_interest.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Helper: the signed-in caller's profile name (falls back to what was sent).
-- Only called from inside other functions, so nobody else can execute it.
-- ---------------------------------------------------------------------------
create or replace function public.bw_caller_name(p_fallback text)
returns text
language sql stable security definer set search_path = public
as $$
  select left(btrim(coalesce(
    (select p.display_name from public.bw_profiles p where p.user_id = auth.uid()),
    p_fallback, '')), 60);
$$;
revoke all on function public.bw_caller_name(text) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 1 + 4. Join a group
-- ---------------------------------------------------------------------------
create or replace function public.bw_join_group(
  p_user_id text, p_user_name text, p_group_id uuid, p_pin text, p_group_name text
)
returns table(ok boolean, message text)
language plpgsql security definer set search_path = public
as $$
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
$$;

-- ---------------------------------------------------------------------------
-- 4. Create a group (profile name for the creator)
-- ---------------------------------------------------------------------------
create or replace function public.bw_create_group(
  p_user_id text, p_user_name text, p_name text, p_is_private boolean
)
returns table(id uuid, name text, is_private boolean, join_pin text)
language plpgsql security definer set search_path = public
as $$
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
$$;

-- ---------------------------------------------------------------------------
-- 2. Leave a group; delete it if it is now empty
-- ---------------------------------------------------------------------------
create or replace function public.bw_leave_group(p_user_id text, p_group_id uuid)
returns table(ok boolean, message text)
language plpgsql security definer set search_path = public
as $$
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
$$;

delete from public.bw_groups g
where not exists (select 1 from public.bw_group_members m where m.group_id = g.id);

-- ---------------------------------------------------------------------------
-- 4. Interested / Going (profile name)
-- ---------------------------------------------------------------------------
create or replace function public.bw_set_event_interest(
  p_user_id text, p_user_name text, p_event_id text, p_status text
)
returns table(event_id text, user_id text, user_name text, status text)
language plpgsql security definer set search_path = public
as $$
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
$$;

-- ---------------------------------------------------------------------------
-- 4 + 6. Community events: profile name, and the upcoming-events limit
-- ---------------------------------------------------------------------------
create or replace function public.bw_custom_events_limit()
returns trigger
language plpgsql security definer set search_path = public
as $$
begin
  if (select count(*) from public.bw_custom_events e
       where e.created_by = new.created_by
         and e.date >= to_char(current_date, 'YYYY-MM-DD')) >= 20 then
    raise exception 'You''ve added the maximum of 20 upcoming events. Please try again once some have passed.';
  end if;
  new.created_by_name := public.bw_caller_name(new.created_by_name);
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- 4. A name change updates the name everywhere it is shown
-- ---------------------------------------------------------------------------
create or replace function public.bw_profiles_propagate_name()
returns trigger
language plpgsql security definer set search_path = public
as $$
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
$$;
revoke all on function public.bw_profiles_propagate_name() from public, anon, authenticated;

drop trigger if exists bw_profiles_propagate_name on public.bw_profiles;
create trigger bw_profiles_propagate_name
after update of display_name on public.bw_profiles
for each row execute function public.bw_profiles_propagate_name();

-- ---------------------------------------------------------------------------
-- 3. Allowed venues for community events (adds Old Albion)
-- ---------------------------------------------------------------------------
alter table public.bw_custom_events drop constraint if exists bw_custom_events_venue_allowed;
alter table public.bw_custom_events add constraint bw_custom_events_venue_allowed check (venue in (
  'Brighton Centre','Brighton Dome','CHALK','Concorde 2','The Old Market','Green Door Store',
  'Volks','Quarters','Patterns','DUST','Komedia','The Forge Comedy Club','Theatre Royal Brighton',
  'The Hope & Ruin','The Prince Albert','A L P H A B E T','The Pipeline','Brighton Racecourse',
  'The Gladstone','Babble','Old Albion','Amex Stadium','Shelter Hall','Other'
));

-- ---------------------------------------------------------------------------
-- 5. People can delete the community events they added
-- ---------------------------------------------------------------------------
grant delete on public.bw_custom_events to authenticated;
drop policy if exists "bw_custom_events_delete_own" on public.bw_custom_events;
create policy "bw_custom_events_delete_own"
on public.bw_custom_events for delete to authenticated
using (created_by = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- 7. event_interest had two identical unique indexes; keep one
-- ---------------------------------------------------------------------------
drop index if exists public.event_interest_unique_user_event;
