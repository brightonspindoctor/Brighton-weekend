# Brighton Weekend v33 — test report

## Automated checks performed

- JavaScript extracted from `index.html` and checked with `node --check`.
- `events.json` parsed successfully and checked for duplicate IDs and invalid dates.
- `manifest.webmanifest` parsed successfully.
- ZIP/package integrity checked with `unzip -t` after packaging.
- Commitment code inspection confirms all three states use the single `bw_set_event_interest` RPC path.
- Commitment confirmation is now explicit: the UI does not accept the click as saved until the subsequent Supabase read shows the requested state.
- Bought/Interested counts include the current user's saved commitment as a fallback, so the user's own action cannot disappear from the count merely because the activity refresh is delayed.

## Database checks

The v33 SQL migration:

- creates/replaces `bw_set_event_interest`;
- validates allowed statuses;
- inserts or updates using the `(event_id,user_id)` unique key;
- deletes when the same selected button is clicked again;
- grants RPC execution to browser roles;
- ensures the read policy and unique index required by the app are present.

## Live-service limitation

A real browser-to-Supabase write could not be executed from the build environment because outbound DNS/network access to the Supabase project is unavailable here. Therefore this release is **not described as live-Supabase tested**. The app contains explicit post-write verification so any remaining permission/schema problem should surface as a visible error rather than silently pretending the click worked.
