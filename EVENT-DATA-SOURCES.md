# Event data sources

Listings are refreshed every day at 07:17 (Europe/London) by
`.github/workflows/weekly-events.yml`, and whenever a scraper file changes.

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
   | `"disabled": true` | Don't fetch this page. The venue stays known to the discovery scraper. |
   | `"note"` | Why the entry is set up this way. |

2. **Discovery calendars** (Visit Brighton, Eventbrite, Ticketmaster, Skiddle),
   read by `scripts/scrape-discovery.py`. Events are kept only when they are at
   a venue in `event-sources.json` (or the Amex Stadium).

3. **Community events** added in the app (Supabase `bw_custom_events`).

## How a refresh treats existing events

- An event found again keeps its id, even if its time or the wording of its
  title changed, so people's Interested/Going choices stay attached. It takes
  the newest details and ticket link.
- An event is removed only after its venue has not listed it for **3 days in a
  row** while the venue's own page was loading properly (`last_seen`).
- If a venue's page fails, or returns less than half its usual number of
  events, none of its events are removed that day.
- Ticket links: a ticketing site or "Tickets"/"Book" button in the event's card
  first, then the event's own page; never a listings page, homepage or social
  media.

## Checking how each source did

`events.json` includes `source_report`: for each venue page, the number of
events found, any error, and three sample events. `discovery_report` covers the
discovery calendars. A venue showing `0` with no error means its page loaded but
the scraper could not read it, which usually means the venue changed its site.

## Venue status (6 October 2026)

| Venue | Status |
|---|---|
| Volks, DUST | Own sites gone: listings via Skiddle |
| Patterns | Own page builds listings with JavaScript: Skiddle added as a second source |
| The Pipeline, The Gladstone | Own sites gone or broken: listings via Songkick |
| The Hope & Ruin | Moved to hope.pub |
| A L P H A B E T, Babble, Old Albion | Switched off: no listings found anywhere |
