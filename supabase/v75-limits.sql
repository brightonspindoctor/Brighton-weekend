-- v75: limits on community genres and saved choices.
--
-- Before this, a signed-in account could save a genre or an Interested/Going
-- choice against any made-up event id, as often as it liked. Genre picks are
-- sent to every visitor (guests included), so one account flooding the table
-- would have slowed the app for everyone.
--
-- 1. Event ids must look like a real one: a listed event (2026-10-11-...),
--    a festival (festival:...) or a community event (its uuid).
-- 2. Genre picks: up to 100 a day per person, only for listed or community
--    events, and only upcoming events' genres are sent to the app.
-- 3. Saved choices: up to 3,000 per person.
-- Safe to run more than once.

create or replace function public.bw_valid_event_id(p_event_id text, p_allow_festival boolean default true)
 returns boolean
 language sql
 immutable
 set search_path to 'public'
as $function$
  select coalesce(
       p_event_id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+$'
    or p_event_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    or (p_allow_festival and p_event_id ~ '^festival:[a-z0-9:-]+$'), false);
$function$;
revoke all on function public.bw_valid_event_id(text, boolean) from public, anon, authenticated;

create or replace function public.bw_set_event_genre(p_event_id text, p_genre text)
 returns void
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
begin
  if auth.uid() is null then raise exception 'Not authorised'; end if;
  if p_event_id is null or not public.bw_valid_event_id(p_event_id, false) then
    raise exception 'That event can''t have a genre.';
  end if;
  if p_genre is null then
    delete from public.bw_event_genres where event_id = p_event_id and user_id = auth.uid();
    return;
  end if;
  if (select count(*) from public.bw_event_genres g
       where g.user_id = auth.uid() and g.created_at > now() - interval '1 day') >= 100 then
    raise exception 'You''ve added a lot of genres today. Please try again tomorrow.';
  end if;
  insert into public.bw_event_genres (event_id, user_id, genre)
  values (p_event_id, auth.uid(), p_genre)
  on conflict (event_id, user_id) do update set genre = excluded.genre, created_at = now();
end;
$function$;
revoke all on function public.bw_set_event_genre(text,text) from public, anon;
grant execute on function public.bw_set_event_genre(text,text) to authenticated;

-- Only upcoming events' genres (from yesterday, so late-night events keep theirs).
create or replace function public.bw_community_genres()
 returns table(event_id text, genre text, my_genre text)
 language sql
 stable
 security definer
 set search_path to 'public'
as $function$
  with since as (
    select to_char((now() at time zone 'Europe/London')::date - 1, 'YYYY-MM-DD') as d
  ), counts as (
    select g.event_id, g.genre, count(*) as n, min(g.created_at) as first_at
    from public.bw_event_genres g, since
    where (g.event_id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}-' and left(g.event_id, 10) >= since.d)
       or exists (select 1 from public.bw_custom_events c where c.id::text = g.event_id and c.date >= since.d)
    group by g.event_id, g.genre
  ), ranked as (
    select c.event_id, c.genre,
           row_number() over (partition by c.event_id order by c.n desc, c.first_at asc) as rk
    from counts c
  )
  select r.event_id, r.genre,
         (select m.genre from public.bw_event_genres m where m.event_id = r.event_id and m.user_id = auth.uid())
  from ranked r
  where r.rk = 1;
$function$;
revoke all on function public.bw_community_genres() from public;
grant execute on function public.bw_community_genres() to anon, authenticated;

create or replace function public.bw_set_event_interest(
  p_user_id text, p_user_name text, p_event_id text, p_status text,
  p_event_title text default null, p_event_genre text default null)
 returns table(event_id text, user_id text, user_name text, status text, event_title text, event_genre text)
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
declare nm text; t text; g text;
begin
  perform public.bw_require_caller(p_user_id);
  if p_event_id is null or btrim(p_event_id) = '' then
    raise exception 'Event ID is required';
  end if;
  if p_status is not null and p_status not in ('not_interested','interested','ticket_bought') then
    raise exception 'Invalid commitment status';
  end if;
  -- Removing a choice works for any id (so old ones can be tidied); saving one
  -- needs a real-looking event id.
  if p_status is not null and not public.bw_valid_event_id(p_event_id) then
    raise exception 'That event isn''t recognised.';
  end if;
  nm := public.bw_caller_name(p_user_name);
  t := nullif(left(btrim(coalesce(p_event_title,'')),200),'');
  g := nullif(left(btrim(coalesce(p_event_genre,'')),40),'');

  if p_status is null then
    delete from public.event_interest as ei
    where ei.event_id = p_event_id and ei.user_id = p_user_id;
  else
    update public.event_interest as ei
       set user_name = nm, status = p_status,
           event_title = coalesce(t, ei.event_title),
           event_genre = coalesce(g, ei.event_genre)
     where ei.event_id = p_event_id and ei.user_id = p_user_id;
    if not found then
      if (select count(*) from public.event_interest e2 where e2.user_id = p_user_id) >= 3000 then
        raise exception 'You''ve saved a lot of choices. Please remove some old ones first.';
      end if;
      insert into public.event_interest as ei (event_id, user_id, user_name, status, event_title, event_genre)
      values (p_event_id, p_user_id, nm, p_status, t, g);
    end if;
  end if;

  return query
  select ei.event_id, ei.user_id, ei.user_name, ei.status, ei.event_title, ei.event_genre
  from public.event_interest as ei
  where ei.event_id = p_event_id and ei.user_id = p_user_id;
end;
$function$;
revoke all on function public.bw_set_event_interest(text,text,text,text,text,text) from public, anon;
grant execute on function public.bw_set_event_interest(text,text,text,text,text,text) to authenticated;
