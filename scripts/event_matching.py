"""Decide whether two listings at the same venue on the same day are one show.

Ticketing and discovery sites decorate titles with the venue and city
("Kepler at Concorde 2 - Brighton", "Hybrid Minds | Brighton",
"Lafs + Supports @ the Pipeline, Brighton"), while the venue's own site just
says "Kepler". Both scrapers and prepare-events.py use this module so the same
show is recognised however each source words it.
"""
import html
import re
import unicodedata
from difflib import SequenceMatcher

# Other names a venue goes by in titles (lower case, compared after the
# "the " prefix is removed). The venue's own name is always included.
VENUE_TITLE_NAMES = {
    "concorde 2": ["concorde2", "concorde ii", "the concorde"],
    "the hope & ruin": ["hope and ruin", "hope & ruin", "hope ruin"],
    "brighton dome": ["the dome", "dome", "corn exchange", "brighton dome corn exchange", "brighton dome concert hall"],
    "theatre royal brighton": ["theatre royal"],
    "komedia": ["komedia brighton"],
    "the pipeline": ["pipeline", "pipleline"],
    "volks": ["volks club", "the volks"],
    "green door store": ["the green door store", "greendoorstore"],
    "the old market": ["old market", "tom"],
    "brighton centre": ["the brighton centre"],
}

CITY = r"(?:brighton(?:\s*(?:&|and)\s*hove)?|hove)"
SEP = r"[\s\-–—|:,·/(\[]+"


def _plain(text):
    text = html.unescape(str(text or ""))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    # "$layyyter" is how one source styles Slayyyter.
    text = re.sub(r"\$(?=[a-z])", "s", text.lower())
    return text.replace("&", " and ")


def _key(text):
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _venue_names(venue):
    v = str(venue or "").strip().lower()
    names = {v, *VENUE_TITLE_NAMES.get(v, [])}
    names |= {n[4:] for n in list(names) if n.startswith("the ")}
    return sorted({_key(_plain(n)) for n in names if n}, key=len, reverse=True)


def core_title(title, venue=""):
    """The show's name with venue, city, year and support-act decoration removed.

    Used only for matching; the published title is left as the source wrote it
    (apart from display_title below).
    """
    k = _key(_plain(title))
    names = _venue_names(venue)
    venue_re = "|".join(re.escape(n) for n in names) if names else r"(?!x)x"
    patterns = [
        r"\s+(?:20\d\d)$",                                         # "... 2026"
        r"\s+tickets?$",                                            # "... tickets"
        r"\s+free\s+entry$",                                       # "*Free Entry*"
        rf"\s+(?:live\s+)?(?:at|in)\s+(?:the\s+)?(?:{venue_re})(?:\s+{CITY})?$",  # "at Concorde 2 Brighton"
        rf"\s+(?:{venue_re})(?:\s+{CITY})?$",                       # "| Concorde 2"
        rf"\s+(?:live\s+)?in\s+{CITY}$",                            # "live in Brighton"
        rf"\s+{CITY}$",                                             # "| Brighton"
        r"\s+(?:plus|and|with|w)\s+(?:special\s+)?(?:guests?|supports?)$",  # "+ supports"
        r"\s+live$",
    ]
    changed = True
    while changed:
        changed = False
        for p in patterns:
            shorter = re.sub(p, "", k).strip()
            if shorter != k and len(shorter) >= 3:
                k, changed = shorter, True
    return k


def same_show(a, b, venue=""):
    """True when two titles at the same venue on the same day are one show."""
    ka, kb = core_title(a, venue), core_title(b, venue)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    short, long_ = sorted((ka, kb), key=len)
    # "Mr Cutts" / "Cutts", "Kepler" / "Kepler support tba": one is a whole-word
    # start or end of the other. Short fragments ("the", "dj") are too vague.
    if len(short) >= 4 and (long_.startswith(short + " ") or long_.endswith(" " + short)):
        return True
    # A single misspelt word ("Keplter" / "Kepler"); every other word identical.
    wa, wb = ka.split(), kb.split()
    if len(wa) != len(wb):
        return False
    diffs = [(x, y) for x, y in zip(wa, wb) if x != y]
    return (len(diffs) == 1 and min(len(diffs[0][0]), len(diffs[0][1])) >= 5
            and not (diffs[0][0].isdigit() or diffs[0][1].isdigit())
            and diffs[0][0][0] == diffs[0][1][0]
            and SequenceMatcher(None, *diffs[0]).ratio() >= 0.85)


# Display cleaning: drop a trailing "at <this venue>", "@ ..." or "| Brighton"
# that only repeats what the card already shows. A title that simply ends in the
# word Brighton ("Brighton Soul Club", "Comedy Brighton") is left alone.
def display_title(title, venue=""):
    raw = str(title or "").strip()
    names = [n for n in _venue_names(venue)]
    venue_re = "|".join(r"\s+".join(map(re.escape, n.split())) for n in names) if names else r"(?!x)x"
    patterns = [
        r"\s*[*(\[]\s*free\s+entry\s*[*)\]]\s*$",
        rf"\s+(?:live\s+)?(?:at|@)\s+(?:the\s+)?(?:{venue_re})\b[\s,\-–|]*(?:{CITY})?\s*$",
        rf"\s+@\s+.+$",
        rf"\s*[\-–—|·]\s*(?:{CITY})\s*$",
        rf"\s*[(\[]\s*(?:{CITY})\s*[)\]]\s*$",
    ]
    cleaned = raw
    for p in patterns:
        shorter = re.sub(p, "", cleaned, flags=re.I).strip(" -–|·,")
        if len(shorter) >= 3:
            cleaned = shorter
    return cleaned


def _self_test():
    cases_same = [
        ("Kepler", "Kepler at Concorde 2 - Brighton", "Concorde 2"),
        ("Hybrid Minds", "Hybrid Minds | Brighton", "Concorde 2"),
        ("Lafs", "Lafs + Supports @ the Pipleline, Brighton", "The Pipeline"),
        ("Drum & Bass Classics Brighton - Halloween All Dayer", "Drum and Bass Classics Brighton | Halloween All Dayer", "Concorde 2"),
        ("Funny Women Live In Brighton", "Funny Women Live in Brighton", "Komedia"),
        ("Mr Cutts", "Cutts", "Komedia"),
        ("Reggaeton Party", "Reggaeton Party (Brighton)", "DUST"),
        ("Kepler", "Keplter", "Concorde 2"),
        ("$layyyter", "Slayyyter", "CHALK"),
    ]
    cases_different = [
        ("Brighton v Crystal Palace", "Brighton v Everton", "Amex Stadium"),
        ("The Amazons", "The Darkness", "CHALK"),
        ("DJ", "DJ Shadow", "Concorde 2"),
        ("Funny Women Volume 1", "Funny Women Volume 2", "Komedia"),
        ("Jazz Night", "Jazz Light", "Komedia"),
        ("Sergi Polo – LIVE in Brighton (in English)", "Sergi Polo – LIVE in Brighton (in Spanish)", "Komedia"),
    ]
    for a, b, v in cases_same:
        assert same_show(a, b, v), f"should match: {a!r} / {b!r} ({core_title(a, v)!r} / {core_title(b, v)!r})"
    for a, b, v in cases_different:
        assert not same_show(a, b, v), f"should not match: {a!r} / {b!r}"
    assert display_title("Kepler at Concorde 2 - Brighton", "Concorde 2") == "Kepler"
    assert display_title("Hybrid Minds | Brighton", "Concorde 2") == "Hybrid Minds"
    assert display_title("Reggaeton Party (Brighton)", "DUST") == "Reggaeton Party"
    assert display_title("Bathing Suits *Free Entry*", "Volks") == "Bathing Suits"
    assert same_show("Bathing Suits", "Bathing Suits *Free Entry*", "Volks")
    assert display_title("Brighton Soul Club", "Komedia") == "Brighton Soul Club"
    assert display_title("Bring Your Own Baby Comedy Brighton", "Komedia") == "Bring Your Own Baby Comedy Brighton"
    assert display_title("Lafs + Supports @ the Pipleline, Brighton", "The Pipeline") == "Lafs + Supports"
    return True


if __name__ == "__main__":
    _self_test()
    print("event_matching self-test passed")
