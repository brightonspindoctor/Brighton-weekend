# Brighton Weekend

A mobile web app for finding gigs, comedy, club nights and theatre in Brighton
& Hove, and making plans with friends. It lives at
<https://brightonweekend.co.uk> (GitHub Pages) and can be installed to a
phone's home screen.

## What it does

- **Discover:** this week's events (Monday–Sunday) at the venues you follow,
  day by day, with quick chips for *Tonight* (from 5pm), *This weekend* (Friday to
  Sunday) and *Next 7 days*. New events since your last visit show as a one-line
  summary you can open. Tapping a promoter's sticker shows only their gigs.
- **Not music:** works like Festivals: choose Comedy, Theatre & musicals, Board
  games, Pub quizzes, Pub events or Other, and every upcoming event of that type
  is listed in date order at any venue (the venues in Settings only shape
  Discover). Anything listed here is left off Discover. Theatre & musicals takes
  plays, musicals and dance; workshops, courses and kids' shows go under Other.
  Theatre Royal, The Old Market and Brighton Dome label each show themselves, and
  their label decides (`venue_label`). Elsewhere, outside Theatre Royal's and
  Komedia's own programmes, an event needs a clear sign in its title that it isn't a gig
  (`notMusicKind` in `index.html`). Board games also takes every listing from
  The Dice & Meeple, Brighton Pub Boardgamers and Dice Saloon (Dice Saloon's
  kids' club goes under Other). Ghost walks and ghost tours are left out.
- **Event cards:** Get tickets up front; Add to calendar, Share and Add a genre
  sit behind the ⋯ button. Friends' counts show only when someone's interested or
  going. Listing markers such as "\*\*FREE ENTRY\*\*" become badges ("Free",
  "Extra show") and titles written in capitals are tidied (`scripts/prepare-events.py`).
- **Festivals:** a separate UK festival feed through the end of the next calendar year,
  with a Brighton location filter and festival-type filters. Festivals never enter the
  normal event feed, but can still be marked Interested or Going and appear in Happenings.
  A festival stays listed until its last day, so multi-week ones show while they're on.
- **Search:** by dates and venues (starting on this weekend at the venues you
  follow), artist, promoter or festival.
- **Commitments:** mark any event *Not for me*, *Interested* or *Going*.
- **Guests:** anyone can browse without a login. Marking events, Happenings and
  adding events ask for a free login, and the app carries out what they tried
  once they've signed up.
- **Groups and Happenings:** every group has a PIN (6 digits for groups made
  from v80 on, 3 for older ones); invite links carry it. Each group accepts at
  most 10 wrong PINs a day. Happenings shows what people in your groups are interested in or going to,
  with the list of people in your groups at the bottom.
- **You might like:** the top of Happenings suggests up to three events in the
  next six months by the same bands, or in the same genres, as things you've
  marked Interested or Going. Bands are matched on the title; genres only when
  both events have a known genre. *Not for me* on a suggestion stops that act
  being suggested again. Shuffled each time the app is opened; hidden when
  nothing matches. Shown even if you're not in a group.
- **Community genres:** a music or club night with no genre has *Add a genre*
  in its ⋯ menu. Signed-in users pick from the fixed genre list
  (`GENRE_ORDER`); the most-picked genre shows for everyone. Genres from the
  listings or the tagger always win.
- **Community events:** signed-in users can add events that are missing.
  Anyone can report one from its ⋯ menu; reports go to the admin page, where
  the event can be removed (Online Safety Act; records and review dates are in
  the online safety records doc in the project).
- **Settings:** venues and days, colour scheme (*Seafront after dark* or
  *Seafront by day*), profile icon, groups, privacy (*Count my visits*: off
  means no guest ID and no visit or ticket-tap counting from that device),
  account, install the app.
- **Messages:** confirmations and errors use in-app toasts and dialogs, not the
  browser's pop-ups. The Welcome back screen only appears when friends have new
  plans or someone joined a group; the groups step is shown once at sign-up.

## How it's built

| Part | Where |
|---|---|
| The app | `index.html`, one self-contained file: markup, styles (`<style id="bw-styles">`) and logic (`<script id="bw-app">`) |
| Design system | `DESIGN-SYSTEM.md`; `design-system.html` renders every token and component with the app's live stylesheet |
| Event and other pages | `e/<id>/` (with `event.ics`), `this-weekend/`, `tonight/`, `gigs/`, `comedy/`, `club-nights/`, `theatre/`, `venues/` and `sitemap.xml`, built daily by `scripts/build-event-pages.py`, which also writes `pages.css`. `about.html`, `privacy.html`, `terms.html` and `404.html` use the same stylesheet |
| Avatars | `profile-icons/` (the chosen artwork) → `profile-icons/standardized/` (what the app shows), built by `scripts/standardize-avatars.mjs`. See `AVATAR_CREATION.md` |
| Offline caching | `sw.js` (caching only; it doesn't change the page) |
| Sign-in, groups, commitments | Supabase (Google, or an email link and code). Setup: `GOOGLE-SIGN-IN.md` |
| Database definition | `supabase/` (see below) |
| Supabase client library | `vendor/supabase-js-2.117.2.js`, a pinned copy served from this site (no CDN). To upgrade, replace the file and update the filename in `index.html`, `admin.html` and `sw.js` |
| Font | `fonts/plus-jakarta-sans-latin.woff2`, served from this site |
| Event listings | `events.json`, generated by the scrapers below |
| Festival listings | `festivals.json`, generated daily from Fezzy with eFestivals as a secondary discovery source |
| Usage dashboard | `admin.html`: users, guests, avatar switches, Get tickets taps and app installs (v78: the browser's `appinstalled` event on Android and computers; on iPhones and iPads the first open from the home screen) |

## Event data

`.github/workflows/weekly-events.yml` refreshes the listings **once a day**,
normally soon after 01:17 (Europe/London), with backup start times at 05:17,
09:17 and 13:17 because GitHub sometimes starts scheduled runs hours late (a
backup run stops straight away if the day's refresh is done). It also runs on
manual dispatch and whenever a scraper file changes on `main`. It runs:

1. `scripts/scrape-events.py`: the venue websites in `event-sources.json`
   (structured Event data first, visible event cards as a fallback). Komedia's
   listings are filed by Komedia's own booking feed (Ticketsolve), which says
   whether each show is comedy, music, a club night or a kids' show.
2. `scripts/scrape-discovery.py`: Visit Brighton, Eventbrite, Ticketmaster,
   Skiddle, Rival Cults and the promoters, filtered back to known venues.
3. `scripts/prepare-events.py`: cleans titles, normalises times to HH:MM,
   drops doors times posing as finish times, removes headings and buttons read
   as events (`scripts/listing_rules.py`, shared with the scrapers and the
   validator), applies `excluded-events.json`, leaves out Patterns' recurring
   nights and merges duplicates: the same show from two sources, two listings
   sharing one show's ticket link, and Brighton Dome's comedy festival listings
   of shows that are on at Komedia. Talks the
   listing filed as something else are filed as Talk when the title says so
   ("In Conversation", "Q&A", "Interview", "Podcast", "Book Tour"), so they
   show under Not music → Other (or Pub events at a pub).
4. `scripts/check-tickets.py`: follows each event's ticket link as close to
   buying as it can (a listing page → the event's card → its booking button →
   the seller, at most three steps) and marks shows **Sold out** only when a
   page says so: the seller's structured data gives every ticket type as sold
   out (on DICE, every type on the waiting list), or the event's page or its
   card on the venue's listings has a "Sold out" / "Fully booked" label and no
   live booking button. Seller data saying tickets are on sale wins over a
   label. Results are kept in `ticket-cache.json`: events in the next three
   weeks are rechecked daily, later ones every four days, within a 20-minute
   limit. Pages that can't be read leave the event as it was. If this step
   fails, the day's listings are still published.
5. `scripts/tag-genres.py`: a genre only when the listing names it or
   MusicBrainz or Wikidata confidently knows the act (cached in `genre-cache.json`).
6. `scripts/validate-events.py` and `scripts/validate-required-events.py`:
   refuse to publish a small or malformed file, or one missing the events in
   `required-events.json`.
7. `scripts/build-event-pages.py`: the shareable event pages and their
   calendar files, This weekend, Tonight, the Gigs, Comedy, Club nights and
   Theatre guides, a page per venue, and the sitemap.
8. `scripts/indexnow.py`: after the push, tells Bing (IndexNow) about new
   pages. The key is the `<32 hex characters>.txt` file in the repo root.

An event's identity is **venue + date + title + start time**, so separate
sessions of the same show on one day are kept (a "Matinee" or "Later Set"
listing is never merged into the plain one unless both give the same time).
Event `id`s never change once published, because saved Interested/Going
choices, the "new since your last visit" summary and shared links use them:
a merged duplicate's id is kept in `also_ids`, and the kept listing takes the
id from the last published `events.json` (`prepare-events.py` reads it from
git).

Source notes: `EVENT-DATA-SOURCES.md`.

### Festival data

`.github/workflows/festivals.yml` refreshes `festivals.json` daily (soon after
02:37, with a backup at 10:37). The scraper
uses Fezzy as the primary discovery source and eFestivals as a music-festival
cross-check, deduplicating by festival name, date and location; sport and
outdoor events are left out by their title. Hand-confirmed Brighton festivals
are in `brighton-festivals.json`. The published window runs from today to 31
December of the following year. Festival ids start with `festival:`, so their
Interested/Going choices use the same `event_interest` table without mixing
festivals into `events.json`.

## Database (Supabase)

- `supabase/schema.sql` is the reference for what is running (exported on
  5 October 2026, with v74 and v75 folded in).
- The numbered files are the change history. `v70` (invite previews), `v72`
  (guest visits), `v73` (venue list) and `v76` (usage counts) are live but not
  yet folded into `schema.sql`. `v77` (reports of community events and an
  hourly pg_cron clean-up) is new: run it in the SQL Editor if it isn't live.
- Backups: an encrypted copy every night once two secrets are set; see
  `BACKUPS.md`.
- When you change the database, add a new numbered file, run it in the
  Supabase SQL Editor and update `schema.sql`. When a venue is added, update the
  venue list in the database along with `VENUES` in `index.html`.

## Making changes

- When you change `index.html`, bump `VERSION` in `sw.js` and the matching
  `sw.js?v=` number at the end of `index.html`, so installed copies drop
  their old cache.
- Follow the rules at the end of `DESIGN-SYSTEM.md`: tokens not hex values,
  no `!important`, no inline styles, and reuse `eventCard()`.
- Earlier changelogs and notes are in the git history.
