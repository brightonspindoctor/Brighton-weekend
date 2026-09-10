# Brighton Weekend v36

## Bought + Happenings fix

v36 fixes the v35 PostgreSQL return-type regression. The existing `bw_set_event_interest` and `bw_shared_happenings` return column names/types are preserved, so the functions can be replaced without dropping them. All column references inside the functions are qualified with table aliases.

Run **supabase-v36-bought-happenings.sql** once in Supabase SQL Editor. Do not run the v33/v35 commitment SQL afterwards.

Expected behaviour:
- Bought increases the event's Bought count by one for the current user.
- Interested does the same for Interested.
- The current user's activity appears in Happenings when they are a member of a group.
- Changing Interested/Bought updates the same commitment rather than creating a second row.
- Clicking the selected status again removes the commitment.

## Validation
The release was statically validated for JavaScript syntax, JSON/manifest parsing, required RPC names, function signatures, and ZIP integrity. A live write against the user's Supabase project cannot be executed from this environment, so the final production write must be tested in the deployed app.

## v39 Google authentication

v39 replaces email magic-link sign-in with Google OAuth. Configure the Google provider in Supabase and Google Cloud using `GOOGLE-SETUP-v39.md`. No new SQL migration is required for the authentication change.
