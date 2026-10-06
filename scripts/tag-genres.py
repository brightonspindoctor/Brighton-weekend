#!/usr/bin/env python3
"""Give music and club events a genre, only when there is evidence for it.

Two kinds of evidence, nothing else (no guessing from the venue, the night of
the week or a loose name match):

1. The listing names the genre: "Drum & Bass Classics", "Reggaeton Party",
   "Techno All-Nighter". This is how most club nights get one.
2. MusicBrainz knows the act: exactly one artist has this exact name, the
   MusicBrainz community has tagged it, and one genre has a clear majority of
   at least two votes. Two artists with the same name, a tribute act, a single
   vote or a split vote means no genre. Club nights are named events, not
   artists, so they are only looked up when the listing names a DJ.

Each tagged event gets "genre" (one of BUCKETS) and "genre_source"
("title" or "musicbrainz:<artist id>") so any tag can be checked.
Lookups are cached in genre-cache.json so each act is looked up once
(re-checked after a while, as MusicBrainz tags grow).

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
USER_AGENT = "BrightonWeekend/1.0 ( https://brightonweekend.co.uk )"  # MusicBrainz asks for a contact
RECHECK_FOUND, RECHECK_MISS = 120, 30  # days before looking an act up again
TAGGABLE = {"Music", "Club", "Music/Club"}

BUCKETS = [
    "Indie & Rock", "Pop", "Electronic", "House & Disco", "Techno & Trance",
    "Drum & Bass", "Garage & Bass", "Hip-hop & R&B", "Latin & Afrobeats",
    "Jazz, Soul & Funk", "Folk & Country", "Punk & Metal", "Reggae & Ska", "Classical",
]

# MusicBrainz genre name -> bucket. Exact names first; WORD_RULES catch the rest.
GENRE_MAP = {
    "drum and bass": "Drum & Bass", "jungle": "Drum & Bass", "liquid funk": "Drum & Bass", "neurofunk": "Drum & Bass",
    "house": "House & Disco", "deep house": "House & Disco", "tech house": "House & Disco", "disco": "House & Disco",
    "nu disco": "House & Disco", "acid house": "House & Disco", "french house": "House & Disco", "italo disco": "House & Disco",
    "techno": "Techno & Trance", "minimal techno": "Techno & Trance", "trance": "Techno & Trance", "hard techno": "Techno & Trance",
    "uk garage": "Garage & Bass", "2 step": "Garage & Bass", "dubstep": "Garage & Bass", "bass music": "Garage & Bass",
    "grime": "Garage & Bass", "uk funky": "Garage & Bass", "bassline": "Garage & Bass",
    "hip hop": "Hip-hop & R&B", "rap": "Hip-hop & R&B", "trap": "Hip-hop & R&B", "r and b": "Hip-hop & R&B",
    "contemporary r and b": "Hip-hop & R&B", "uk hip hop": "Hip-hop & R&B", "drill": "Hip-hop & R&B",
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
    "electronic": "Electronic", "electronica": "Electronic", "idm": "Electronic", "ambient": "Electronic", "downtempo": "Electronic",
    "trip hop": "Electronic", "big beat": "Electronic", "breakbeat": "Electronic", "dance": "Electronic",
    "pop rock": "Pop", "soft rock": "Pop", "dark wave": "Electronic", "darkwave": "Electronic", "minimal wave": "Electronic",
    "coldwave": "Electronic", "synthwave": "Electronic", "electro": "Electronic", "highlife": "Latin & Afrobeats", "afropop": "Latin & Afrobeats", "afro house": "House & Disco",
}
MIN_VOTES = 2  # one person's tag is an opinion, not evidence
# Fallback for MusicBrainz genres not listed above, by a whole word in the name.
WORD_RULES = [
    ("metal", "Punk & Metal"), ("punk", "Punk & Metal"), ("techno", "Techno & Trance"), ("trance", "Techno & Trance"),
    ("house", "House & Disco"), ("disco", "House & Disco"), ("jazz", "Jazz, Soul & Funk"), ("soul", "Jazz, Soul & Funk"),
    ("funk", "Jazz, Soul & Funk"), ("blues", "Jazz, Soul & Funk"), ("folk", "Folk & Country"), ("country", "Folk & Country"),
    ("reggae", "Reggae & Ska"), ("hip", "Hip-hop & R&B"), ("rap", "Hip-hop & R&B"), ("classical", "Classical"),
    ("rock", "Indie & Rock"), ("indie", "Indie & Rock"), ("pop", "Pop"), ("electronic", "Electronic"),
]

# Genre words a listing title can name outright. Multi-word and specific terms
# only: single words that are also common band names ("Jungle", "House",
# "Soul", "Rock") are not used, because a band called Grandmas House is not a
# house night.
TITLE_RULES = [
    (r"drum\s*(?:&|and|n|'n')\s*bass|\bd\s*&\s*b\b|\bdnb\b|\bjungle\s+(?:night|rave|classics|all.?dayer)", "Drum & Bass"),
    (r"\bdeep\s+house\b|\btech\s+house\b|\bhouse\s+(?:music|night|party|classics)\b|\bdisco\s+(?:night|party|classics)\b|\bnu.?disco\b|\bday\s+disco\b", "House & Disco"),
    (r"\btechno\b|\btrance\s+(?:night|classics|anthems)\b|\bhard\s+dance\b", "Techno & Trance"),
    (r"\buk\s*garage\b|\bukg\b|\bdubstep\b|\bbassline\b|\bgrime\b", "Garage & Bass"),
    (r"\bhip.?hop\b|\br\s*(?:&|n)\s*b\b|\brnb\b", "Hip-hop & R&B"),
    (r"\breggaeton\b|\blatin\s+(?:night|party)\b|\bsalsa\b|\bafrobeats\b|\bamapiano\b|\bbachata\b", "Latin & Afrobeats"),
    (r"\bjazz\b|\bmotown\b|\bnorthern\s+soul\b|\bsoul\s+(?:club|night|weekender|all.?dayer)\b|\bfunk\s+(?:night|club)\b", "Jazz, Soul & Funk"),
    (r"\bbluegrass\b|\bamericana\b|\bcountry\s+(?:night|music)\b|\bfolk\s+(?:club|night|session)\b", "Folk & Country"),
    (r"\bpunk\s+(?:night|all.?dayer|festival)\b|\bmetal\s+(?:night|all.?dayer|festival)\b", "Punk & Metal"),
    (r"\breggae\b|\bdancehall\b|\bska\s+(?:night|all.?dayer)\b|\bdub\s+(?:night|sound\s?system)\b", "Reggae & Ska"),
    # "Orchestra" alone is not used: The Rock Orchestra, Jools Holland's Rhythm &
    # Blues Orchestra and the House & Garage Orchestra are not classical.
    (r"\bsymphony\s+orchestra\b|\bphilharmonic\b|\bstring\s+quartet\b|\bchamber\s+orchestra\b", "Classical"),
]

# Acts that are someone else's music: MusicBrainz would describe the original.
TRIBUTE = re.compile(r"\btribute\b|\bthe\s+music\s+of\b|\bcelebrat|\bplays?\s+the\s+hits\b|\blegends?\s+of\b|\bsalute\b|\bexperience\b|\bsongs\s+of\b|\bin\s+concert\b|\blive\s+in\s+concert\b|\bclassical\b.*\bmusic\s+of\b|\bvs\.?\b|\bversus\b", re.I)


def norm(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\$(?=[a-z])", "s", text).replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def genre_from_title(title):
    t = str(title or "")
    found = {bucket for pattern, bucket in TITLE_RULES if re.search(pattern, t, re.I)}
    return found.pop() if len(found) == 1 else None  # two genres named: not sure which, so none


def act_name(title):
    """The headliner's name, or None when the title isn't just an act."""
    t = re.sub(r"\s*\*[^*]*\*\s*", " ", str(title or ""))           # *Free Entry*
    t = re.sub(r"\s*[(\[][^)\]]*[)\]]\s*", " ", t)                   # (USA), [Brighton]
    t = re.split(r"\s+(?:\+|w/|with|ft\.?|feat\.?|featuring|plus|support)\s+|\s+[-–—:|]\s+|:\s", t, maxsplit=1, flags=re.I)[0]
    t = re.sub(r"\s+(?:live|uk\s+tour|tour|20\d\d)$", "", t.strip(), flags=re.I).strip(" -–|")
    if TRIBUTE.search(str(title or "")) or len(norm(t)) < 2:
        return None
    return t


def bucket_for(genres):
    """Map MusicBrainz genres [{name, count}] to one bucket, or None if unclear."""
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
    if not votes:
        return None
    best, best_votes = max(votes.items(), key=lambda kv: kv[1])
    # A clear majority of at least MIN_VOTES, or no genre: an act tagged disco 2,
    # funk 1, highlife 1, electro 1 is not clearly any one thing.
    if best_votes < MIN_VOTES or best_votes * 2 <= sum(votes.values()):
        return None
    return best


def mb_get(path):
    req = Request("https://musicbrainz.org/ws/2/" + path, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as exc:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
        finally:
            time.sleep(1.1)  # MusicBrainz allows about one request a second


def lookup(name):
    """{"mbid","name","genres","bucket","reason"} for an act name."""
    found = mb_get("artist?fmt=json&limit=10&query=" + quote(f'artist:"{name}"'))
    exact = [a for a in found.get("artists", []) if norm(a.get("name")) == norm(name)]
    if not exact:
        return {"bucket": None, "reason": "not in MusicBrainz"}
    if len(exact) > 1:
        return {"bucket": None, "reason": f"{len(exact)} artists share this name"}
    artist = exact[0]
    detail = mb_get(f"artist/{artist['id']}?fmt=json&inc=genres")
    genres = [{"name": g.get("name"), "count": g.get("count")} for g in detail.get("genres", [])]
    bucket = bucket_for(genres)
    return {"mbid": artist["id"], "name": artist.get("name"), "genres": genres, "bucket": bucket,
            "reason": "tagged" if bucket else ("no genre tags" if not genres else "genres unclear")}


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
        act = act_name(e.get("title"))
        if not act:
            rows.append({**row, "genre": None, "source": None, "reason": "not an act name (tribute, festival or mixed bill)"}); continue
        key = norm(act); hit = cache.get(key)
        stale = not hit or date.fromisoformat(hit["checked"]) < today - timedelta(days=RECHECK_FOUND if hit.get("bucket") else RECHECK_MISS)
        if stale and not offline:
            try:
                hit = dict(lookup(act), act=act, checked=today.isoformat()); cache[key] = hit; looked_up += 1
            except Exception as exc:
                errors += 1; print(f"MusicBrainz lookup failed for {act!r}: {exc}")
        bucket = bucket_for(hit.get("genres")) if hit and hit.get("mbid") else None  # today's rules, not the ones at lookup time
        if bucket:
            e["genre"], e["genre_source"] = bucket, "musicbrainz:" + hit["mbid"]
            rows.append({**row, "genre": bucket, "source": "musicbrainz", "act": act,
                         "musicbrainz": f"https://musicbrainz.org/artist/{hit['mbid']}", "mb_genres": hit.get("genres")})
        else:
            reason = (hit or {}).get("reason", "not looked up")
            if hit and hit.get("mbid") and hit.get("genres"): reason = "genres unclear or too few votes"
            rows.append({**row, "genre": None, "source": None, "act": act, "reason": reason})
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    CACHE.write_text(json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=1) + "\n")
    tagged = [r for r in rows if r["genre"]]
    by_source = {s: sum(1 for r in tagged if r["source"] == s) for s in ("title", "musicbrainz")}
    print(f"Genres: {len(tagged)}/{len(rows)} music and club events tagged "
          f"(from title {by_source['title']}, from MusicBrainz {by_source['musicbrainz']}); "
          f"lookups this run {looked_up}, failed {errors}; cached acts {len(cache)}")
    if report_path:
        Path(report_path).write_text(json.dumps({"summary": {"events": len(rows), "tagged": len(tagged), **by_source}, "rows": rows},
                                                ensure_ascii=False, indent=1) + "\n")


def _self_test():
    assert genre_from_title("Drum & Bass Classics Brighton - Halloween All Dayer") == "Drum & Bass"
    assert genre_from_title("Reggaeton Halloween Party (Brighton) 2026") == "Latin & Afrobeats"
    assert genre_from_title("Grandmas House") is None          # a band, not a house night
    assert genre_from_title("Jungle") is None                   # a band
    assert genre_from_title("party 4 u") is None                # no genre named: untagged, not guessed
    assert genre_from_title("Brighton Soul Club") == "Jazz, Soul & Funk"
    assert genre_from_title("Jools Holland & His Rhythm & Blues Orchestra") is None
    assert genre_from_title("The House & Garage Orchestra") is None
    assert genre_from_title("The Rock Orchestra") is None
    assert act_name("Boris - Pink 20th Anniversary UK Tour") == "Boris"
    assert act_name("TCHOTCHKE (USA)") == "TCHOTCHKE"
    assert act_name("Bathing Suits *Free Entry*") == "Bathing Suits"
    assert act_name("Hudson Freeman + Support") == "Hudson Freeman"
    assert act_name("Kacy & Clayton") == "Kacy & Clayton"
    assert act_name("The Jam UK - The Definitive Tribute to The Jam") is None
    assert act_name("Love Actually - Live in Concert") is None
    assert bucket_for([{"name": "indie rock", "count": 3}, {"name": "post-punk", "count": 1}]) == "Indie & Rock"
    assert bucket_for([{"name": "drum and bass", "count": 2}]) == "Drum & Bass"
    assert bucket_for([{"name": "rock", "count": 1}, {"name": "pop", "count": 1}]) is None  # a tie
    assert bucket_for([{"name": "dub", "count": 1}]) is None                                # a single vote
    assert bucket_for([{"name": "disco", "count": 2}, {"name": "electro-funk", "count": 1},
                       {"name": "highlife", "count": 1}, {"name": "electro", "count": 1}]) is None  # no majority
    assert bucket_for([]) is None
    print("tag-genres self-test passed")


if __name__ == "__main__":
    _self_test() if "--self-test" in sys.argv else main(sys.argv)
