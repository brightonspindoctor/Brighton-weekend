# Brighton Weekend v32

This is a complete deployment package.

## Important
Use the Supabase SQL from the previous v31 setup (`supabase-v31-complete.sql` or `supabase-v31-repair.sql`) if it has not already been run. v32 does not require a new database migration for the commitment fix.

## Main v32 fix
The Bought/Interested action had regressed because v31 attempted to perform an upsert by sending a POST request with `on_conflict` in the URL. Supabase's documented JavaScript API treats upsert as a distinct operation. v32 returns to explicit INSERT/PATCH/DELETE operations against the existing unique `(event_id,user_id)` constraint.

## Community events
Community events remain stored in `bw_custom_events`. Events using the standard venue list appear normally; events using `Other` are now also included in the main feed and display their entered venue name.
