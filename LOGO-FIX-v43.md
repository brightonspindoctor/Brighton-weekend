# Brighton Weekend v43 — dark theme and logo fix

This release keeps the darker v42 visual system and hardens branding/PWA asset loading for the GitHub Pages project URL.

## Logo fixes
- Visible app logos use absolute GitHub Pages URLs.
- Manifest icon URLs are absolute and cache-busted.
- Manifest `id`, `start_url`, and `scope` are absolute to the project site.
- Added root `favicon.ico`.
- Added explicit Apple touch icon and PNG favicon references.
- Service worker cache is v43 and registration uses `updateViaCache: 'none'`.

Project URL: https://brightonspindoctor.github.io/Brighton-weekend/
