-- v70: invite links show the group's real name.
-- The "Join X?" prompt used the name written into the link, so a link could
-- claim to be a friend's group while pointing at a stranger's. This returns
-- the real name and size, but only for a valid group id + PIN. Wrong guesses
-- count towards the same 5-per-15-minutes limit as bw_join_group.

create or replace function public.bw_invite_preview(p_group_id uuid, p_pin text)
returns table(name text, member_count int)
language plpgsql
security definer
set search_path = public
as $$
declare uid text := auth.uid()::text; gname text; stored_pin text;
begin
  if uid is null then raise exception 'Not authorised' using errcode = '42501'; end if;
  if (select count(*) from bw_join_attempts a
       where a.user_id = uid and a.attempted_at > now() - interval '15 minutes') >= 5 then
    return;
  end if;
  select g.name, g.join_pin into gname, stored_pin from bw_groups g where g.id = p_group_id;
  if gname is null or p_pin is null or p_pin <> stored_pin then
    insert into bw_join_attempts(user_id) values (uid);
    return;
  end if;
  return query select gname, (select count(*)::int from bw_group_members m where m.group_id = p_group_id);
end;
$$;

revoke all on function public.bw_invite_preview(uuid, text) from public, anon;
grant execute on function public.bw_invite_preview(uuid, text) to authenticated;

