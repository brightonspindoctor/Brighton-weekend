# Brighton Weekend v39 — Google Sign-In setup

## 1. Google Cloud

Create/select a Google Cloud project and configure the OAuth consent screen / Google Auth Platform.

Create an OAuth Client ID with application type **Web application**.

### Authorized JavaScript origin

```text
https://brightonspindoctor.github.io
```

### Authorized redirect URI

```text
https://zqvccsnfrkrtcsitfwcd.supabase.co/auth/v1/callback
```

Copy the Google **Client ID** and **Client Secret**.

## 2. Supabase

Open:

**Authentication → Providers → Google**

Enable Google and paste the Google Client ID and Client Secret.

Then open:

**Authentication → URL Configuration**

Set Site URL to:

```text
https://brightonspindoctor.github.io/Brighton-weekend/
```

Add this to Redirect URLs:

```text
https://brightonspindoctor.github.io/Brighton-weekend/
```

Save.

## 3. No new SQL migration is required for Google sign-in

The existing v37 profile SQL remains valid. Google Auth supplies the persistent Supabase user ID and email; the app stores the user's chosen display name in `bw_profiles`.

## 4. Test

1. Deploy v39.
2. Open the production GitHub Pages URL.
3. Click **Continue with Google**.
4. Choose a Google account.
5. Approve the requested permissions.
6. You should return to Brighton Weekend.
7. Enter your display name if prompted.
8. Close/reopen the app. The Supabase session should remain active.
9. Sign out and confirm that the Google sign-in screen is shown again.

The app uses an explicit production `redirectTo` URL and does not use the old email magic-link flow.
