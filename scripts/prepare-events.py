#!/usr/bin/env python3
"""Normalise and apply publication rules to the combined event dataset."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "events.json"

DOME_VENUES = {
    "brighton dome",
    "dome - concert hall",
    "dome - corn exchange",
    "dome - studio theatre",
    "brighton dome - concert hall",
}
BEN_FOLDS_TITLE = "ben folds"
PATTERNS_RECURRING = (
    "foundations",
    "fnky frdy",
    "fnky friday",
    "bottomless brunch",
)
GENERIC_TITLES = {
    "event", "club", "live", "this week", "film",
    "comedy", "classical music", "music", "talks & debate", "talks and debate",
    "dance", "theatre", "family", "what's on", "events", "upcoming events",
    "get tickets", "buy tickets", "book tickets", "learn more", "more info",
    "more info & tickets", "find out more", "event details", "sold out",
    "on sale", "on sale today", "tickets", "read more", "view event", "openings",
}

def title_key(title):
    return re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()

def fuller_title(a, b):
    ka, kb = title_key(a), title_key(b)
    if ka == kb:
        return a if len(str(a)) >= len(str(b)) else b
    if ka and kb and (ka.startswith(kb + " ") or kb.startswith(ka + " ")):
        return a if len(ka) > len(kb) else b
    return None

# Reject venue placeholders such as “Mon 21 Sep 26” rather than publishing them as events.
def is_date_only_title(title):
    value = str(title or "").strip()
    return bool(re.fullmatch(r"(?:mon|tue|wed|thu|fri|sat|sun)(?:day)?\s+\d{1,2}\s+[a-z]{3,9}\s+\d{2,4}", value, re.I))

def is_ben_folds_exception(venue, title):
    return venue == "brighton dome - concert hall" and BEN_FOLDS_TITLE in title_key(title)

# Venue sites sometimes append the listing date/time/doors to the title, e.g.
# "Story Magic Fri 25 Sep 2026 10:00 AM ( Doors: 9:50 AM )". Strip that tail.
TRAILING_DATE = re.compile(
    r"\s*(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s+)?\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}\b.*$", re.I)

def clean_title(title):
    cleaned = TRAILING_DATE.sub("", str(title or "")).strip(" -–|·")
    return cleaned if len(cleaned) >= 3 else str(title or "").strip()

def normalise_time(value):
    """Return HH:MM for values like '19:30', '7:30pm', '11pm'; '' if unreadable."""
    v = str(value or "").strip().lower().replace(".", ":")
    if not v:
        return ""
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", v)
    if not m:
        return ""
    h, mins, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mins:02d}" if h < 24 and mins < 60 else ""

def fix_times(event):
    start = normalise_time(event.get("time"))
    finish = normalise_time(event.get("finish_time"))
    # A "finish" earlier than the start but not in the small hours is a doors time.
    if start and finish and (finish == start or (finish < start and finish >= "06:00")):
        finish = ""
    event["time"], event["finish_time"] = start, finish

data = json.loads(DATA.read_text())
cleaned_titles = 0
for event in data.get("events", []):
    new_title = clean_title(event.get("title"))
    if new_title != event.get("title"):
        event["title"] = new_title  # the id is kept so saved Interested/Going choices still match
        cleaned_titles += 1
    fix_times(event)
events = data.get("events", [])
kept = []
removed = {"dome": 0, "patterns_recurring": 0, "generic": 0, "duplicates": 0}
for event in events:
    venue = str(event.get("venue") or "").strip().lower()
    title = str(event.get("title") or "").strip()
    low = title.lower()
    # Brighton Dome is a major comedy venue as well as a concert/theatre venue.
    # Keep its comedy listings so named comedians are not silently discarded.
    if venue in DOME_VENUES and not is_ben_folds_exception(venue, title) and str(event.get("category") or "").lower() != "comedy":
        removed["dome"] += 1; continue
    if venue == "patterns" and any(marker in low for marker in PATTERNS_RECURRING):
        removed["patterns_recurring"] += 1; continue
    if low in GENERIC_TITLES or is_date_only_title(title) or not title:
        removed["generic"] += 1; continue
    kept.append(event)

# Identity is venue + date + title + start time, so separate sessions of the
# same show on one day (e.g. 10:00 and 11:00) are kept as separate events.
def base_key(event):
    return (str(event.get("venue") or "").lower(), str(event.get("date") or ""), title_key(event.get("title")))

exact = {}
for event in kept:
    key = base_key(event) + (event.get("time") or "",)
    if key in exact:
        removed["duplicates"] += 1
        continue
    exact[key] = event

# An untimed listing is a duplicate when the same show has a timed listing that day.
timed = {base_key(e) for e in exact.values() if e.get("time")}
deduped = []
for event in exact.values():
    if not event.get("time") and base_key(event) in timed:
        removed["duplicates"] += 1
        continue
    deduped.append(event)

groups = {}
for event in deduped:
    groups.setdefault((str(event.get("venue") or "").lower(), str(event.get("date") or ""), event.get("time") or ""), []).append(event)
final = []
for group in groups.values():
    chosen = []
    for event in sorted(group, key=lambda e: len(title_key(e.get("title"))), reverse=True):
        if any(fuller_title(existing.get("title"), event.get("title")) for existing in chosen):
            removed["duplicates"] += 1
            continue
        chosen.append(event)
    final.extend(chosen)

final.sort(key=lambda e: (e.get("date", ""), e.get("time") or "99:99", e.get("venue", ""), e.get("title", "")))
data["events"] = final
data["venues"] = sorted({str(e["venue"]) for e in final if e.get("venue")})
DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print("Prepared event data: " + ", ".join(f"{k}={v}" for k, v in removed.items()) + f"; cleaned_titles={cleaned_titles}; published={len(final)}")
