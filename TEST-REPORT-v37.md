# Brighton Weekend v37 Test Report

## Automated checks
- JavaScript extracted from both inline `<script>` blocks and checked with `node --check`: PASS
- `events.json` parsed with Python JSON parser: PASS
- `manifest.webmanifest` parsed with Python JSON parser: PASS
- Required auth UI markers present: PASS
- `persistSession:true` present in Supabase client: PASS
- `autoRefreshToken:true` present: PASS
- Magic-link `signInWithOtp` flow present: PASS
- Auth user UUID used by `uid()`: PASS
- Profile table migration includes UUID FK to `auth.users`: PASS
- Profile email unique index present: PASS
- Profile RLS policies restrict rows to `auth.uid()`: PASS
- No `sb_secret` or `service_role` key included: PASS
- Service worker cache bumped to v37: PASS

## Live test limitation
A real magic-link email delivery and authenticated Supabase session cannot be exercised from this build environment. The final live checks must be performed after running the SQL and configuring the Supabase Site URL/Redirect URL.

## Manual acceptance test
1. Open the GitHub Pages app in a fresh/private browser.
2. Enter an email and request a magic link.
3. Follow the link.
4. Enter a display name and join/create a group.
5. Close and reopen the app: it should remain signed in.
6. Go to Venues: signed-in email should be shown.
7. Click Sign out: app should return to email sign-in.
8. Sign back in with the same email: the same account/profile should load.
9. On a second browser/device, sign in with the same email: it should resolve to the same Supabase Auth user.
