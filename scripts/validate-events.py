#!/usr/bin/env python3
"""Fail the event refresh if the generated dataset is structurally unsafe."""
import json
import re
import sys
from datetime import date
from pathlib import Path

from listing_rules import is_excluded, is_generic_title, is_patterns_recurring, title_key

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "events.json"

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
    key = (venue.lower(), event_date.isoformat(), title_key(title), str(event.get("time") or ""))
    if key in keys: errors.append(f"duplicate venue/date/time/title: {venue} / {event_date} {event.get('time') or ''} / {title}")
    keys.add(key)
    if not (start <= event_date <= end): errors.append(f"{event_id}: date outside declared range")
    if is_patterns_recurring(event): errors.append(f"recurring Patterns event still present: {event_id}")
    if is_excluded(event): errors.append(f"hidden event still present (excluded-events.json): {event_id}")
    if is_generic_title(title): errors.append(f"generic title still present: {event_id}")
    if re.search(r"(?:\bfind\s+out\s+more|\bfind\s+tickets|\bfrom\s+£\s?\d)", title, re.I): errors.append(f"listing card text as a title: {event_id}")
    if re.match(r"^\*+\s*sold\s+out", title, re.I): errors.append(f"'SOLD OUT' label in title: {event_id}")
    for field in ("time", "finish_time"):
        value = str(event.get(field) or "")
        if value and not re.fullmatch(r"\d{2}:\d{2}", value): errors.append(f"{event_id}: {field} {value!r} is not HH:MM")

alias_owner = {}
for event in events:
    for a in event.get("also_ids", []) or []:
        if a in ids: errors.append(f"{event.get('id')}: also_ids points at live event {a}")
        if a in alias_owner: errors.append(f"also_ids {a} claimed by {alias_owner[a]} and {event.get('id')}")
        alias_owner[a] = event.get("id")
if errors:
    print("\n".join(errors[:50]), file=sys.stderr)
    if len(errors) > 50: print(f"... and {len(errors) - 50} more errors", file=sys.stderr)
    raise SystemExit(1)
print(f"Validated {len(events)} events across {len({e['venue'] for e in events})} venues.")
print("No duplicate IDs, duplicate venue/date/time/title records, recurring Patterns entries, or generic titles found.")
