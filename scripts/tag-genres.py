#!/usr/bin/env python3
"""Give music and club events a genre, only when there is evidence for it.

Three kinds of evidence, nothing else (no guessing from the venue, the night of
the week or a loose name match):

1. The listing names the genre: "Drum & Bass Classics", "Reggaeton Party",
   "Indie Rock Night", "Brighton Big Band". This is how most club nights get one.
2. MusicBrainz knows the act: exactly one artist has this exact name (or an
   alias MusicBrainz records as a name it performs under; not for one-word names),
   the MusicBrainz community has tagged it, and one genre has a clear majority
   of at least two votes. Two artists with the same name, a tribute act, a
   single vote or a split vote means no genre. Club nights are named events,
   not artists, so they are only looked up when the listing names a DJ.
3. Wikidata knows the act: when MusicBrainz has found the one artist but isn't
   sure of the genre, the genres on the artist's Wikidata entry (the ones
   Wikipedia shows) are used if one genre has a clear majority. Wikidata can
   break a tie or fill a gap but can't overrule MusicBrainz: if MusicBrainz has
   any genre votes, Wikidata's genre must be one of them.

The act is the headliner: support acts, promoters ("X presents:"), tour names,
"live at ..." and similar are stripped from the title first. When that name
isn't in MusicBrainz, the first name of a list ("A / B", "A, B") is tried.

Each tagged event gets "genre" (one of BUCKETS) and "genre_source"
("title", "musicbrainz:<artist id>" or "wikidata:<item id>") so any tag can be
checked. Lookups are cached in genre-cache.json so each act is looked up once
(re-checked after a while, as MusicBrainz and Wikidata grow).

Usage: python scripts/tag-genres.py [--report genre-report.json] [--offline]
"""
import json, re, sys, time, unicodedata
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "events.json"
CACHE = ROOT / "genre-cache.json"
USER_AGENT = "BrightonWeekend/1.0 ( https://brightonweekend.co.uk )"  # MusicBrainz and Wikidata ask for a contact
RECHECK_FOUND, RECHECK_MISS = 120, 30  # days before looking an act up again
RULES_VERSION = 3  # stored with each lookup; see stale() for what each version changed
MAX_LOOKUPS = 1500  # per run; anything left is looked up on the next run
TAGGABLE = {"Music", "Club", "Music/Club"}

BUCKETS = [
    "Indie & Rock", "Pop", "Electronic", "House & Disco", "Techno & Trance",
    "Drum & Bass", "Garage & Bass", "Hip-hop & R&B", "Latin & Afrobeats",
    "Jazz, Soul & Funk", "Folk & Country", "Punk & Metal", "Reggae & Ska", "Classical",
]

# Genre name -> bucket. Exact names first; WORD_RULES catch the rest.
GENRE_MAP = {
    "drum and bass": "Drum & Bass", "jungle": "Drum & Bass", "liquid funk": "Drum & Bass", "neurofunk": "Drum & Bass",
    "house": "House & Disco", "deep house": "House & Disco", "tech house": "House & Disco", "disco": "House & Disco",
    "nu disco": "House & Disco", "acid house": "House & Disco", "french house": "House & Disco", "italo disco": "House & Disco",
    "techno": "Techno & Trance", "minimal techno": "Techno & Trance", "trance": "Techno & Trance", "hard techno": "Techno & Trance",
    "uk garage": "Garage & Bass", "2 step": "Garage & Bass", "dubstep": "Garage & Bass", "bass music": "Garage & Bass",
    "grime": "Garage & Bass", "uk funky": "Garage & Bass", "bassline": "Garage & Bass",
    "hip hop": "Hip-hop & R&B", "rap": "Hip-hop & R&B", "trap": "Hip-hop & R&B", "r and b": "Hip-hop & R&B",
    "contemporary r and b": "Hip-hop & R&B", "uk hip hop": "Hip-hop & R&B", "drill": "Hip-hop & R&B",
    "rhythm and blues": "Hip-hop & R&B",
    "reggaeton": "Latin & Afrobeats", "latin": "Latin & Afrobeats", "salsa": "Latin & Afrobeats", "afrobeats": "Latin & Afrobeats",
    "amapiano": "Latin & Afrobeats", "cumbia": "Latin & Afrobeats", "bachata": "Latin & Afrobeats", "latin pop": "Latin & Afrobeats",
    "jazz": "Jazz, Soul & Funk", "soul": "Jazz, Soul & Funk", "funk": "Jazz, Soul & Funk", "blues": "Jazz, Soul & Funk",
    "afrobeat": "Jazz, Soul & Funk", "neo soul": "Jazz, Soul & Funk", "gospel": "Jazz, Soul & Funk", "motown": "Jazz, Soul & Funk",
    "folk": "Folk & Country", "singer songwriter": "Folk & Country", "americana": "Folk & Country", "country": "Folk & Country",
    "bluegrass": "Folk & Country", "alt country": "Folk & Country", "contemporary folk": "Folk & Country", "indie folk": "Folk & Country",
    "punk": "Punk & Metal", "post punk": "Punk & Metal", "hardcore punk": "Punk & Metal", "metal": "Punk & Metal",
    "heavy metal": "Punk & Metal", "doom metal": "Punk & Metal", "sludge metal": "Punk & Metal", "emo": "Punk & Metal",
    "grindcore": "Punk & Metal", "drone metal": "Punk & Metal", "stoner rock": "Punk & Metal", "metalcore": "Punk & Metal",
    "reggae": "Reggae & Ska", "ska": "Reggae & Ska", "dub": "Reggae & Ska", "dancehall": "Reggae & Ska", "rocksteady": "Reggae & Ska",
    "classical": "Classical", "orchestral": "Classical", "opera": "Classical", "baroque": "Classical", "choral": "Classical",
    "contemporary classical": "Classical", "film score": "Classical",
    "pop": "Pop", "dance pop": "Pop", "synth pop": "Pop", "electropop": "Pop", "k pop": "Pop", "art pop": "Pop", "teen pop": "Pop",
    "indie pop": "Indie & Rock", "dream pop": "Indie & Rock", "britpop": "Indie & Rock", "shoegaze": "Indie & Rock",
    "post britpop": "Indie & Rock", "jangle pop": "Indie & Rock", "noise pop": "Indie & Rock", "blues rock": "Indie & Rock",
    "electronic": "Electronic", "electronica": "Electronic", "idm": "Electronic", "ambient": "Electronic", "downtempo": "Electronic",
    "trip hop": "Electronic", "big beat": "Electronic", "breakbeat": "Electronic", "dance": "Electronic",
    "electronic music": "Electronic", "electronic dance music": "Electronic",
    "pop rock": "Pop", "soft rock": "Pop", "dark wave": "Electronic", "darkwave": "Electronic", "minimal wave": "Electronic",
    "coldwave": "Electronic", "synthwave": "Electronic", "electro": "Electronic", "highlife": "Latin & Afrobeats", "afropop": "Latin & Afrobeats", "afro house": "House & Disco",
}
MIN_VOTES = 2  # one person's MusicBrainz tag is an opinion, not evidence
# Fallback for genres not listed above, by a whole word in the name.
WORD_RULES = [
    ("metal", "Punk & Metal"), ("punk", "Punk & Metal"), ("techno", "Techno & Trance"), ("trance", "Techno & Trance"),
    ("house", "House & Disco"), ("disco", "House & Disco"), ("jazz", "Jazz, Soul & Funk"), ("soul", "Jazz, Soul & Funk"),
    ("funk", "Jazz, Soul & Funk"), ("blues", "Jazz, Soul & Funk"), ("folk", "Folk & Country"), ("country", "Folk & Country"),
    ("reggae", "Reggae & Ska"), ("hip", "Hip-hop & R&B"), ("rap", "Hip-hop & R&B"), ("classical", "Classical"),
    ("rock", "Indie & Rock"), ("indie", "Indie & Rock"), ("pop", "Pop"), ("electronic", "Electronic"),
]
# Wikidata genres that are about something other than music ("stand-up comedy",
# "classical Chinese dance", "musical theatre") never count, unless they are
# listed in GENRE_MAP by their exact name.
NOT_MUSIC = re.compile(r"\b(?:dance|comedy|comedian|theatre|theater|film|poetry|spoken|musical|cabaret|circus|magic)\b")

# Genre words a listing title can name outright. Multi-word and specific terms
# only: single words that are also common band names ("Jungle", "House",
# "Soul", "Rock") are not used, because a band called Grandmas House is not a
# house night.
TITLE_RULES = [
    (r"drum\s*(?:&|and|n|'n')\s*bass|\bd\s*&\s*b\b|\bdnb\b|\bjungle\s+(?:night|rave|classics|all.?dayer)", "Drum & Bass"),
    (r"\bdeep\s+house\b|\btech\s+house\b|\bhouse\s+(?:music|night|party|classics)\b|\bdisco\s+(?:night|party|classics)\b|\bnu.?disco\b|\bday\s+disco\b", "House & Disco"),
    (r"\btechno\b|\btrance\s+(?:night|classics|anthems)\b|\bhard\s+dance\b", "Techno & Trance"),
    (r"\buk\s*garage\b|\bukg|\bdubstep\b|\bbassline\b|\bgrime\b", "Garage & Bass"),
    (r"\bhip.?hop\b|\br\s*(?:&|n)\s*b\b|\brnb\b", "Hip-hop & R&B"),
    (r"\breggaeton\b|\blatin\s+(?:night|party)\b|\bsalsa\b|\bafrobeats\b|\bamapiano\b|\bbachata\b", "Latin & Afrobeats"),
    # "Brighton Big Band", "Big Band": a title that is a big band. Not "Dutty
    # Moonshine Big Band" (electro swing), hence at most one word before it.
    (r"\bjazz\b|\bmotown\b|\bnorthern\s+soul\b|\bsoul\s+(?:club|night|weekender|all.?dayer)\b|\bfunk\s+(?:night|club)\b|^(?:the\s+)?(?:[a-z]+\s+)?big\s+band\b", "Jazz, Soul & Funk"),
    (r"\bbluegrass\b|\bamericana\b|\bcountry\s+(?:night|music)\b|\bfolk\s+(?:club|night|session)\b|\bsinger.?songwriters\b", "Folk & Country"),
    (r"\bpunk\s+(?:night|all.?dayer|festival)\b|\bmetal\s+(?:night|all.?dayer|festival)\b|\bemo\s+(?:night|anthems|party|club)\b|\bpop.?punk\s+(?:night|party|anthems)\b", "Punk & Metal"),
    (r"\breggae\b|\bdancehall\b|\bska\s+(?:night|all.?dayer)\b|\bdub\s+(?:night|club|sound\s?system)\b", "Reggae & Ska"),
    # Indie and rock nights say so: "Indie Rock Night", "An Afternoon of Indie",
    # "The Big Indie Fest", "Britpop Night". "Rock" alone is not used.
    (r"\bindie\s+(?:rock\s+)?(?:night|club|disco|party|all.?dayer|anthems|fest(?:ival)?)\b|\b(?:afternoon|evening|night)\s+of\s+indie\b|\bbrit.?pop\b|\brock\s+(?:night|club|anthems)\b", "Indie & Rock"),
    # "Queer Pop Halloween Party", "Pop Night". Not Britpop, nor pop-punk.
    (r"(?<!brit)(?<!brit\s)(?<!brit-)\bpop\s+(?:[a-z]+\s+)?(?:night|party|anthems)\b|\bcheesy\s+pop\b", "Pop"),
    # "Orchestra" alone is not used: The Rock Orchestra, Jools Holland's Rhythm &
    # Blues Orchestra and the House & Garage Orchestra are not classical.
    (r"\bsymphony\s+orchestra\b|\bphilharmonic\b|\bstring\s+quartet\b|\bchamber\s+orchestra\b|\bearly\s+music\b|\bconducts\b", "Classical"),
]

# Acts that are someone else's music: MusicBrainz would describe the original.
TRIBUTE = re.compile(r"\btribute\b|\bthe\s+music\s+of\b|\bcelebrat|\bplays?\s+the\s+hits\b|\blegends?\s+of\b|\bsalute\b|\bexperience\b|\bsongs\s+of\b|\bin\s+concert\b|\blive\s+in\s+concert\b|\bclassical\b.*\bmusic\s+of\b|\bvs\.?\b|\bversus\b", re.I)

# What separates the headliner from the rest of the title.
LINEUP_SPLIT = re.compile(r"\s+(?:\+|w/|with|ft\.?|feat\.?|featuring|plus|support(?:\s+from)?)\s+|\s+[-–—:|]\s+|:\s", re.I)
# Words after the act's name that aren't part of it, removed repeatedly.
TRAILING = [re.compile(p, re.I) for p in (
    r"\s+live\s+(?:at|in|from)\b.*$",                         # Noah Derksen live in Hove
    r"\s+(?:and\s+|&\s*|\+\s*)?special\s+guests?.*$",         # Lael Neale & Special Guests
    r"\s+headline\s+show.*$",
    r"\s+show\s*#?\s*\d+$",                                   # Abigail Lapell Show #2
    r"\s+\d+(?:st|nd|rd|th)\s+anniversary.*$",                # 3 Daft Monkeys 25th anniversary double set show
    r"\s+(?:album|ep|single|record)\s+(?:launch|release).*$",  # Kristin McClement Album Launch
    r"\s+(?:launch|release)\s+(?:show|party|gig)$",
    r"\s+(?:halloween|christmas|xmas|nye)\s+special$",
    r"\s+dj\s+set$", r"\s+acoustic(?:\s+set)?$", r"\s+in.?store$",
    r"[\s,]+(?:(?:the|spring|summer|autumn|fall|winter|uk|world|european|europe|farewell|headline|reunion|\d+(?:st|nd|rd|th)|20\d\d)\s+)*tour(?:\s+20\d\d)?$",
    r"\s+(?:live!?|20\d\d|mbe|obe|cbe)$",
)]

APOSTROPHES = "'’‘ʼ`´"
LETTERS = str.maketrans({"ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "ß": "ss",
                         "đ": "d", "Đ": "d", "ł": "l", "Ł": "l", "þ": "th", "ð": "d", "ı": "i"})


def norm(text):
    """Lower case without accents or apostrophes; any other punctuation is a space.
    ("Gentleman’s Dub Club" and "Gentleman's Dub Club" are the same, and so are
    "Pile‐Up" with a Unicode hyphen and "Pile-Up".)"""
    text = str(text or "").translate(LETTERS)
    text = "".join(ch for ch in text if ch not in APOSTROPHES)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"\$(?=[a-z])", "s", text).replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def same_name(a, b):
    """The same name, ignoring case, accents, punctuation and a leading "The"."""
    a, b = norm(a), norm(b)
    drop_the = lambda s: s[4:] if s.startswith("the ") else s
    return bool(a) and drop_the(a) == drop_the(b)


def genre_from_title(title):
    t = str(title or "")
    found = {bucket for pattern, bucket in TITLE_RULES if re.search(pattern, t, re.I)}
    return found.pop() if len(found) == 1 else None  # two genres named: not sure which, so none


def tidy(name):
    t = str(name or "").strip(" -–—|,:")
    while True:
        u = t
        for pattern in TRAILING:
            u = pattern.sub("", u).strip(" -–—|,:")
        if u == t:
            return t
        t = u


def act_candidates(title):
    """Names to look up for a listing, best first ([] when it isn't an act).
    The headliner, then the first name of a list ("A / B", "A, B", "A x B")."""
    raw = str(title or "")
    if TRIBUTE.search(raw):
        return []
    t = re.sub(r"\s*\*+[^*]*\*+\s*", " ", raw)                           # *Free Entry*, **FREE ENTRY**
    t = re.sub(r"\s*[(\[][^)\]]*[)\]]\s*", " ", t)                        # (USA), [Brighton]
    t = re.sub(r"(?:^|\s)[‘“\"'][^‘’“”\"]{2,}[’”\"'](?=\s|$)", " ", t)    # '50 years of The Jam'
    presents = re.match(r"^.*?\bpresents?\b\s*:?\s*(.*)$", t, re.I)     # the promoter isn't the act
    if presents:
        t = presents.group(1)
    head = tidy(LINEUP_SPLIT.split(t.strip(), maxsplit=1)[0])
    out = [head]
    for sep in (r"\s*/\s*", r"\s*,\s*", r"\s+x\s+"):
        first = tidy(re.split(sep, head, maxsplit=1, flags=re.I)[0])
        if first not in out:
            out.append(first)
    return [c for c in out if len(norm(c)) >= 2 and not re.search(r"\bpresents?$", c, re.I)]


def act_name(title):
    """The headliner's name, or None when the title isn't just an act."""
    names = act_candidates(title)
    return names[0] if names else None


def bucket_votes(genres):
    """Votes per bucket for genres [{name, count}]."""
    votes = {}
    for g in genres or []:
        name, count = norm(g.get("name")), int(g.get("count") or 0)
        if count <= 0:
            continue
        bucket = GENRE_MAP.get(name)
        if not bucket:
            words = set(name.split())
            bucket = next((b for w, b in WORD_RULES if w in words), None)
        if bucket:
            votes[bucket] = votes.get(bucket, 0) + count
    return votes


def bucket_for(genres, min_votes=MIN_VOTES):
    """Map genres [{name, count}] to one bucket, or None if unclear."""
    votes = bucket_votes(genres)
    if not votes:
        return None
    best, best_votes = max(votes.items(), key=lambda kv: kv[1])
    # A clear majority of at least min_votes, or no genre: an act tagged disco 2,
    # funk 1, highlife 1, electro 1 is not clearly any one thing.
    if best_votes < min_votes or best_votes * 2 <= sum(votes.values()):
        return None
    return best


def bucket_for_labels(labels):
    """One bucket for a list of Wikidata genre names, or None. Each name is one
    vote; the winner needs more than half of the music genres listed."""
    music = [l for l in labels or [] if norm(l) in GENRE_MAP or not NOT_MUSIC.search(norm(l))]
    return bucket_for([{"name": l, "count": 1} for l in music], min_votes=1)


def decide(hit):
    """(bucket, genre_source) for a cached lookup, using today's rules."""
    if not hit or not hit.get("mbid"):
        return None, None
    bucket = bucket_for(hit.get("genres"))
    if bucket:
        return bucket, "musicbrainz:" + hit["mbid"]
    bucket = bucket_for_labels(hit.get("wd_genres"))
    mb_buckets = bucket_votes(hit.get("genres"))
    if bucket and hit.get("wikidata") and (not mb_buckets or bucket in mb_buckets):
        return bucket, "wikidata:" + hit["wikidata"]
    return None, None


def http_json(url, pause):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
        finally:
            time.sleep(pause)


def mb_get(path):
    return http_json("https://musicbrainz.org/ws/2/" + path, 1.1)  # MusicBrainz allows about one request a second


def wikidata_genres(qid):
    """English names of the genres on a Wikidata item (its preferred statements)."""
    if not re.fullmatch(r"Q\d+", qid or ""):
        return []
    query = f'SELECT ?label WHERE {{ wd:{qid} wdt:P136 ?genre . ?genre rdfs:label ?label . FILTER(LANG(?label) = "en") }}'
    data = http_json("https://query.wikidata.org/sparql?format=json&query=" + quote(query), 1.0)
    return sorted({b["label"]["value"] for b in data.get("results", {}).get("bindings", []) if b.get("label")})


def lookup(name):
    """{"mbid","name","genres","wikidata","wd_genres","bucket","reason"} for an act name."""
    q = name.replace("\\", " ").replace('"', " ")
    found = mb_get("artist?fmt=json&limit=25&query=" + quote(f'artist:"{q}" OR alias:"{q}"'))
    # An alias counts only when MusicBrainz records it as a name the artist
    # performs under ("Artist name"), not a search hint: Pierre Henry has the
    # search hint "Henry", which isn't the band HENRY. One-word names are too
    # common to match through an alias at all.
    one_word = len(norm(name).split()) < 2
    names_of = lambda a: [a.get("name")] + ([] if one_word else
        [x.get("name") for x in (a.get("aliases") or []) if str(x.get("type") or "").lower() == "artist name"])
    exact = [a for a in found.get("artists", []) if any(same_name(n, name) for n in names_of(a))]
    if not exact:
        return {"bucket": None, "reason": "not in MusicBrainz"}
    if len(exact) > 1:
        return {"bucket": None, "reason": f"{len(exact)} artists share this name"}
    artist = exact[0]
    detail = mb_get(f"artist/{artist['id']}?fmt=json&inc=genres+url-rels")
    genres = [{"name": g.get("name"), "count": g.get("count")} for g in detail.get("genres", [])]
    hit = {"mbid": artist["id"], "name": artist.get("name"), "genres": genres}
    for rel in detail.get("relations", []) or []:
        m = re.search(r"/(Q\d+)$", str((rel.get("url") or {}).get("resource", ""))) if rel.get("type") == "wikidata" else None
        if m:
            hit["wikidata"] = m.group(1)
    if hit.get("wikidata") and not bucket_for(genres):  # Wikidata is only asked when MusicBrainz isn't sure
        try:
            hit["wd_genres"] = wikidata_genres(hit["wikidata"])
        except Exception as exc:
            hit["wd_error"] = True
            print(f"Wikidata lookup failed for {name!r} ({hit['wikidata']}): {exc}")
    hit["bucket"] = decide(hit)[0]
    hit["reason"] = "tagged" if hit["bucket"] else ("no genre tags" if not genres and not hit.get("wd_genres") else "genres unclear")
    return hit


def stale(hit, today):
    if not hit or "checked" not in hit:
        return True
    if hit.get("wd_error"):
        return True
    v = hit.get("v", 1)
    if v < 2 and not hit.get("bucket"):  # v2: better act names, apostrophes, "The", aliases, Wikidata
        return True
    if v < 3 and hit.get("mbid") and not same_name(hit.get("name"), hit.get("act")):  # v3: matched through an alias
        return True
    days = RECHECK_FOUND if hit.get("bucket") else RECHECK_MISS
    return date.fromisoformat(hit["checked"]) < today - timedelta(days=days)


def main(argv):
    report_path = argv[argv.index("--report") + 1] if "--report" in argv else None
    offline = "--offline" in argv
    data = json.loads(DATA.read_text())
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    today = date.today()
    looked_up = errors = 0
    rows = []
    for e in data.get("events", []):
        e.pop("genre", None); e.pop("genre_source", None)
        if e.get("category") not in TAGGABLE:
            continue
        row = {"date": e.get("date"), "venue": e.get("venue"), "title": e.get("title"), "category": e.get("category")}
        g = genre_from_title(e.get("title"))
        if g:
            e["genre"], e["genre_source"] = g, "title"
            rows.append({**row, "genre": g, "source": "title"}); continue
        if e.get("category") == "Club" and not re.search(r"^\s*dj\s|\bdj\s+set\b", str(e.get("title") or ""), re.I):
            rows.append({**row, "genre": None, "source": None, "reason": "club night with no genre in its listing"}); continue
        names = act_candidates(e.get("title"))
        if not names:
            rows.append({**row, "genre": None, "source": None, "reason": "not an act name (tribute, festival or mixed bill)"}); continue
        hit = act = None
        try:
            for name in names:
                key = norm(name); h = cache.get(key)
                if stale(h, today) and not offline and looked_up < MAX_LOOKUPS:
                    try:
                        h = dict(lookup(name), act=name, checked=today.isoformat(), v=RULES_VERSION); cache[key] = h; looked_up += 1
                    except Exception as exc:
                        errors += 1; print(f"MusicBrainz lookup failed for {name!r}: {exc}")
                hit, act = h, name
                # Found (with or without a genre) or shared by several artists:
                # the headliner is settled, so the list's first name isn't tried.
                if not h or h.get("reason") != "not in MusicBrainz":
                    break
            bucket, source = decide(hit)
        except Exception as exc:  # one odd listing must not stop the daily refresh
            errors += 1; print(f"Genre tagging failed for {e.get('title')!r}: {exc}")
            bucket = source = None
        if bucket:
            e["genre"], e["genre_source"] = bucket, source
            link = (f"https://musicbrainz.org/artist/{hit['mbid']}" if source.startswith("musicbrainz:")
                    else f"https://www.wikidata.org/wiki/{hit['wikidata']}")
            rows.append({**row, "genre": bucket, "source": source.split(":")[0], "act": act, "link": link,
                         "mb_genres": hit.get("genres"), "wd_genres": hit.get("wd_genres")})
        else:
            reason = (hit or {}).get("reason", "not looked up")
            if hit and hit.get("mbid") and (hit.get("genres") or hit.get("wd_genres")): reason = "genres unclear or too few votes"
            rows.append({**row, "genre": None, "source": None, "act": act, "tried": names, "reason": reason})
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    CACHE.write_text(json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=1) + "\n")
    tagged = [r for r in rows if r["genre"]]
    by_source = {s: sum(1 for r in tagged if r["source"] == s) for s in ("title", "musicbrainz", "wikidata")}
    print(f"Genres: {len(tagged)}/{len(rows)} music and club events tagged "
          f"(from title {by_source['title']}, MusicBrainz {by_source['musicbrainz']}, Wikidata {by_source['wikidata']}); "
          f"lookups this run {looked_up}, failed {errors}; cached acts {len(cache)}")
    if report_path:
        Path(report_path).write_text(json.dumps({"summary": {"events": len(rows), "tagged": len(tagged), **by_source}, "rows": rows},
                                                ensure_ascii=False, indent=1) + "\n")


def _self_test():
    # Every rule files into one of the BUCKETS (GENRE_ORDER in index.html lists the same ones).
    assert {b for b in GENRE_MAP.values()} | {b for _, b in WORD_RULES} | {b for _, b in TITLE_RULES} <= set(BUCKETS)
    assert genre_from_title("Drum & Bass Classics Brighton - Halloween All Dayer") == "Drum & Bass"
    assert genre_from_title("Reggaeton Halloween Party (Brighton) 2026") == "Latin & Afrobeats"
    assert genre_from_title("Grandmas House") is None          # a band, not a house night
    assert genre_from_title("Jungle") is None                   # a band
    assert genre_from_title("party 4 u") is None                # no genre named: untagged, not guessed
    assert genre_from_title("Brighton Soul Club") == "Jazz, Soul & Funk"
    assert genre_from_title("Jools Holland & His Rhythm & Blues Orchestra") is None
    assert genre_from_title("The House & Garage Orchestra") is None
    assert genre_from_title("The Rock Orchestra") is None
    assert genre_from_title("Indie Rock Night ∙ DAD ROCK") == "Indie & Rock"
    assert genre_from_title("An Afternoon of Indie") == "Indie & Rock"
    assert genre_from_title("The Big Indie Fest") == "Indie & Rock"
    assert genre_from_title("Britpop Night") == "Indie & Rock"   # not also Pop
    assert genre_from_title("ROCK 'N' POLE") is None
    assert genre_from_title("BLACK PARADE – 00S EMO ANTHEMS HALLOWEEN PARTY") == "Punk & Metal"
    assert genre_from_title("CLUB BNDM: QUEER POP HALLOWEEN PARTY") == "Pop"
    assert genre_from_title("Alt Pop: with Drunk Keith!, Project Adorno") is None
    assert genre_from_title("Brighton Big Band") == "Jazz, Soul & Funk"
    assert genre_from_title("Dutty Moonshine Big Band") is None  # electro swing
    assert genre_from_title("Alpesh Chauhan conducts Schumann") == "Classical"
    assert genre_from_title("Brighton Early Music Festival : Clubnight") == "Classical"
    assert genre_from_title("Return To UKGrave (Halloween Special)") == "Garage & Bass"
    assert genre_from_title("Singer Songwriters for Free Tibet") == "Folk & Country"
    assert act_name("Boris - Pink 20th Anniversary UK Tour") == "Boris"
    assert act_name("TCHOTCHKE (USA)") == "TCHOTCHKE"
    assert act_name("Bathing Suits *Free Entry*") == "Bathing Suits"
    assert act_name("Hudson Freeman + Support") == "Hudson Freeman"
    assert act_name("Kacy & Clayton") == "Kacy & Clayton"
    assert act_name("The Jam UK - The Definitive Tribute to The Jam") is None
    assert act_name("Love Actually - Live in Concert") is None
    assert act_name("Willkommen Records presents: Kristin McClement Album Launch + Chris Cundy") == "Kristin McClement"
    assert act_name("HI JINX PROMOTIONS PRESENTS **FREE ENTRY**") is None
    assert act_name("REVOLT BRIGHTON PRESENTS") is None
    assert act_name("Noah Derksen live in Hove") == "Noah Derksen"
    assert act_name("Lael Neale & Special Guests") == "Lael Neale"
    assert act_name("Gaz Brookfield, Autumn 2026 tour") == "Gaz Brookfield"
    assert act_name("BRUCE FOXTON '50 years of The Jam' Tour") == "BRUCE FOXTON"
    assert act_name("Runner Devolver: 'Forces Beyond Our Control' EP Launch") == "Runner Devolver"
    assert act_name("Lo Fidelity Allstars DJ Set") == "Lo Fidelity Allstars"
    assert act_name("3 Daft Monkeys 25th anniversary double set show") == "3 Daft Monkeys"
    assert act_name("Abigail Lapell Show #2") == "Abigail Lapell"
    assert act_name("Shed Seven: Live + Signing") == "Shed Seven"
    assert act_name("Let's Meet Tommy Romero Tour - Gentleman of Rock'n'Roll") == "Let's Meet Tommy Romero"
    assert act_candidates("Jetstream Pony / Firestations") == ["Jetstream Pony / Firestations", "Jetstream Pony"]
    assert act_candidates("Interpol, Bloc Party") == ["Interpol, Bloc Party", "Interpol"]
    assert act_candidates("Hed P.E. / Cold") == ["Hed P.E. / Cold", "Hed P.E."]
    assert norm("Gentleman’s Dub Club") == norm("Gentleman's Dub Club") == "gentlemans dub club"
    assert norm("Dinosaur Pile‐Up") == norm("Dinosaur Pile-Up") == "dinosaur pile up"
    assert norm("Røyksopp") == "royksopp" and norm("Björn Again") == "bjorn again"
    assert same_name("Mekons", "The Mekons") and not same_name("Mekons", "Mekon")
    assert bucket_for([{"name": "indie rock", "count": 3}, {"name": "post-punk", "count": 1}]) == "Indie & Rock"
    assert bucket_for([{"name": "drum and bass", "count": 2}]) == "Drum & Bass"
    assert bucket_for([{"name": "rock", "count": 1}, {"name": "pop", "count": 1}]) is None  # a tie
    assert bucket_for([{"name": "dub", "count": 1}]) is None                                # a single vote
    assert bucket_for([{"name": "disco", "count": 2}, {"name": "electro-funk", "count": 1},
                       {"name": "highlife", "count": 1}, {"name": "electro", "count": 1}]) is None  # no majority
    assert bucket_for([]) is None
    assert bucket_for_labels(["indie rock", "post-punk revival", "alternative rock"]) == "Indie & Rock"
    assert bucket_for_labels(["folk music"]) == "Folk & Country"
    assert bucket_for_labels(["folk music", "trip hop"]) is None          # split
    assert bucket_for_labels(["stand-up comedy", "observational comedy"]) is None
    assert bucket_for_labels(["classical Chinese dance"]) is None
    assert bucket_for_labels(["dance-pop", "pop music"]) == "Pop"
    assert decide({"mbid": "m", "genres": [{"name": "folk", "count": 1}], "wikidata": "Q1", "wd_genres": ["folk music"]}) == ("Folk & Country", "wikidata:Q1")
    assert decide({"mbid": "m", "genres": [{"name": "folk", "count": 2}]}) == ("Folk & Country", "musicbrainz:m")
    assert decide({"bucket": None, "reason": "not in MusicBrainz"}) == (None, None)
    # Wikidata can't overrule MusicBrainz (Tom McRae: rock/folk votes, Wikidata says pop)
    assert decide({"mbid": "m", "wikidata": "Q1", "wd_genres": ["pop music", "pop rock"],
                   "genres": [{"name": "alternative rock", "count": 1}, {"name": "indie folk", "count": 1}]}) == (None, None)
    assert decide({"mbid": "m", "wikidata": "Q1", "wd_genres": ["alternative rock"], "genres": []}) == ("Indie & Rock", "wikidata:Q1")
    assert stale({"mbid": "x", "name": "Pierre Henry", "act": "HENRY", "bucket": "Classical", "v": 2, "checked": "2099-01-01"}, date(2099, 1, 1))
    assert not stale({"mbid": "x", "name": "The Mekons", "act": "Mekons", "bucket": "Indie & Rock", "v": 2, "checked": "2099-01-01"}, date(2099, 1, 1))
    print("tag-genres self-test passed")


if __name__ == "__main__":
    _self_test() if "--self-test" in sys.argv else main(sys.argv)
