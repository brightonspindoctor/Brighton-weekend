#!/usr/bin/env python3
"""Validate the separate festival dataset before publishing."""
import json, re, sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "festivals.json"
MIN_FESTIVALS = 20
# More than this many festivals on the same date at the same place means the
# scraper has copied one listing's date and address onto its neighbours.
MAX_SAME_DATE_AND_PLACE = 3
CATEGORIES = {"Music", "Arts & Culture", "Food & Drink", "Family", "Wellness", "Comedy", "Film", "Sport & Outdoor", "Other"}
BAD_TITLES = {
    "read more", "read less", "places to stay", "places to stay in brighton", "next", "previous", "list view",
    "map view", "grid view", "plan your visit", "things to do", "what's on", "work with us", "submit event",
    "site map", "skip to main content", "sign up for e-newsletter", "translate", "media", "accessibility statement",
    "contact us", "accommodation", "privacy policy", "cookie policy", "a-z lowest", "z-a",
}

def norm(s): return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

if not DATA.exists(): raise SystemExit("festivals.json is missing")
try: data = json.loads(DATA.read_text())
except Exception as exc: raise SystemExit(f"invalid festivals.json: {exc}")
festivals = data.get("festivals")
if not isinstance(festivals, list): raise SystemExit("festivals must be an array")
if len(festivals) < MIN_FESTIVALS: raise SystemExit(f"only {len(festivals)} festivals; refusing to publish a suspiciously small dataset")
try: start = date.fromisoformat(data["range_start"]); end = date.fromisoformat(data["range_end"])
except Exception: raise SystemExit("invalid festival date range")
if end != date(start.year + 1, 12, 31): raise SystemExit("festival range must end on 31 December of the following calendar year")

ids, keys, errors, places = set(), set(), [], Counter()
for i, f in enumerate(festivals):
    label = f.get("id") or i
    missing = [k for k in ("id", "title", "date", "date_end", "location", "category", "ticket_url", "detail_url") if not f.get(k)]
    if missing: errors.append(f"{label}: missing {', '.join(missing)}"); continue
    try: d = date.fromisoformat(str(f["date"])); de = date.fromisoformat(str(f["date_end"]))
    except ValueError: errors.append(f"{label}: invalid date or date_end"); continue
    if not (start <= d <= de <= end): errors.append(f"{label}: dates {d} to {de} are out of order or outside {start} to {end}")
    if not str(f["id"]).startswith("festival:"): errors.append(f"{label}: id is not festival-scoped")
    if f["id"] in ids: errors.append(f"duplicate id {f['id']}")
    ids.add(f["id"])
    key = (norm(f["title"]), d.isoformat(), norm(f["location"]))
    if key in keys: errors.append(f"duplicate title/date/location {f['title']} {d}")
    keys.add(key)
    places[(d.isoformat(), norm(f["location"]))] += 1
    if f["category"] not in CATEGORIES: errors.append(f"{label}: invalid category {f['category']!r}")
    title = str(f["title"]).strip()
    if title.lower() in BAD_TITLES or title.startswith("#"): errors.append(f"{label}: navigation title {title!r}")
    if "@" in title: errors.append(f"{label}: email-like title")
    for k in ("ticket_url", "detail_url"):
        if not re.match(r"^https?://", str(f[k]), re.I): errors.append(f"{label}: {k} is not a web link")

for (d, loc), n in places.items():
    if n > MAX_SAME_DATE_AND_PLACE and loc != "uk":
        errors.append(f"{n} festivals share {d} at {loc!r}; the scraper has probably copied one listing's details onto others")

if errors:
    print("\n".join(errors[:50]), file=sys.stderr)
    if len(errors) > 50: print(f"... and {len(errors) - 50} more errors", file=sys.stderr)
    raise SystemExit(1)
print(f"Validated {len(festivals)} festivals from {start} to {end}.")
