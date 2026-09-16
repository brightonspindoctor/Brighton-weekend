#!/usr/bin/env python3
"""Fail the event refresh if the generated dataset is structurally unsafe."""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "events.json"
DOME_VENUES = {"brighton dome", "dome - concert hall", "dome - corn exchange", "dome - studio theatre", "brighton dome - concert hall"}
PATTERNS_RECURRING = ("foundations", "fnky frdy", "fnky friday", "bottomless brunch")
GENERIC_TITLES = {
    "comedy", "classical music", "music", "talks & debate", "talks and debate", "dance", "theatre", "family",
    "what's on", "events", "upcoming events", "get tickets", "buy tickets", "book tickets", "learn more",
    "more info", "more info & tickets", "find out more", "event details", "sold out", "on sale", "on sale today",
    "tickets", "read more", "view event", "openings",
}

def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)

def is_ben_folds_exception(venue, title):
    return venue.lower() == "brighton dome - concert hall" and "ben folds" in re.sub(r"[^a-z0-9]+", " ", title.lower())

if not DATA.exists(): fail("events.json is missing")
try: data = json.loads(DATA.read_text())
except Exception as exc: fail(f"events.json is not valid JSON: {exc}")
events = data.get("events")
if not isinstance(events, list): fail("events.json.events must be an array")
if len(events) < 100: fail(f"only {len(events)} events were generated; refusing to publish a suspiciously small dataset")
try:
    start = date.fromisoformat(data.get("range_start", "")); end = date.fromisoformat(data.get("range_end", ""))
except ValueError: fail("range_start/range_end are not valid ISO dates")
if end < start: fail("range_end is before range_start")

ids, keys, errors = set(), set(), []
for i, event in enumerate(events):
    if not isinstance(event, dict): errors.append(f"event {i} is not an object"); continue
    required = ("id", "title", "date", "venue", "category")
    missing = [key for key in required if not event.get(key)]
    if missing: errors.append(f"event {i} missing {', '.join(missing)}"); continue
    event_id, title, venue = str(event["id"]), str(event["title"]).strip(), str(event["venue"]).strip()
    try: event_date = date.fromisoformat(str(event["date"]))
    except ValueError: errors.append(f"{event_id}: invalid date {event['date']!r}"); continue
    if event_id in ids: errors.append(f"duplicate id: {event_id}")
    ids.add(event_id)
    key = (venue.lower(), event_date.isoformat(), re.sub(r"[^a-z0-9]+", " ", title.lower()).strip())
    if key in keys: errors.append(f"duplicate venue/date/title: {venue} / {event_date} / {title}")
    keys.add(key)
    if not (start <= event_date <= end): errors.append(f"{event_id}: date outside declared range")
    if venue.lower() in DOME_VENUES and not is_ben_folds_exception(venue, title): errors.append(f"unauthorised Brighton Dome event still present: {event_id}")
    low = title.lower()
    if venue.lower() == "patterns" and any(marker in low for marker in PATTERNS_RECURRING): errors.append(f"recurring Patterns event still present: {event_id}")
    if low in GENERIC_TITLES: errors.append(f"generic title still present: {event_id}")

if errors:
    print("\n".join(errors[:50]), file=sys.stderr)
    if len(errors) > 50: print(f"... and {len(errors) - 50} more errors", file=sys.stderr)
    raise SystemExit(1)
print(f"Validated {len(events)} events across {len({e['venue'] for e in events})} venues.")
print("No duplicate IDs, duplicate venue/date/title records, unauthorised Brighton Dome events, recurring Patterns entries, or generic titles found.")
