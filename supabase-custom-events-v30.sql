-- Brighton Weekend v30 — community-added events
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

create policy "bw_custom_events_read"
on public.bw_custom_events for select to anon, authenticated using (true);

create policy "bw_custom_events_insert"
on public.bw_custom_events for insert to anon, authenticated with check (true);

grant select, insert on public.bw_custom_events to anon, authenticated;
