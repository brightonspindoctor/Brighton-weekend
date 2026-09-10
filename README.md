# Brighton Weekend v30

Complete deployment package for the Brighton Weekend PWA.

## v30 changes
- Expanded the bundled event feed from 192 to 239 events, including newly verified Concorde 2, Quarters and Brighton Centre listings.
- Added the previously missing DJ Yoda — 6 Nov 2026 at Concorde 2.
- Added a community **Add an event** form inside Happenings.
- Community events are stored in Supabase and merged into the main event feed at runtime, so they appear on Discover/Comedy and can be used by the social layer.
- Users may choose one of the existing Brighton Weekend venues or **Other**; Other requires a venue name.
- Community events support date, start/finish time, category, price, ticket link and optional description.
- Community-added events are labelled in the feed.
- Service-worker cache bumped to v30.

## Supabase
Run both:
- `supabase-happenings-v29.sql` if v29 has not already been applied.
- `supabase-custom-events-v30.sql` to create the community event feed.

## Important architecture note
A static GitHub Pages app cannot let an anonymous phone browser physically rewrite the deployed `events.json` file. v30 therefore treats the Supabase `bw_custom_events` table as the writable extension to the main event file and merges those rows into the main event array at runtime. This gives the requested behaviour for all users without exposing a GitHub write token in the browser.

## Deploy
Upload the complete contents of this package to the root of the GitHub Pages repository.

## v31 repair notes
If Interested/Bought does not save, run `supabase-v31-repair.sql` once in Supabase SQL Editor. It restores the browser policies/grants on `event_interest` and creates the unique `(event_id,user_id)` key required by the app's upsert.

Happenings now has a prominent Add event launcher. Community events are stored in `bw_custom_events` and merged into the main feed at runtime. A community event using `Other` as its venue is visible regardless of the saved venue filter because there is no standard venue checkbox for Other.

## Recommended Supabase setup for v31
Use `supabase-v31-complete.sql` as the single migration. It includes the groups/functions, Happenings activity function, event_interest policies and unique key, and the community-events table/policies. You do not need to run the older v30/v31 SQL files if you run this complete migration successfully.
