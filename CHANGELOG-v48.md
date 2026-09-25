# Brighton Weekend v48

## Security (run `supabase/v48-security-hardening.sql` in Supabase)
- Database functions now act only for the signed-in user; anonymous access removed.
- `event_interest`: users read only their own rows; open insert/update/delete policies removed.
- Community events: signed-in users only, `created_by` must be the caller, ticket links must be http(s).
- App: ticket links are checked before being shown (blocks `javascript:` links); event ids are no longer injected into inline `onclick` code.

## Bugs fixed
- On Saturdays and Sundays "This week" jumped to the following week.
- The service worker rewrote `index.html` to add Search and day filters; opening Search then another tab showed both. These features now live in the app; `sw.js` only caches.
- Community events failed for 10 of the 23 venues in the form (database venue list was out of date).
- 237 titles had the listing date and doors time appended; 200 events showed doors time as the finish time. Data cleaned and scraper fixed.
- Sessions of the same show on one day (e.g. 10:00 and 11:00) could be merged into one; start time is now part of an event's identity.
- Signed-in users re-ran setup on every hourly token refresh.
- Past events stayed in Happenings and Search; past days cluttered the current week.
- Commitment buttons wrapped onto two lines on phones; stray `</div>`; theme colour mismatch.

## Design
- Eight stacked stylesheets (three colour schemes, heavy `!important`) replaced by `css/app.css`, driven by tokens.
- `DESIGN-SYSTEM.md` and `design-system.html` added.

## Files moved or removed — delete these from GitHub
If you upload through the GitHub website, old files are not deleted automatically. Remove:

- `head.txt`, `.github/ui-fix-trigger.txt`
- `CHANGELOG-v26.txt` … `CHANGELOG-v34.txt` (now in `docs/archive/`)
- `TEST-REPORT-v33.md` … `TEST-REPORT-v41.md` (now in `docs/archive/`)
- `README-v37.md`, `README-v38.md`, `DESIGN-SYSTEM-v41.md`, `LOGO-FIX-v43.md`, `LOGO-SETTINGS-v44.md`, `EVENT-DATA-SOURCES-v30.md`, `EVENT-DATA-SOURCES-v46.md` (now in `docs/archive/`)
- `EVENT-DATA-SOURCES-v47.md` → `docs/EVENT-DATA-SOURCES.md`
- `GOOGLE-SETUP-v39.md` → `docs/GOOGLE-SETUP.md`
- `GOOGLE-BRANDING-v40.md` → `docs/GOOGLE-BRANDING.md`
- `AVATAR_CREATION.md` → `docs/AVATAR_CREATION.md`
- All 12 root `supabase-*.sql` files (now in `supabase/archive/`)
