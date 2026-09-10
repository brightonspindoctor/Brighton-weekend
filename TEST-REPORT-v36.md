# Brighton Weekend v36 test report

## Root cause fixed
The v35 RPC still contained `ON CONFLICT (event_id, user_id)`. Because the RPC uses `RETURNS TABLE(event_id text, user_id text, ...)`, those names are also PL/pgSQL output variables. PostgreSQL can therefore report 42702 ambiguous_column.

## v36 fix
Replaced the ambiguous ON CONFLICT path with an explicitly qualified UPDATE followed by INSERT when no row was found. The return query remains explicitly qualified with `ei.`.

## Static tests
- JavaScript extracted and checked with Node `--check`: PASS
- events.json parsed: PASS
- manifest.webmanifest parsed: PASS
- ZIP integrity: PASS
- Searched commitment SQL for unqualified `ON CONFLICT (event_id, user_id)`: PASS (absent)
- Confirmed RPC call parameters in index.html match v36 function signature: PASS
- Confirmed Happenings RPC includes all group members and statuses interested/ticket_bought: PASS

## Live-test limitation
A live write against the user's Supabase project cannot be executed from this build environment. The app now surfaces the actual RPC error if the live database function has not been updated.
