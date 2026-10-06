#!/usr/bin/env python3
"""Fail the event refresh if the generated dataset is structurally unsafe."""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "events.json"
PATTERNS_RECURRING = ("foundations", "fnky frdy", "fnky friday", "bottomless brunch")
GENERIC_TITLES = {
    "comedy", "classical music", "music", "talks & debate", "talks and debate", "dance", "theatre", "family",
    "what's on", "events", "upcoming events", "get tickets", "buy tickets", "book tickets", "learn more",
    "more info", "more info & tickets", "find out more", "event details", "sold out", "on sale", "on sale today",
    "tickets", "read more", "view event", "openings",
    # Page sections and category labels scraped from venue sites (seen on Brighton Dome pages).
    "buy ticket", "book ticket", "get ticket", "book now", "more details", "sign up", "subscribe", "newsletter",
    "you might also like", "accessible events", "accessible events theatre", "contemporary music",
    "literature, poetry & spoken word", "literature poetry and spoken word", "spoken word",
    "related events", "similar events", "more events", "whats on", "coming soon",
    # Website buttons, section headings and marketing lines read as events (6 Oct 2026 review).
    "select a date", "select date", "choose a date", "select a time", "choose a time", "select a performance",
    "exhibitions and workshops", "exhibitions & workshops", "heritage & tours", "heritage and tours",
    "for the kids", "podcast", "podcasts", "talk", "talks", "secure your spot", "book your spot",
}

NOT_A_TITLE = re.compile(r"""(?:
   doors?(?:\s*open)?\s*[:\-]?\s*\d.*                 # Doors: 7:00 PM
  |starts?(?:\s*at)?\s*[:\-]?\s*\d.*                  # Starts 8pm
  |(?:start\s*)?times?\s*[:\-]\s*\d.*                 # Time: 8pm
  |on\s+sale(?:\s+now)?|on\s+sale\s+\d.*
  |tickets?\s+from\s+\W?\d.*|from\s+\W?\d[\d.,]*      # Tickets from £10
  |ages?\s*\d+\+?.*|\d{1,2}\+                         # Age 18+, 18+
  |\d{1,2}(?::\d{2})?\s*(?:am|pm)(?:\s*[-–]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm))?   # 8pm, 8pm-11pm
  |limited\s+(?:free\s+)?tickets?\b.*|early\s*bird(?:\s+tickets?)?|bu[yt]\s+tickets?\b.*
  |pub\s+events|top\s+picks|next\s+up(?:\s+in\s+the\s+venue)?|this\s+week|coming\s+(?:up|soon)|upcoming
  |featured|free\s+tickets?|all\s+events|whats?\s+on|more\s+events|more\s+.+\s+events|you\s+might\s+also\s+like|edition
)""", re.I | re.X)
EXCLUDED = json.loads((ROOT / "excluded-events.json").read_text()) if (ROOT / "excluded-events.json").exists() else []
GENERIC_KEYS = {re.sub(r"[^a-z0-9]+", " ", t).strip() for t in GENERIC_TITLES}

def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)

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
    key = (venue.lower(), event_date.isoformat(), re.sub(r"[^a-z0-9]+", " ", title.lower()).strip(), str(event.get("time") or ""))
    if key in keys: errors.append(f"duplicate venue/date/time/title: {venue} / {event_date} {event.get('time') or ''} / {title}")
    keys.add(key)
    if not (start <= event_date <= end): errors.append(f"{event_id}: date outside declared range")
    low = title.lower()
    if venue.lower() == "patterns" and any(marker in low for marker in PATTERNS_RECURRING): errors.append(f"recurring Patterns event still present: {event_id}")
    if any(str(r.get("title_contains", "")).lower() in low and (not r.get("venue") or str(r["venue"]).lower() == venue.lower()) for r in EXCLUDED if r.get("title_contains")):
        errors.append(f"hidden event still present (excluded-events.json): {event_id}")
    if low in GENERIC_TITLES or re.sub(r"[^a-z0-9]+", " ", low).strip() in GENERIC_KEYS or not re.search(r"[^\W\d_]{2}", low) or NOT_A_TITLE.fullmatch(low): errors.append(f"generic title still present: {event_id}")
    if re.search(r"(?:\bfind\s+out\s+more|\bfind\s+tickets|\bfrom\s+£\s?\d)", title, re.I): errors.append(f"listing card text as a title: {event_id}")
    if re.match(r"^\*+\s*sold\s+out", title, re.I): errors.append(f"'SOLD OUT' label in title: {event_id}")
    for field in ("time", "finish_time"):
        value = str(event.get(field) or "")
        if value and not re.fullmatch(r"\d{2}:\d{2}", value): errors.append(f"{event_id}: {field} {value!r} is not HH:MM")

if errors:
    print("\n".join(errors[:50]), file=sys.stderr)
    if len(errors) > 50: print(f"... and {len(errors) - 50} more errors", file=sys.stderr)
    raise SystemExit(1)
print(f"Validated {len(events)} events across {len({e['venue'] for e in events})} venues.")
print("No duplicate IDs, duplicate venue/date/time/title records, recurring Patterns entries, or generic titles found.")
