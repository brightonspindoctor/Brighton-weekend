# Google sign-in

Accounts are Supabase Auth users. People sign in with Google, or with a link
and code sent to their email address. The app asks Supabase to return to the
address it was opened from, so nothing in `index.html` names the domain.

## Google Cloud (Google Auth Platform)

- OAuth client type: **Web application**.
- Authorised redirect URI, which must not change:
  `https://zqvccsnfrkrtcsitfwcd.supabase.co/auth/v1/callback`
- The client ID and secret go into Supabase → Authentication → Providers →
  Google.

## Supabase → Authentication → URL Configuration

- Site URL: `https://brightonweekend.co.uk/`
- Redirect URLs: `https://brightonweekend.co.uk/` (add any other address the
  app is opened from, such as a test copy).

## Branding (Google Auth Platform → Branding)

| Field | Value |
|---|---|
| App name | Brighton Weekend |
| App logo | `icons/icon-120.png` (120×120) |
| Home page | `https://brightonweekend.co.uk/` |
| Privacy policy | `https://brightonweekend.co.uk/privacy.html` |
| Terms of service | `https://brightonweekend.co.uk/terms.html` |
| Authorised domain | `brightonweekend.co.uk` |

Google verifies that the domain is yours through Google Search Console, which
reads `google64271ac436a68466.html` in the site's root: keep that file. After
saving the branding, use **Verify branding**, then **Publish branding**.

## Checking it works

1. Open the live site in a private window and choose **Continue with Google**.
2. Pick an account and approve: you come back to Brighton Weekend and, the
   first time, are asked for a display name.
3. Close and reopen the app: you are still signed in.
4. Settings → Sign out shows the app as a guest again.
