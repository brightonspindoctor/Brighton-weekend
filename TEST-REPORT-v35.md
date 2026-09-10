# v36 Test Report

- JavaScript syntax: PASS
- events.json JSON parse: PASS
- manifest JSON parse: PASS
- `bw_set_event_interest` signature preserved as `(text,text,text,text) returns table(event_id text,user_id text,user_name text,status text)`: PASS
- `bw_shared_happenings` signature preserved as `(text) returns table(group_id uuid,group_name text,event_id text,user_id text,user_name text,status text)`: PASS
- No ambiguous unqualified `event_id` references in the two repaired functions: PASS
- Happenings includes current user through group membership join: PASS (static SQL inspection)
- ZIP integrity: PASS
- Live Supabase write: NOT RUN (environment has no authenticated/live project access)
