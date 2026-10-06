#!/usr/bin/env python3
"""Normalise and apply publication rules to the combined event dataset."""
import html
import json
import re
from pathlib import Path

from event_matching import display_title, is_venue_name, same_show

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "events.json"
# Events hidden on request: {"venue", "title_contains", "note"} in excluded-events.json.
EXCLUDED = [dict(r, venue=str(r.get("venue", "")).strip().lower(), title_contains=str(r.get("title_contains", "")).strip().lower())
            for r in (json.loads((ROOT / "excluded-events.json").read_text()) if (ROOT / "excluded-events.json").exists() else [])]

def is_excluded(event):
    venue, title = str(event.get("venue") or "").strip().lower(), str(event.get("title") or "").lower()
    return any(r["title_contains"] and r["title_contains"] in title and (not r["venue"] or r["venue"] == venue) for r in EXCLUDED)

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
    # Page sections and category labels scraped from venue sites (seen on Brighton Dome pages).
    "buy ticket", "book ticket", "get ticket", "book now", "more details", "sign up", "subscribe", "newsletter",
    "you might also like", "accessible events", "accessible events theatre", "contemporary music",
    "literature, poetry & spoken word", "literature poetry and spoken word", "spoken word",
    "related events", "similar events", "more events", "whats on", "coming soon",
}

def title_key(title):
    return re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()

GENERIC_KEYS = {re.sub(r"[^a-z0-9]+", " ", t).strip() for t in GENERIC_TITLES}

# Reject venue placeholders such as “Mon 21 Sep 26” rather than publishing them as events.
def is_date_only_title(title):
    value = str(title or "").strip()
    return bool(re.fullmatch(r"(?:mon|tue|wed|thu|fri|sat|sun)(?:day)?\s+\d{1,2}\s+[a-z]{3,9}\s+\d{2,4}", value, re.I))

# Some venue sites list one hall under a longer name. Publish one venue name so
# the same show isn't listed twice (matches VENUE_ALIASES in index.html).
VENUE_ALIASES = {"Brighton Dome - Concert Hall": "Brighton Dome"}

# Venue sites sometimes append the listing date/time/doors to the title, e.g.
# "Story Magic Fri 25 Sep 2026 10:00 AM ( Doors: 9:50 AM )". Strip that tail.
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
TRAILING_DATE = re.compile(
    r"\s*(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?"
    rf"(?:(?:\d{{1,2}}(?:st|nd|rd|th)?\s+{_MON}|{_MON}\s+\d{{1,2}}(?:st|nd|rd|th)?,?)\s+\d{{4}}\b|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}\b).*$", re.I)
LEADING_LABEL = re.compile(r"^(?:(?:club|live|comedy|music|theatre|family|special|featured|free)\s+events?|limited\s+(?:free\s+)?tickets?|sold\s+out|on\s+sale\s+now|just\s+announced)\s*[-:–|]?\s+", re.I)
# Same rule as scrape-events.py: door/start times and page section labels are not event names.
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


def clean_title(title):
    raw = html.unescape(str(title or ""))
    cleaned = TRAILING_DATE.sub("", raw).strip(" -–|·")
    while True:
        shorter = LEADING_LABEL.sub("", cleaned, count=1)
        if shorter == cleaned or len(shorter) < 3:
            break
        cleaned = shorter
    return cleaned if len(cleaned) >= 3 else raw.strip()

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
    venue_name = VENUE_ALIASES.get(str(event.get("venue") or "").strip(), str(event.get("venue") or "").strip())
    new_title = display_title(clean_title(event.get("title")), venue_name)
    if new_title != event.get("title"):
        event["title"] = new_title  # the id is kept so saved Interested/Going choices still match
        cleaned_titles += 1
    fix_times(event)
    venue = str(event.get("venue") or "").strip()
    if venue in VENUE_ALIASES:
        event["venue"] = VENUE_ALIASES[venue]
events = data.get("events", [])
kept = []
removed = {"patterns_recurring": 0, "excluded": 0, "generic": 0, "duplicates": 0}
for event in events:
    venue = str(event.get("venue") or "").strip().lower()
    title = str(event.get("title") or "").strip()
    low = title.lower()
    if venue == "patterns" and any(marker in low for marker in PATTERNS_RECURRING):
        removed["patterns_recurring"] += 1; continue
    if is_excluded(event):
        removed["excluded"] += 1; continue
    if low in GENERIC_TITLES or title_key(title) in GENERIC_KEYS or NOT_A_TITLE.fullmatch(low) or not re.search(r"[^\W\d_]{2}", low) or is_date_only_title(title) or not title:
        removed["generic"] += 1; continue
    kept.append(event)

# Identity is venue + date + title + start time, so separate sessions of the
# same show on one day (e.g. 10:00 and 11:00) are kept as separate events.
def base_key(event):
    return (str(event.get("venue") or "").lower(), str(event.get("date") or ""), title_key(event.get("title")))

# The same show listed by more than one source, or worded differently
# ("Kepler" from the venue, "Kepler at Concorde 2 - Brighton" from Skiddle),
# becomes one event. Two timed listings from the same source at different
# times are separate sessions (matinee and evening) and both stay.
# The kept record lists the ids it absorbed in "also_ids", so Interested/Going
# choices saved against either id still show (index.html reads them).
def preference(event):
    # A real show name before a title that is only the venue's name, then the
    # venue's own listing, then a timed one, then the fuller title.
    return (is_venue_name(event.get("title"), event.get("venue")), event.get("source") == "discovery",
            not event.get("time"), -len(title_key(event.get("title"))))

def can_merge(kept_event, event):
    t1, t2 = kept_event.get("time") or "", event.get("time") or ""
    # Some venue pages give each show a second card titled only with the venue's
    # name ("The Forge Comedy Club" beside "Tom Ward: ..."). At the same time
    # (or with no time) it is that show.
    if is_venue_name(event.get("title"), event.get("venue")) and (not t1 or not t2 or t1 == t2):
        return True
    if not same_show(kept_event.get("title"), event.get("title"), kept_event.get("venue")):
        return False
    if not t1 or not t2 or t1 == t2:
        return True
    return kept_event.get("source") != event.get("source") and "discovery" in (kept_event.get("source"), event.get("source"))

def absorb(kept_event, event):
    for field in ("time", "finish_time", "ticket_url", "promoter"):
        if not kept_event.get(field) and event.get(field):
            kept_event[field] = event[field]
    if kept_event.get("category") in (None, "", "Other") and event.get("category") not in (None, "", "Other"):
        kept_event["category"] = event["category"]
    ids = [i for i in [*kept_event.get("also_ids", []), event.get("id"), *event.get("also_ids", [])] if i and i != kept_event.get("id")]
    kept_event["also_ids"] = sorted(set(ids))
    kept_event["last_seen"] = max(str(kept_event.get("last_seen") or ""), str(event.get("last_seen") or "")) or kept_event.get("last_seen")

merged_report = []
by_day = {}
for event in kept:
    by_day.setdefault(base_key(event)[:2], []).append(event)
final = []
for day_events in by_day.values():
    chosen = []
    for event in sorted(day_events, key=preference):
        match = next((c for c in chosen if can_merge(c, event)), None)
        if match is None:
            chosen.append(event)
            continue
        absorb(match, event)
        removed["duplicates"] += 1
        merged_report.append(f"{match['date']} {match['venue']}: kept {match['title']!r}, merged {event['title']!r}")
    final.extend(chosen)

final.sort(key=lambda e: (e.get("date", ""), e.get("time") or "99:99", e.get("venue", ""), e.get("title", "")))
# Safety net: ids must be unique (they are what saved Interested/Going choices
# point at). A record created on an earlier day keeps its id; a later
# duplicate gets a suffix.
used = set()
for event in sorted(final, key=lambda e: str(e.get("last_seen") or "")):
    base_id, n = event["id"], 2
    while event["id"] in used:
        event["id"] = f"{base_id}-{n}"; n += 1
    used.add(event["id"])
data["events"] = final
data["venues"] = sorted({str(e["venue"]) for e in final if e.get("venue")})
DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
for line in merged_report:
    print("  merged duplicate: " + line)
print("Prepared event data: " + ", ".join(f"{k}={v}" for k, v in removed.items()) + f"; cleaned_titles={cleaned_titles}; published={len(final)}")
