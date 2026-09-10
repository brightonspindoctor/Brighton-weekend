# Brighton Weekend v37 — Email Identity & Persistent Login

## What changed
- Added Supabase Auth passwordless email magic-link sign-in.
- Users are identified by their Supabase Auth UUID instead of a browser-generated ID.
- One email address maps to one Supabase Auth user.
- Sessions persist in the browser/PWA, so users normally stay signed in between launches.
- Added a private `bw_profiles` table for the display name associated with the authenticated user.
- Existing groups, Bought/Interested activity, Happenings and community events continue to use the authenticated user's UUID string as `user_id`.
- Added Sign out and displays the signed-in email under Venues.
- Bumped the service-worker cache to v37.

## Supabase setup
Run `supabase-v37-auth.sql` once in Supabase SQL Editor.

Then in Supabase Dashboard:
1. Authentication → Providers → Email: ensure Email provider is enabled.
2. Authentication → URL Configuration → Site URL: set to the GitHub Pages URL, e.g. `https://brightonspindoctor.github.io/Brighton-weekend/`.
3. Add the same GitHub Pages URL as an allowed Redirect URL if it is not already present.

Magic links are sent by Supabase Auth. Supabase's default browser client persists sessions, so users do not have to sign in each time they open the app.

## Important
Do not put a Supabase secret/service-role key into this repository. The app only contains the publishable browser key.
