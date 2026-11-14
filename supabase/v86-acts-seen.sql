-- v86: "I saw them" ticks on festival line-ups (14 November 2026).
--
-- Once a festival has started, signed-in users can tick the acts they saw on
-- its opened card. Each tick is one row: who, which festival (its id from
-- festivals.json) and the act's name as written in festival-headliners.json.
-- Only the person who ticked can read or change their ticks; nobody else sees
-- them. Rows go with the account (on delete cascade). Safe to run more than once.

create table if not exists public.bw_acts_seen (
  user_id uuid not null references auth.users(id) on delete cascade,
  festival_id text not null,
  act text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, festival_id, act),
  constraint bw_acts_seen_festival_id check (festival_id like 'festival:%' and char_length(festival_id) <= 300),
  constraint bw_acts_seen_act_length check (char_length(btrim(act)) between 1 and 200)
);
alter table public.bw_acts_seen enable row level security;
-- No direct table access: reads and writes go through the functions below.
revoke all on public.bw_acts_seen from public, anon, authenticated;

-- Tick (p_seen true) or untick an act. At most 3,000 ticks per person.
create or replace function public.bw_set_act_seen(p_festival_id text, p_act text, p_seen boolean)
 returns void
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'Not authorised'; end if;
  if p_festival_id is null or p_festival_id not like 'festival:%' or char_length(p_festival_id) > 300 then
    raise exception 'Festival ID is required';
  end if;
  if p_act is null or char_length(btrim(p_act)) not between 1 and 200 then
    raise exception 'Act is required';
  end if;
  if not coalesce(p_seen, false) then
    delete from public.bw_acts_seen where user_id = me and festival_id = p_festival_id and act = p_act;
    return;
  end if;
  if (select count(*) from public.bw_acts_seen where user_id = me) >= 3000 then
    raise exception 'Too many ticks';
  end if;
  insert into public.bw_acts_seen (user_id, festival_id, act)
  values (me, p_festival_id, p_act)
  on conflict do nothing;
end;
$function$;
revoke all on function public.bw_set_act_seen(text,text,boolean) from public, anon;
grant execute on function public.bw_set_act_seen(text,text,boolean) to authenticated;

-- The caller's own ticks.
create or replace function public.bw_my_acts_seen()
 returns table(festival_id text, act text)
 language sql
 stable
 security definer
 set search_path to 'public'
as $function$
  select s.festival_id, s.act from public.bw_acts_seen s where s.user_id = auth.uid();
$function$;
revoke all on function public.bw_my_acts_seen() from public, anon;
grant execute on function public.bw_my_acts_seen() to authenticated;
