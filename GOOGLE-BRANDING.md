# Brighton Weekend — Google branding / verification setup

## Public pages added

- Homepage: `https://brightonspindoctor.github.io/Brighton-weekend/`
- About: `https://brightonspindoctor.github.io/Brighton-weekend/about.html`
- Privacy: `https://brightonspindoctor.github.io/Brighton-weekend/privacy.html`
- Terms: `https://brightonspindoctor.github.io/Brighton-weekend/terms.html`

The public welcome screen now includes a short description of Brighton Weekend and direct links to Privacy and Terms, so the homepage is not just a login screen.

## Google Branding page

Use:

- App name: `Brighton Weekend`
- Application home page: `https://brightonspindoctor.github.io/Brighton-weekend/`
- Application privacy policy: `https://brightonspindoctor.github.io/Brighton-weekend/privacy.html`
- Terms of service: `https://brightonspindoctor.github.io/Brighton-weekend/terms.html`
- Authorized domain: `brightonspindoctor.github.io`
- App logo: `icons/google-logo-120.png` (or the copy supplied in the release root)

## Important domain-verification point

Google's current branding-verification requirements say that domains associated with the homepage, privacy policy, terms, JavaScript origins and redirect URIs must be verified. A GitHub Pages URL uses `brightonspindoctor.github.io`, which is a subdomain of `github.io`; Google may require a domain/property that you can actually verify as yours. If Search Console will not let the Google Cloud project verify `brightonspindoctor.github.io`, this is the blocker — the pages themselves are not the problem.

Do not change the Supabase callback URL. It remains:
`https://zqvccsnfrkrtcsitfwcd.supabase.co/auth/v1/callback`

## After the pages are live

1. Open Google Cloud → Google Auth Platform → Branding.
2. Enter the URLs above.
3. Upload the 120×120 Brighton Weekend logo.
4. Save the branding.
5. Verify the authorised domain in Google Search Console if Google requests it.
6. Click **Verify Branding**.
7. If Google reports **Ready to publish**, click **Publish branding**.

The Google OAuth client and Supabase Google provider do not need to be recreated for these page changes.
