# Event data sources — v30

The v30 refresh used the existing Brighton Weekend feed as its baseline and added newly verified listings from current venue pages where the research pass found material gaps.

## Primary venue sources used

- Concorde 2 — https://www.concorde2.co.uk/whats-on
- DJ Yoda — https://www.concorde2.co.uk/event/dj-yoda
- Quarters — https://www.quartersbrighton.co.uk/whatson
- Brighton Centre — https://brightoncentre.co.uk/
- Komedia — https://www.komedia.co.uk/

## Research notes

- DJ Yoda at Concorde 2 on 6 November 2026 is explicitly listed by Concorde 2 at 7:00pm and was added to the feed.
- Concorde 2's November and December listings were substantially expanded from the venue's current What's On page.
- Quarters' current What's On page supplied additional September/November listings that were missing from the baseline file.
- Brighton Centre's current site supplied additional November/December 2026 and February 2027 listings.
- The existing feed was retained rather than replaced wholesale; new records were de-duplicated by date + venue + title.

## Important limitation

This is a substantial refresh, not a guarantee that every event announced across every Brighton venue and every third-party ticketing platform has been captured. Event pages change frequently, some listings are published later than others, and third-party aggregators can contain listings that are not yet present on a venue's own site.

v30 is designed so that users can add missing events themselves from Happenings; those community events are stored in Supabase and merged into the main feed for everyone.
