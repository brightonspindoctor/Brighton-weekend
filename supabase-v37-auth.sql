-- Brighton Weekend v37: email identity + persistent passwordless login
-- Run once in Supabase SQL Editor.

create table if not exists public.bw_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  display_name text not null check (char_length(trim(display_name)) between 1 and 40),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists bw_profiles_email_unique on public.bw_profiles(lower(email));

alter table public.bw_profiles enable row level security;

drop policy if exists "bw_profiles_select_own" on public.bw_profiles;
drop policy if exists "bw_profiles_insert_own" on public.bw_profiles;
drop policy if exists "bw_profiles_update_own" on public.bw_profiles;

create policy "bw_profiles_select_own" on public.bw_profiles
  for select to authenticated using (auth.uid() = user_id);
create policy "bw_profiles_insert_own" on public.bw_profiles
  for insert to authenticated with check (auth.uid() = user_id and lower(email) = lower(coalesce(auth.jwt()->>'email','')));
create policy "bw_profiles_update_own" on public.bw_profiles
  for update to authenticated using (auth.uid() = user_id)
  with check (auth.uid() = user_id and lower(email) = lower(coalesce(auth.jwt()->>'email','')));

grant select, insert, update on public.bw_profiles to authenticated;

-- Keep updated_at current.
create or replace function public.bw_profiles_touch_updated_at()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists bw_profiles_touch_updated_at on public.bw_profiles;
create trigger bw_profiles_touch_updated_at
before update on public.bw_profiles
for each row execute function public.bw_profiles_touch_updated_at();

-- Optional: prevent anonymous/public database use for profile rows.
revoke all on public.bw_profiles from anon;
