# Brighton Weekend v38 — Magic-link redirect fix

## Fix
The magic-link redirect is now explicitly hard-coded to the production GitHub Pages URL rather than using the browser origin. This prevents development/localhost URLs from being embedded in authentication requests.

## Supabase URL Configuration — required once
In Supabase Dashboard → Authentication → URL Configuration:
- Site URL: `https://brightonspindoctor.github.io/Brighton-weekend/`
- Redirect URL: `https://brightonspindoctor.github.io/Brighton-weekend/`

If the Site URL is still `http://localhost:3000` (or another localhost URL), Supabase may continue to generate authentication links that return to localhost. Supabase requires the requested redirect URL to be on the allowed Redirect URLs list.

## Testing
- JavaScript syntax checked with Node.
- Production redirect URL is present in the source.
- No localhost URL remains in the app source.
- Service-worker cache bumped to v38.
