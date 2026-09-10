# Brighton Weekend v34 test report

## Static tests performed
- JavaScript source extracted from `index.html` and checked with Node.js syntax checking: PASS.
- `events.json` parsed successfully: PASS (239 events).
- `manifest.webmanifest` parsed successfully: PASS.
- ZIP archive integrity checked after packaging: PASS.
- Commitment path inspected end-to-end: `act()` -> `bw_set_event_interest` RPC -> `loadAttendance()` -> save verification -> `bw_shared_happenings` -> `renderAll()`.

## Root cause fixed
The v33 PL/pgSQL function declared output columns named `event_id`, `user_id`, etc. Those names became PL/pgSQL variables. The statement `ON CONFLICT (event_id,user_id)` therefore produced PostgreSQL error 42702 because `event_id` could refer to the output variable or the table column.

v34 removes the ambiguity in two ways:
1. The function output columns are renamed to `result_event_id`, `result_user_id`, `result_user_name`, and `result_status`.
2. Table columns are explicitly qualified (`ei.event_id`, `ei.user_id`) and the upsert uses `ON CONFLICT DO UPDATE` without an ambiguous conflict-column list.

The Happenings function is also given unambiguous output names and explicit table aliases.

## Live-database limitation
A real write to the user's hosted Supabase project cannot be executed from this build environment. Therefore no claim of live production testing is made. The SQL was statically reviewed and the client-side request/verification path was checked. After running the v34 SQL in Supabase, the first real Bought click should be the live integration test.
