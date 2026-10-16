# Event data sources

Listings are refreshed once a day by `.github/workflows/weekly-events.yml`,
normally soon after 01:17 (Europe/London), and whenever a scraper file changes.
GitHub sometimes starts scheduled runs hours late or skips them, so the
workflow also starts at 05:17, 09:17 and 13:17; those runs stop straight away
if the day's refresh has already happened.

## Where events come from

1. **Venue sources**: `event-sources.json`, read by `scripts/scrape-events.py`.
   Each entry is one page to read for one venue:

   ```json
   {"venue": "Quarters", "url": "https://www.quartersbrighton.co.uk/whatson"}
   ```

   Optional settings:

   | Setting | Meaning |
   |---|---|
   | `"jsonld_only": true` | Read only the page's structured event data (schema.org), never its layout. Used for ticketing-site pages (Skiddle, Songkick) that also show other venues' events. |
   | `"match_location": "pipeline"` | Keep only events whose stated location contains this text. Use with `jsonld_only`. |
   | `"ticketsolve": "<feed>"` | The venue's Ticketsolve feed (`<venue>.ticketsolve.com/shows.xml`). Each listing is matched to its show (by the ticket link, or by name and date) and filed under the venue's own category (comedy, music, club, kids' show, spoken word); a start time the listing leaves out is filled in. Used for Komedia. |
   | `"disabled": true` | Don't fetch this page. The venue stays known to the discovery scraper. |
   | `"note"` | Why the entry is set up this way. |

2. **Discovery calendars** (Visit Brighton, Eventbrite, Ticketmaster, Skiddle,
   the Rival Cults gig list, the promoters JOY. Concerts and Beat Down Promotions,
   and The Dice & Meeple's board game nights), read by `scripts/scrape-discovery.py`.
   Events are kept only when they are at a venue in `event-sources.json` (or the
   Amex Stadium), apart from The Dice & Meeple's (see below).

3. **Community events** added in the app (Supabase `bw_custom_events`).

## How a refresh treats existing events

- An event found again keeps its id, even if its time or the wording of its
  title changed, so people's Interested/Going choices stay attached. It takes
  the newest details and ticket link (a calendar that leaves out the time or
  link doesn't remove them). Today's listings are matched to stored events in
  three passes: same title and time, then a similar title at the same time,
  then a similar title at any time. So when a venue lists a show twice (Brighton
  Dome's comedy festival pages list each show once with a time and once
  without), the copy that matches best keeps the event's id.
- An id never changes once published. When two listings are merged, the kept
  one takes the id the app already knows (from the last published
  `events.json`, read from git). A changed id would show the event as new
  since someone's last visit and break its shared link's preview.
- A matinee, early or late show is never merged with the plain listing of the
  same show ("Phoebe Bridgers (Matinee)" and "Phoebe Bridgers", "Jake Bugg
  (Later Set)" and "Jake Bugg") unless both give the same start time
  (`session_marker` in `scripts/event_matching.py`).
- A calendar's listing of a venue's show fills the gaps in the venue's own
  listing (its start time, finish time, ticket link, and a category when the
  venue gave none, such as Music from JOY) but never replaces its details.
- The same show from two sources is published once. `scripts/event_matching.py`
  compares titles at the same venue on the same day after removing decoration
  ticketing sites add ("Kepler **at Concorde 2 - Brighton**", "**| Brighton**",
  "**+ supports**"), `&`/`and` differences and a single misspelt word. The
  venue's own listing is kept; the other record's id goes in its `also_ids`, and
  the app shows choices saved under either id. Two timed listings from the same
  source at different times are separate sessions and both stay. Each run prints
  the merges it made (`merged duplicate: ...`) in the "Prepare event data" step.
  To teach it a venue's other names in titles, add them to `VENUE_TITLE_NAMES`.
- Brighton Dome's comedy festival pages also list the festival's shows at
  Komedia. When Komedia lists the same show that day (at the same time, with no
  time on one of them, or with the same ticket link), the Dome's listing is
  merged into Komedia's, so the show appears once, at Komedia, filed as Comedy.
  Another venue that lists a partner's shows can be added to `ALSO_LISTED_BY`
  in `prepare-events.py`.
- Two listings at a venue on the same day that share a ticket link used for
  nothing else (the show's own page) are one show, whatever their titles say.
  Two listings of one show 12 hours apart (11:00 and 23:00) are one show too:
  a source dropped the "pm", and the evening time is kept. The same goes for an
  event found again 12 hours off (Skiddle's 11:00 for a Patterns club night on
  a day Patterns' own page doesn't load).
- Headings, buttons and labels read as events ("Select a date", "Book now",
  "Podcasts", "Workshops") are dropped. The list is in `scripts/listing_rules.py`, which the
  scrapers, the prepare step and the validator all use.
- Dates on the end of titles are removed: "Story Magic Fri 25 Sep 2026",
  "Mutations Unkle Sounds 2026 10 24", and Skiddle's "Ghostface Killah
  (Wu-Tang Clan) / Sat 5th Dec / Chalk / Brighton".
- An event is removed only after its venue has not listed it for **3 days in a
  row** while the venue's own page was loading properly (`last_seen`).
- If a venue's page fails, or returns less than half its usual number of
  events, none of its events are removed that day.
- Some events come from an earlier import and have no `source`. A discovery
  calendar that lists them keeps them up to date; otherwise they stay until
  their date. Several venues' own pages show only part of their programme
  (Theatre Royal's first page of shows, Brighton Centre's highlights, CHALK's
  homepage), so a show missing from them may still be on: those venues count
  as not healthy, and nothing of theirs is removed for being missing.
- A time on a listing card is read from "7:30pm" or "19:30" (two-digit hours),
  never from a doors, running or last-entry time, and a time in the act's name
  ("4am Kru") only when the card gives no other.
- Ticket links: a ticketing site or "Tickets"/"Book" button in the event's card
  first, then the event's own page; never a listings page, homepage or social
  media.

## Hiding an event

Add an entry to `excluded-events.json`: `venue` (exact app venue name; leave
empty for any venue), `title_contains` (case-insensitive text in the title) and
a `note`. The next refresh removes every matching listing and keeps it out.

## Checking how each source did

`events.json` includes `source_report`: for each venue page, the number of
events found, any error, and three sample events. `discovery_report` covers the
discovery calendars. A venue showing `0` with no error means its page loaded but
the scraper could not read it, which usually means the venue changed its site.

## Venue status (6 October 2026)

Beat Down Promotions (`tickettailor.com/events/beatdown`) is read by a Ticket
Tailor reader in `scrape-discovery.py`, which suits any promoter selling on
Ticket Tailor: add its page to `SOURCES` and `PROMOTERS`, and its sticker to
`PROMOTER_STICKERS` in `index.html`. Only Brighton & Hove postcodes are kept.

The Dice & Meeple (`tickettailor.com/events/thedicemeeple`) runs hosted board
game nights in pubs and is read by the same Ticket Tailor reader. Its nights
move between pubs, so it is in `ANY_VENUE_PROMOTERS`: a listing with a Brighton
& Hove postcode is kept at whatever venue Ticket Tailor names, filed as Other,
and the app lists it under Not music → Board games (`GAMES_PROMOTERS` in
`index.html`). It has no sticker, since stickers filter Discover's gigs; it
appears in Search → Promoter. Dice Saloon (`dicesaloon.com`) isn't read: its
site asks automated tools not to read it (robots.txt). Brighton Pub Boardgamers
list its Sunday games on Meetup.

Rival Cults (`rivalcults.com/gigs`) is one table of Brighton gigs (Date, Title,
Location, Link) read by `rivalcults_rows` in `scrape-discovery.py`. Its venue
names are mapped to ours in `RIVALCULTS_VENUES` (Alphabet = A L P H A B E T,
Chalk = CHALK, every Dome room = Brighton Dome), so no venue appears twice. A
name it lists that isn't mapped is never guessed: it is printed in the
"Discover events" step and kept in `discovery_report.rivalcults_unknown_venues`.
To add one, put it in `event-sources.json`, `VENUES` in `index.html`,
`RIVALCULTS_VENUES`, and the venue check in the latest `supabase/` file. Its
dates have no year; gigs in January onwards roll into next year.

JOY. Concerts (`joyconcerts.com/listings`) is read by its own card reader in
`scrape-discovery.py`: only gigs whose town is Brighton or Hove, at a venue in
`event-sources.json`, are kept. Its listing has no start times; the venue's own
listing supplies the time when there is one.


| Venue | Status |
|---|---|
| Volks, DUST | Own sites gone: listings via Skiddle |
| Patterns | Own page builds listings with JavaScript: Skiddle added as a second source |
| The Pipeline, The Gladstone | Own sites gone or broken: listings via Songkick |
| The Hope & Ruin | Moved to hope.pub |
| A L P H A B E T | Own listings switched off: its JOY. Concerts gigs come via joyconcerts.com |
| Babble, Old Albion | Switched off: no listings found anywhere |
| The Brunswick, Caroline of Brunswick, The Cowley Club, Daltons, The Folklore Rooms, Fortune of War, Resident, The Rose Hill, Rossi Bar, The Bee's Mouth, The Waterbear | Added 7 October 2026: listings via Rival Cults only |
