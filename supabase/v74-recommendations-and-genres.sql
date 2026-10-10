-- v74: recommendations ("You might like") and community genres.
--
-- 1. Each Interested/Going choice now keeps the event's title and genre, so the
--    app still knows which bands and genres someone liked after the event has
--    passed and dropped out of events.json. Choices saved before v74 have none.
-- 2. Signed-in users can add a genre to a music or club event that has none,
--    from the app's fixed list. Everyone (guests included) sees the genre most
--    people picked; ties go to the earliest pick.

-- 1. Title and genre on commitments ------------------------------------------
alter table public.event_interest add column if not exists event_title text;
alter table public.event_interest add column if not exists event_genre text;
alter table public.event_interest drop constraint if exists event_interest_event_title_length;
alter table public.event_interest add constraint event_interest_event_title_length check (event_title is null or char_length(event_title) <= 200);
alter table public.event_interest drop constraint if exists event_interest_event_genre_length;
alter table public.event_interest add constraint event_interest_event_genre_length check (event_genre is null or char_length(event_genre) <= 40);

-- The two new arguments default to null, so older copies of the app that send
-- only four arguments keep working.
drop function if exists public.bw_set_event_interest(text,text,text,text);
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

-- 2. Community genres ---------------------------------------------------------
-- Keep the genre list in step with GENRE_ORDER in index.html.
create table if not exists public.bw_event_genres (
  event_id text not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  genre text not null,
  created_at timestamptz not null default now(),
  primary key (event_id, user_id),
  constraint bw_event_genres_event_id_length check (char_length(event_id) <= 300),
  constraint bw_event_genres_genre_allowed check (genre in (
    'Indie & Rock','Pop','Electronic','House & Disco','Techno & Trance','Drum & Bass',
    'Garage & Bass','Hip-hop & R&B','Latin & Afrobeats','Jazz, Soul & Funk',
    'Folk & Country','Punk & Metal','Reggae & Ska','Classical'))
);
alter table public.bw_event_genres enable row level security;
-- No direct table access: reads and writes go through the functions below.
revoke all on public.bw_event_genres from public, anon, authenticated;

-- Set, change or (with p_genre null) remove my genre for an event.
create or replace function public.bw_set_event_genre(p_event_id text, p_genre text)
 returns void
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
begin
  if auth.uid() is null then raise exception 'Not authorised'; end if;
  if p_event_id is null or btrim(p_event_id) = '' or char_length(p_event_id) > 300 then
    raise exception 'Event ID is required';
  end if;
  if p_genre is null then
    delete from public.bw_event_genres where event_id = p_event_id and user_id = auth.uid();
    return;
  end if;
  insert into public.bw_event_genres (event_id, user_id, genre)
  values (p_event_id, auth.uid(), p_genre)
  on conflict (event_id, user_id) do update set genre = excluded.genre, created_at = now();
end;
$function$;
revoke all on function public.bw_set_event_genre(text,text) from public, anon;
grant execute on function public.bw_set_event_genre(text,text) to authenticated;

-- The winning genre per event, plus the caller's own pick (null for guests).
create or replace function public.bw_community_genres()
 returns table(event_id text, genre text, my_genre text)
 language sql
 stable
 security definer
 set search_path to 'public'
as $function$
  with counts as (
    select g.event_id, g.genre, count(*) as n, min(g.created_at) as first_at
    from public.bw_event_genres g
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
