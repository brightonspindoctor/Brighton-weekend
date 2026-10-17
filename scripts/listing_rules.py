"""Which scraped listings are published: one copy of the rules, shared by
scrape-events.py, scrape-discovery.py, prepare-events.py (which applies them)
and validate-events.py (which refuses a dataset that breaks them).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Titles that are a page heading, a button or a category label, not an event.
GENERIC_TITLES = {
    "event", "events", "club", "live", "late", "night", "gig", "gigs", "film", "sport", "other", "this week",
    "comedy", "classical music", "music", "music & club", "talks & debate", "talks and debate",
    "dance", "theatre", "family", "what's on", "whats on", "upcoming events", "coming soon", "openings",
    "get tickets", "buy tickets", "book tickets", "get ticket", "buy ticket", "book ticket", "tickets",
    "book now", "learn more", "more info", "more info & tickets", "more details", "find out more",
    "event details", "read more", "view event", "sold out", "on sale", "on sale today",
    "sign up", "subscribe", "newsletter",
    # Page sections and category labels scraped from venue sites (seen on Brighton Dome pages).
    "you might also like", "accessible events", "accessible events theatre", "contemporary music",
    "literature, poetry & spoken word", "literature poetry and spoken word", "spoken word",
    "related events", "similar events", "more events",
    # Website buttons, section headings and marketing lines read as events (6 Oct 2026 review).
    "select a date", "select date", "choose a date", "select a time", "choose a time", "select a performance",
    "exhibitions and workshops", "exhibitions & workshops", "heritage & tours", "heritage and tours",
    "for the kids", "podcast", "podcasts", "talk", "talks", "secure your spot", "book your spot",
}


def title_key(title):
    return re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()


GENERIC_KEYS = {title_key(t) for t in GENERIC_TITLES}

# Text that sits in an event card but is not its name: door/start times and
# page section labels.
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
  |workshops?|accessible\s+events(?:\s+[a-z&]+)?                  # Brighton Dome's section labels
)""", re.I | re.X)


def is_generic_title(title):
    """A heading, button or label rather than an event's name."""
    low = str(title or "").strip().lower()
    return (not low or low in GENERIC_TITLES or title_key(low) in GENERIC_KEYS
            or bool(NOT_A_TITLE.fullmatch(low)) or not re.search(r"[^\W\d_]{2}", low))


# Patterns' weekly nights are left out (they would fill every week).
PATTERNS_RECURRING = ("foundations", "fnky frdy", "fnky friday", "bottomless brunch")


def is_patterns_recurring(event):
    return (str(event.get("venue") or "").strip().lower() == "patterns"
            and any(m in str(event.get("title") or "").lower() for m in PATTERNS_RECURRING))


# Events hidden on request: {"venue", "title_contains", "note"} in excluded-events.json.
_excluded_file = ROOT / "excluded-events.json"
EXCLUDED = [{"venue": str(r.get("venue", "")).strip().lower(), "title_contains": str(r.get("title_contains", "")).strip().lower()}
            for r in (json.loads(_excluded_file.read_text()) if _excluded_file.exists() else [])]


def is_excluded(event):
    venue, title = str(event.get("venue") or "").strip().lower(), str(event.get("title") or "").lower()
    return any(r["title_contains"] and r["title_contains"] in title and (not r["venue"] or r["venue"] == venue) for r in EXCLUDED)


# ---- The venue's own word for what a show is ----------------------------------
# Theatre Royal (its ATG listings), The Old Market and Brighton Dome label each
# show ("Concert", "Plays", "Musicals, Family", "Music", "Theatre", "Workshop").
# scrape-events.py collects the labels (venue_labels in events.json) and
# prepare-events.py files those venues' shows by them, because a guess from the
# words on a card can't tell a concert from a play when the card says "Theatre
# Royal". When a show has several labels, the first group here that one of
# them falls in decides: a show labelled "Music, Theatre" is a theatre show,
# "Talk, Comedy" a comedy, "Musicals, Family" a musical. A label in none of
# these groups decides nothing.
LABEL_CATEGORIES = (
    ("Theatre", {"play", "plays", "drama", "musical", "musicals", "theatre", "opera", "pantomime", "panto", "cabaret"}),
    ("Dance", {"dance", "ballet"}),
    ("Comedy", {"comedy", "stand-up", "stand up"}),
    ("Music", {"concert", "concerts", "music", "gig", "gigs", "classical", "jazz", "folk", "contemporary music"}),
    ("Talk", {"talk", "talks", "podcast", "spoken word", "lecture", "lectures", "literature", "in conversation"}),
    ("Family", {"family", "kids", "children"}),
    ("Other", {"events", "event", "film", "visual arts", "exhibition", "exhibitions", "workshop", "workshops",
               "soundbath", "tour", "tours", "course", "courses", "circus", "magic", "festival"}),
)


def label_category(label):
    parts = {p.strip().lower() for p in re.split(r"[,/&+]|\band\b", str(label or "")) if p.strip()}
    for category, words in LABEL_CATEGORIES:
        if parts & words:
            return category
    return None


def page_key(url):
    """The part of a show's address that names it: the site and the first two
    parts of the path ('atgtickets.com/shows/six', 'theoldmarket.com/shows/eddi-reader',
    'brightondome.org/whats-on/l0h-congregational'), so a show's card link
    matches its calendar or ticket link on the same site."""
    from urllib.parse import urlparse
    p = urlparse(str(url or ""))
    host = p.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    parts = [s for s in p.path.lower().split("/") if s][:2]
    return f"{host}/{'/'.join(parts)}" if host and len(parts) == 2 else ""
