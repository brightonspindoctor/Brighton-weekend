#!/usr/bin/env python3
"""Normalise and apply publication rules to the combined event dataset."""
import html
import json
import re
import subprocess
from pathlib import Path

from event_matching import display_title, is_venue_name, same_session, same_show
from listing_rules import is_excluded, is_generic_title, is_patterns_recurring, title_key

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "events.json"

# Talks whose listing filed them as something else: the title says so ("In
# Conversation", "Q&A", "Interview", "Podcast", "Book Tour"), or it's a
# professor's tour (not Professor Green or Professor Elemental, who are
# musicians). They are filed as Talk, which puts them on the app's Not music
# tab and keeps them out of genre tagging. Comedy is left as it is (it's on the
# same tab).
TALK_TITLE = re.compile(r"\b(?:in\s+conversation|q\s*&\s*a|interview|podcast|lecture|spoken\s+word|book\s+(?:tour|signing|launch|reading|talk))\b"
                        r"|^(?:professor|prof\.?)\s+(?!green\b|elemental\b)", re.I)

def is_talk_title(title):
    return bool(TALK_TITLE.search(str(title or "")))

assert is_talk_title("PETER SERAFINOWICZ & DOON MACKICHAN (INTERVIEW / Q&A)")
assert is_talk_title("The Wow! Scenario (James Acaster): Q&A + Signing")
assert is_talk_title("Nick Heyward: In Conversation + Book Signing")
assert is_talk_title("The Blindboy Podcast LIVE")
assert is_talk_title("Alice Cooper's 'Devil on my Shoulder' Book Tour")
assert is_talk_title("Professor Brian Cox: Emergence World Tour")
assert not is_talk_title("Professor Green")
assert not is_talk_title("Scarlet Reading")
assert not is_talk_title("Shed Seven: Live + Signing")
assert not is_talk_title("The Holiday in Concert - Film with Live Orchestra")

# ---- Tidy titles for display ----
# Listing markers such as "**FREE ENTRY**", "(FREE!)" or "(EXTRA SHOW)" become
# badges on the event ("Free", "Extra show"); "(SOLD OUT)" sets the status.
# Parts of a title written entirely in capitals are put in title case
# ("LENNA BAHULE" -> "Lenna Bahule"), keeping acronyms such as DJ, UK and Q&A.
# Ids are never changed, so saved choices still match.
BADGE_RULES = [
    (re.compile(r"^free(?:\s+(?:entry|event|gig|show|admission))?!?$", re.I), "Free"),
    (re.compile(r"^extra\s+(?:matinee\s+|evening\s+|late\s+)?(?:show|date|night|performance)!?$", re.I), "Extra show"),
    (re.compile(r"^new\s+date!?$", re.I), "New date"),
    (re.compile(r"^(?:last\s+(?:few\s+)?tickets|few\s+tickets\s+left|selling\s+fast)!?$", re.I), "Last tickets"),
]
MARKER = re.compile(r"\s*(?:\*+\s*([^*]{2,40}?)\s*\*+|\(\s*([^()]{2,40}?)\s*\)|\[\s*([^\[\]]{2,40}?)\s*\])")
TRAILING_FREE = re.compile(r"\s*[-–—|:]\s*free\s+entry(?:\s+tickets?\s+available)?\s*$", re.I)
NAME_ABBR = {"DR": "Dr", "MR": "Mr", "MRS": "Mrs", "MS": "Ms", "ST": "St", "JR": "Jr", "SR": "Sr", "MT": "Mt"}
SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "vs", "vs.", "v", "with", "feat", "feat.", "ft", "ft."}
KEEP_UPPER = {"DJ", "DJS", "MC", "MCS", "UK", "US", "USA", "NYE", "BBC", "EP", "LP", "TV", "AI", "Q&A", "B2B", "UKG", "DNB", "D&B", "R&B", "RNB",
              "NYC", "ABBA", "AC/DC", "BBQ", "VIP", "EDM", "IDM", "EBM", "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII", "XL", "AV",
              "TBA", "TBC", "RNLI", "BHAFC", "AKT", "LGBT", "LGBTQ", "LGBTQ+", "LGBTQIA+", "NHS", "HMV", "UNKLE", "KISS", "YMCA", "ATP", "AOH", "CBE", "MBE", "OBE"}


def _title_word(word, first):
    core = word.strip("()[]{}\"'‘’“”!?.,:;")
    if not core or not re.search(r"[A-Z]", core):
        return word
    if core.upper() in NAME_ABBR:  # DR -> Dr, ST -> St
        return word.replace(core, NAME_ABBR[core.upper()])
    if core.upper() in KEEP_UPPER or not re.search(r"[AEIOUY]", core) or re.search(r"[./]", core.strip(".")):
        return word  # acronyms, initials and things like A.M.C or P.E.
    if re.search(r"\d", core):
        return re.sub(r"(?<=\d)(ST|ND|RD|TH|S|AM|PM)\b", lambda m: m.group(1).lower(), word)  # 25TH, 90S, 4AM
    if not first and core.lower() in SMALL_WORDS:
        return word.lower()

    def cap(part):
        part = part.lower()
        m = re.match(r"^(mc)([a-z])(.*)$", part)
        if m and len(part) > 3:
            return "Mc" + m.group(2).upper() + m.group(3)
        m = re.match(r"^([o])(['’])([a-z])(.*)$", part)
        if m:
            return "O" + m.group(2) + m.group(3).upper() + m.group(4)
        return part[:1].upper() + part[1:]
    lead = re.match(r"^[^A-Za-z0-9]*", word).group(0)
    body = word[len(lead):]
    return lead + "-".join(cap(x) for x in body.split("-"))


def calm_caps(title):
    """Title case for parts of a title written entirely in capitals."""
    parts = re.split(r"(\s+(?:[+∙•|/&x–—-])\s+|:\s+|,\s+)", str(title or ""))
    one_word_title = len(re.findall(r"[A-Za-z][A-Za-z'’]*", str(title or ""))) == 1
    out = []
    for part in parts:
        # Small joining words ("vs", "x", "and") may already be lower case.
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’]*", part) if w.lower() not in SMALL_WORDS]
        letters = re.sub(r"[^A-Za-z]", "", "".join(words))
        short_name = one_word_title and len(letters) <= 4  # a title that is just MNEK or KEG: styled that way
        if len(letters) >= 4 and letters.isupper() and not short_name and part.strip().upper() not in KEEP_UPPER:
            words = part.split(" ")
            seen_first = False
            fixed = []
            for w in words:
                fixed.append(_title_word(w, not seen_first) if w else w)
                if w.strip():
                    seen_first = True
            part = " ".join(fixed)
        out.append(part)
    return "".join(out)


def tidy_title(title):
    """(title, badges, sold_out) for display: markers out, capitals calmed."""
    t = str(title or "")
    badges, sold_out = [], False

    def marker(m):
        nonlocal sold_out
        text = next(g for g in m.groups() if g)
        if re.fullmatch(r"sold\s+out!?", text.strip(), re.I):
            sold_out = True
            return ""
        for rx, label in BADGE_RULES:
            if rx.match(text.strip()):
                if label not in badges:
                    badges.append(label)
                return ""
        return m.group(0)
    t = MARKER.sub(marker, t)
    if TRAILING_FREE.search(t):
        t = TRAILING_FREE.sub("", t)
        if "Free" not in badges:
            badges.append("Free")
    t = re.sub(r"\s{2,}", " ", t).strip(" -–—|:·,")
    if len(t) < 2:
        return str(title or ""), [], False
    return calm_caps(t), badges, sold_out


assert tidy_title("HI JINX PROMOTIONS PRESENTS **FREE ENTRY**") == ("Hi Jinx Promotions Presents", ["Free"], False)
assert tidy_title("Harriet Kemsley: Floozy **EXTRA MATINEE SHOW**") == ("Harriet Kemsley: Floozy", ["Extra show"], False)
assert tidy_title("GET YOUR ROCKS OFF KARAOKE (FREE!)") == ("Get Your Rocks Off Karaoke", ["Free"], False)
assert tidy_title("Rough times Party - CALYX - Free Entry tickets available")[1] == ["Free"]
assert tidy_title("Some Band (SOLD OUT)") == ("Some Band", [], True)
assert tidy_title("PETER SERAFINOWICZ & DOON MACKICHAN (INTERVIEW / Q&A)")[0] == "Peter Serafinowicz & Doon Mackichan (Interview / Q&A)"
assert tidy_title("DJ FREAKING OUT THE NEIGHBOURHOOD")[0] == "DJ Freaking Out the Neighbourhood"
assert tidy_title("Indie Rock Night ∙ OASIS vs ARCTIC MONKEYS")[0] == "Indie Rock Night ∙ Oasis vs Arctic Monkeys"
assert tidy_title("TCHOTCHKE + support")[0] == "Tchotchke + support"
assert tidy_title("999 + SUPPORTS TBA")[0] == "999 + Supports TBA"
assert tidy_title("MUTATIONS 26 - MIKE D 5D (BEASTIE BOYS) + MORE")[0] == "Mutations 26 - Mike D 5D (Beastie Boys) + More"
assert tidy_title("PAUL MCGANN & BEN WHEATLEY")[0] == "Paul McGann & Ben Wheatley"
assert tidy_title("DR RAZZU + MARGAUX'S STAR CHART")[0] == "Dr Razzu + Margaux's Star Chart"
assert tidy_title("ABBA")[0] == "ABBA" and tidy_title("MNEK")[0] == "MNEK" and tidy_title("DMAs")[0] == "DMAs"
assert tidy_title("Michael Kiwanuka: 'FUDGE' Listening Gathering")[0] == "Michael Kiwanuka: 'FUDGE' Listening Gathering"
assert tidy_title("Noisy Women Present: Whispers and Waves (Matinee show only)")[0] == "Noisy Women Present: Whispers and Waves (Matinee show only)"
assert tidy_title("THE ROSE HILL IS TEN FESTIVAL ( FRIDAY TICKETS)")[0] == "The Rose Hill Is Ten Festival ( Friday Tickets)"

# Reject venue placeholders such as “Mon 21 Sep 26” rather than publishing them as events.
def is_date_only_title(title):
    value = str(title or "").strip()
    return bool(re.fullmatch(r"(?:mon|tue|wed|thu|fri|sat|sun)(?:day)?\s+\d{1,2}\s+[a-z]{3,9}\s+\d{2,4}", value, re.I))

# Some venue sites list one hall under a longer name. Publish one venue name so
# the same show isn't listed twice, and the app only ever sees its own names.
VENUE_ALIASES = {"Brighton Dome - Concert Hall": "Brighton Dome"}

# Venue sites sometimes append the listing date/time/doors to the title, e.g.
# "Story Magic Fri 25 Sep 2026 10:00 AM ( Doors: 9:50 AM )". Strip that tail.
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
# A day's name, whole or short ("Fri", "Friday"), but not "Friends" or "Sunset".
_DAY = r"(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b"
TRAILING_DATE = re.compile(
    rf"\s*(?:{_DAY}\.?,?\s+)?"
    rf"(?:(?:\d{{1,2}}(?:st|nd|rd|th)?\s+{_MON}|{_MON}\s+\d{{1,2}}(?:st|nd|rd|th)?,?)\s+\d{{4}}\b|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}\b).*$", re.I)
# A whole listing card read as a title: "Music Katherine Jenkins ... Tue 6 Oct
# Concert Hall From £39.75 Find out more" (Brighton Dome). Its show name is
# recovered and a cleaner listing of the same show is preferred.
CARD_TEXT = re.compile(r"(?:\bfind\s+out\s+more|\bfind\s+tickets|\bbook\s+now|\bfrom\s+£\s?\d)\s*$", re.I)
CARD_LABELS = re.compile(r"^(?:(?:new\s+on\s+sale|accessible\s+events|just\s+announced|music|comedy|theatre|dance|family|film\s*&\s*visual\s+arts|talks?\s*(?:&|and)\s*debate|classical\s+music|literature,?\s+poetry\s*&\s*spoken\s+word)\s+)+", re.I)
CARD_TAIL = re.compile(rf"\s+(?:{_DAY}\s+\d{{1,2}}\s+[a-z]{{3,9}}\b|brighton\s+dome\s+comedy\s+festival\b|presented\s+by\b).*$", re.I)

# "Mutations Unkle Sounds 2026 10 24": a date in numbers on the end of a title
# made from the event page's address.
TRAILING_NUMERIC_DATE = re.compile(r"\s+(?:20\d\d[\s./-]\d{1,2}[\s./-]\d{1,2}|\d{1,2}[\s./-]\d{1,2}[\s./-]20\d\d)\s*$")
# Skiddle's "Ghostface Killah (Wu-Tang Clan) / Sat 5th Dec / Chalk / Brighton":
# the date, venue and town after the name.
SLASHED_DATE_TAIL = re.compile(
    rf"\s+/\s+{_DAY}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\s+{_MON}(?:\s+\d{{4}})?(?:\s+/.*)?$", re.I)

def card_title(title):
    t = CARD_TAIL.sub("", CARD_LABELS.sub("", str(title).strip())).strip(" -–|·")
    return t if len(t) >= 3 else str(title)

LEADING_LABEL = re.compile(r"^(?:\*+\s*sold\s+out\s*\*+|(?:club|live|comedy|music|theatre|family|special|featured|free)\s+events?|limited\s+(?:free\s+)?tickets?|sold\s+out|on\s+sale\s+now|just\s+announced)\s*[-:–|]?\s+", re.I)


def clean_title(title):
    raw = html.unescape(str(title or ""))
    cleaned = TRAILING_NUMERIC_DATE.sub("", TRAILING_DATE.sub("", SLASHED_DATE_TAIL.sub("", raw))).strip(" -–|·")
    while True:
        shorter = LEADING_LABEL.sub("", cleaned, count=1)
        if shorter == cleaned or len(shorter) < 3:
            break
        cleaned = shorter
    return cleaned if len(cleaned) >= 3 else raw.strip()

assert clean_title("Ghostface Killah (Wu-Tang Clan) / Sat 5th Dec / Chalk / Brighton") == "Ghostface Killah (Wu-Tang Clan)"
assert clean_title("Mutations Unkle Sounds 2026 10 24") == "Mutations Unkle Sounds"
assert clean_title("IO / Playing Alice / Spooky Huge / Dateless Wonder Club") == "IO / Playing Alice / Spooky Huge / Dateless Wonder Club"

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
    # A date with no time read as midnight ("2026-10-12T00:00"): a concert or
    # show does not start at 00:00. Club nights can, so theirs is kept.
    if start == "00:00" and event.get("category") != "Club":
        start = ""
    finish = normalise_time(event.get("finish_time"))
    # A "finish" earlier than the start but not in the small hours is a doors time.
    if start and finish and (finish == start or (finish < start and finish >= "06:00")):
        finish = ""
    event["time"], event["finish_time"] = start, finish

data = json.loads(DATA.read_text())
cleaned_titles = 0
for event in data.get("events", []):
    venue_name = VENUE_ALIASES.get(str(event.get("venue") or "").strip(), str(event.get("venue") or "").strip())
    raw_title = str(event.get("title") or "")
    if CARD_TEXT.search(raw_title):
        event["_card_text"] = True
        raw_title = card_title(raw_title)
    if re.match(r"^\*+\s*sold\s+out", raw_title, re.I):
        event["status"] = "SOLD OUT"
    new_title = display_title(clean_title(raw_title), venue_name)
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
    if is_patterns_recurring(event):
        removed["patterns_recurring"] += 1; continue
    if is_excluded(event):
        removed["excluded"] += 1; continue
    if is_generic_title(event.get("title")) or is_date_only_title(str(event.get("title") or "").strip()):
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
    return (bool(event.get("_card_text")), is_venue_name(event.get("title"), event.get("venue")), event.get("source") == "discovery",
            not event.get("time"), -len(title_key(event.get("title"))))

# A ticket link that only this venue's listings on one day use is that show's
# own page: two listings there are one show, however each source words it
# ("Groundwork 002: Halloween w/ Soul Mass Transit System" and a title made from
# the page's address). Listings pages (any page in event-sources.json, or one
# ending /whats-on/, /events/...) never count.
SOURCE_PAGES = {str(s.get("url") or "").rstrip("/") for s in json.loads((ROOT / "event-sources.json").read_text())}
LISTING_ENDS = re.compile(r"/(?:whats-?on|events?|shows|listings|calendar|gigs|tickets|comedy(?:festival)?|music|programme)/?$", re.I)
link_days = {}
def own_link(url):
    return (bool(url) and url.rstrip("/") not in SOURCE_PAGES and not LISTING_ENDS.search(url.split("?")[0])
            and len(link_days.get(url, ())) == 1)

def minutes(t):
    return int(t[:2]) * 60 + int(t[3:5])

def can_merge(kept_event, event):
    t1, t2 = kept_event.get("time") or "", event.get("time") or ""
    u = kept_event.get("ticket_url")
    if u and u == event.get("ticket_url") and own_link(u) and (not t1 or not t2 or t1 == t2):
        return True
    # Some venue pages give each show a second card titled only with the venue's
    # name ("The Forge Comedy Club" beside "Tom Ward: ..."). At the same time
    # (or with no time) it is that show.
    if is_venue_name(event.get("title"), event.get("venue")) and (not t1 or not t2 or t1 == t2):
        return True
    if not same_show(kept_event.get("title"), event.get("title"), kept_event.get("venue")):
        return False
    # "Phoebe Bridgers" and "Phoebe Bridgers (Matinee)": two sessions, unless
    # both give the same start time.
    if not same_session(kept_event, event):
        return False
    if not t1 or not t2 or t1 == t2:
        return True
    # 11:00 and 23:00: one source read "11" without its "pm". The evening time is kept.
    if abs(minutes(t1) - minutes(t2)) == 720:
        return True
    # One site listing a show twice with the same ticket link, the second start
    # inside the first one's running time ("19:00-21:00" and "20:00": doors and
    # stage times), is one show. A matinee and an evening, or 10:00 and 11:00
    # sessions, don't overlap like that, so they stay separate.
    if (kept_event.get("source") == event.get("source") and kept_event.get("ticket_url")
            and kept_event.get("ticket_url") == event.get("ticket_url") and starts_during(kept_event, event)):
        return True
    return kept_event.get("source") != event.get("source") and "discovery" in (kept_event.get("source"), event.get("source"))

def starts_during(a, b):
    """True when one listing starts while the other, which has a finish time, is running."""
    for x, y in ((a, b), (b, a)):
        start, finish, other = x.get("time") or "", x.get("finish_time") or "", y.get("time") or ""
        if start and finish and other and (start < other < finish or (finish < start and (other > start or other < finish))):
            return True
    return False

# The ids the app already knows: those in the last published events.json (git's
# copy, as the scrapers have rewritten the file since), and the ids merged into
# them. When two listings of a show are merged, the kept one takes the id the app
# knows, so the show's id doesn't change between runs. A changed id shows the
# event as new since someone's last visit and breaks its shared link's preview.
def published_ids():
    try:
        r = subprocess.run(["git", "show", "HEAD:events.json"], cwd=ROOT, capture_output=True, text=True, timeout=60)
        events = json.loads(r.stdout).get("events", []) if r.returncode == 0 else []
    except (OSError, ValueError, subprocess.SubprocessError):
        events = []
    return {e.get("id") for e in events}, {a for e in events for a in e.get("also_ids") or []}

PUBLISHED, PUBLISHED_ALIASES = published_ids()

def keep_known_id(kept_event, event):
    rank = lambda i: 2 if i in PUBLISHED else 1 if i in PUBLISHED_ALIASES else 0
    if rank(event.get("id")) > rank(kept_event.get("id")):
        kept_event["id"], event["id"] = event["id"], kept_event["id"]

def absorb(kept_event, event, fields=("time", "finish_time", "ticket_url", "promoter")):
    keep_known_id(kept_event, event)
    for field in fields:
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
    if event.get("ticket_url"):
        link_days.setdefault(event["ticket_url"], set()).add((event.get("venue"), event.get("date")))
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
        t1, t2 = match.get("time") or "", event.get("time") or ""
        if t1 and t2 and abs(minutes(t1) - minutes(t2)) == 720:
            match["time"] = max(t1, t2)
        absorb(match, event)
        removed["duplicates"] += 1
        merged_report.append(f"{match['date']} {match['venue']}: kept {match['title']!r}, merged {event['title']!r}")
    final.extend(chosen)

# Brighton Dome's comedy festival pages also list the festival's shows at
# Komedia, which lists them itself. A Dome listing of a show Komedia has the
# same day, at the same time (or with no time on one of them, or the same
# ticket link), is Komedia's show: it is merged into Komedia's listing, which
# keeps its category (from Komedia's own booking feed) and its id (unless only
# the Dome one's was published; see keep_known_id) and lists the other in
# also_ids. A title naming Komedia is its show whatever the time, when Komedia
# has just one listing of it that day.
ALSO_LISTED_BY = {"Brighton Dome": "Komedia"}

def listed_elsewhere(event, candidates, host):
    """The host venue's own listing of this show that day, or None."""
    same = [c for c in candidates if same_show(c.get("title"), event.get("title"), host)]
    t = event.get("time") or ""
    for c in same:
        ct = c.get("time") or ""
        if not t or not ct or t == ct or (event.get("ticket_url") and event.get("ticket_url") == c.get("ticket_url")):
            return c
    if len(same) == 1 and re.search(rf"\b{re.escape(host.lower())}\b", str(event.get("title") or "").lower()):
        return same[0]
    return None

host_day = {}
for event in final:
    if event.get("venue") in ALSO_LISTED_BY.values():
        host_day.setdefault((event["venue"], event.get("date")), []).append(event)
cross_listed = set()
for event in final:
    host = ALSO_LISTED_BY.get(event.get("venue"))
    match = host and listed_elsewhere(event, host_day.get((host, event.get("date")), []), host)
    if match:
        # Not the Dome's finish time or link: its pages give most shows 23:00,
        # and Komedia's own link is the one closest to buying.
        absorb(match, event, fields=("time", "promoter"))
        cross_listed.add(id(event))
        removed["duplicates"] += 1
        merged_report.append(f"{match['date']} {match['venue']}: kept {match['title']!r}, merged {event['venue']}'s {event['title']!r}")
final = [e for e in final if id(e) not in cross_listed]

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
# Merged-away ids ("also_ids") let saved choices follow a show. An alias must
# never point at another live event, be claimed by two events, or be another
# live event's earlier id (same id apart from a -2 suffix): any of those would
# move someone's choice onto the wrong show.
def id_base(i):
    return re.sub(r"-\d+$", "", str(i))
live_ids = {e["id"] for e in final}
live_bases = {}
for e in final:
    live_bases.setdefault(id_base(e["id"]), set()).add(e["id"])
claims = {}
for e in final:
    for a in e.get("also_ids", []):
        claims[a] = claims.get(a, 0) + 1
dropped_aliases = 0
for e in final:
    if not e.get("also_ids"):
        continue
    keep = [a for a in e["also_ids"] if a not in live_ids and claims[a] == 1
            and not (live_bases.get(id_base(a), set()) - {e["id"]})]
    dropped_aliases += len(e["also_ids"]) - len(keep)
    if keep: e["also_ids"] = keep
    else: e.pop("also_ids")
recategorised = 0
for event in final:
    event.pop("_card_text", None)
    if event.get("category") not in ("Talk", "Comedy") and is_talk_title(event.get("title")):
        event["category"] = "Talk"; recategorised += 1
print(f"Filed as talks from their titles: {recategorised}")
# Display titles last, after duplicates are merged. A tidy that would make two
# listings at the same venue and time look identical is skipped.
taken = {(e.get("venue"), e.get("date"), e.get("time"), title_key(e.get("title"))) for e in final}
tidied = badged = 0
for event in final:
    new_title, badges, sold_out = tidy_title(event.get("title"))
    key = (event.get("venue"), event.get("date"), event.get("time"), title_key(new_title))
    if new_title != event.get("title"):
        if title_key(new_title) != title_key(event.get("title")) and key in taken:
            continue
        taken.add(key); event["title"] = new_title; tidied += 1
    # A listing found again today comes with its raw title, so its badges are
    # worked out afresh. One that wasn't (its venue's page failed today) keeps
    # its published title, already without the markers, and its badges.
    if badges:
        event["badges"] = badges; badged += 1
    if sold_out:
        event["status"] = "SOLD OUT"
print(f"Tidied titles: {tidied}; badges added: {badged}")
data["events"] = final
data["venues"] = sorted({str(e["venue"]) for e in final if e.get("venue")})
DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
for line in merged_report:
    print("  merged duplicate: " + line)
print("Prepared event data: " + ", ".join(f"{k}={v}" for k, v in removed.items()) + f"; cleaned_titles={cleaned_titles}; unsafe_aliases_dropped={dropped_aliases}; published={len(final)}")
