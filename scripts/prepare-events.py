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

def is_ben_folds_exception(venue, title):
    return venue == "brighton dome - concert hall" and BEN_FOLDS_TITLE in title_key(title)

data = json.loads(DATA.read_text())
events = data.get("events", [])
kept = []
removed = {"dome": 0, "patterns_recurring": 0, "generic": 0, "duplicates": 0}
for event in events:
    venue = str(event.get("venue") or "").strip().lower()
    title = str(event.get("title") or "").strip()
    low = title.lower()
    if venue in DOME_VENUES and not is_ben_folds_exception(venue, title):
        removed["dome"] += 1; continue
    if venue == "patterns" and any(marker in low for marker in PATTERNS_RECURRING):
        removed["patterns_recurring"] += 1; continue
    if low in GENERIC_TITLES or not title:
        removed["generic"] += 1; continue
    kept.append(event)

exact = {}
for event in kept:
    key = (str(event.get("venue") or "").lower(), str(event.get("date") or ""), title_key(event.get("title")))
    old = exact.get(key)
    if old is None or (not old.get("time") and event.get("time")):
        if old is not None: removed["duplicates"] += 1
        exact[key] = event
    else:
        removed["duplicates"] += 1

groups = {}
for event in exact.values():
    groups.setdefault((str(event.get("venue") or "").lower(), str(event.get("date") or "")), []).append(event)
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
print("Prepared event data: " + ", ".join(f"{k}={v}" for k, v in removed.items()) + f"; published={len(final)}")
