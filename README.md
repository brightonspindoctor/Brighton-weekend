# Brighton Weekend v27

Large-scale stability/debugging release.

## Fixed
- Comedy tab now re-renders when moving between weekends with Previous, Next and Today.
- Venue filters now update Discover, Comedy and Happenings together.
- Local date handling no longer relies on UTC conversion for event-day keys.
- Comedy date range is explicitly Thursday–Sunday.
- Event feed refresh validates HTTP responses, removes duplicate IDs and ignores malformed events.
- Refresh button is protected against overlapping clicks.
- Added browser-console diagnostics for event-feed integrity.
- Service-worker cache bumped to v27.

## Included
- 192-event current six-month event feed dated 8 September 2026.
- PWA manifest and icons.
- Admin page.
- Supabase group SQL.

## Deployment
Replace the files in the GitHub Pages repository with this package.

## v28 Happenings change
Run `supabase-happenings-v28.sql` in the Supabase SQL editor. Happenings now includes your own Interested/Bought activity as well as activity from other members of your groups.
