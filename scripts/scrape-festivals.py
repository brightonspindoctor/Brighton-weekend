#!/usr/bin/env python3
"""Build the separate festival dataset for Brighton Weekend.

Primary discovery: Fezzy's UK festival directory.
Secondary discovery: eFestivals' UK music-festival directory.
The output is deliberately separate from events.json so festivals never enter
the normal event feed. User commitments still use the existing event_interest
table, with IDs prefixed "festival:".
"""
import asyncio, json, re
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse, urljoin
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"festivals.json"
CURATED=ROOT/"brighton-festivals.json"
TZ=ZoneInfo("Europe/London")
TODAY=datetime.now(TZ).date()
END=date(TODAY.year+1,12,31)
# Refuse to publish if a run finds fewer festivals than this, or loses more than half.
MIN_FESTIVALS=20
MAX_DROP=0.5
VISITBRIGHTON_SOURCES=[
    "https://www.visitbrighton.com/whats-on/festivals?p=1",
    "https://www.visitbrighton.com/whats-on/festivals?p=2",
]
BRIGHTONSCOOP_SOURCES=[
    "https://www.brightonscoop.co.uk/festivals-in-brighton",
]
FEZZY_SOURCES=[
    "https://fezzy.uk/uk-festivals-2027/",
    "https://fezzy.uk/search/",
    "https://fezzy.uk/collections/pop-festivals-uk-2026/",
    "https://fezzy.uk/collections/rock-festivals-uk-2026/",
    "https://fezzy.uk/collections/indie-festivals-uk-2026/",
    "https://fezzy.uk/collections/electronic-festivals-uk-2026/",
    "https://fezzy.uk/collections/electronic-edm-festivals-uk-2026/",
    "https://fezzy.uk/collections/indie-alt-festivals-2026/",
]
EFESTIVALS=[f"https://www.efestivals.co.uk/festivals/festivals.php?from={n}&year={TODAY.year+1}" for n in range(0,70,10)] + [
    f"https://www.efestivals.co.uk/festivals/festivals.php?area=S&year={TODAY.year+1}",
    "https://www.efestivals.co.uk/festivals/festivals.php?area=S&year=now",
]
MONTHS="Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
DATE_RE=re.compile(rf"\b(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:\s+\d{{4}})?|(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?)\b",re.I)
RANGE_RE=re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?(?:\s*[–-]\s*\d{{1,2}}(?:st|nd|rd|th)?)?\s+(?:{MONTHS})(?:\s+\d{{4}})?\b",re.I)
GENERIC={"festival","details","tickets","buy tickets","2027 tickets","check tickets","more","show more festivals","source checked","source check pending","read more","read less","places to stay","next","previous","list view","map view","grid view","plan your visit","things to do","what's on","work with us","submit event","site map","skip to main content","sign up for e-newsletter","translate","media","contact us","accommodation"}

def clean(s): return re.sub(r"\s+"," ",str(s or "")).strip()
def display_location(s):
    # Some listings put contact details in the address; show only the place.
    s=re.sub(r"\S+@\S+|https?://\S+|www\.\S+|\+?44 ?\(?0?\)? ?\d[\d ]{8,}\d|\b0\d{3,4} ?\d{3} ?\d{3,4}\b","",str(s or ""))
    return clean(re.sub(r"\s*,\s*(,\s*)+",", ",s)).strip(" ,")
def norm(s):
    s=re.sub(r"\b(?:19|20)\d{2}\b","",clean(s).lower())
    return re.sub(r"[^a-z0-9]+"," ",s).strip()
MONTH_NUM={m:i for i,m in enumerate(("jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"),1)}
_WD=r"(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s+)?"
_DAY=r"(\d{1,2})(?:st|nd|rd|th)?"
_SEP=r"\s*(?:[–—-]|to|until)\s*"
_YEAR=r"(?:,?\s+(\d{4}))?"
CROSS_MONTH_RE=re.compile(rf"\b{_WD}{_DAY}\s+({MONTHS})\.?{_YEAR}{_SEP}{_WD}{_DAY}\s+({MONTHS})\.?{_YEAR}\b",re.I)
SAME_MONTH_RE=re.compile(rf"\b{_WD}{_DAY}{_SEP}{_WD}{_DAY}\s+({MONTHS})\.?{_YEAR}\b",re.I)
SINGLE_RE=re.compile(rf"\b{_WD}{_DAY}\s+({MONTHS})\.?{_YEAR}\b",re.I)
US_SINGLE_RE=re.compile(rf"\b({MONTHS})\.?\s+{_DAY}{_YEAR}\b",re.I)

def _mk(year,month,day):
    try: return date(int(year),MONTH_NUM[month[:3].lower()],int(day))
    except (ValueError,KeyError): return None

def _settle(d1,d2,explicit_year):
    """Fix the year of a parsed range. A range that crosses New Year
    ('28 Dec - 2 Jan 2027') starts in the previous year; a date given without
    a year that has already passed is next year's edition."""
    if not d1 or not d2: return None,None
    if d2<d1:
        if explicit_year: d1=_mk(d1.year-1,d1.strftime("%b"),d1.day)
        else: d2=_mk(d2.year+1,d2.strftime("%b"),d2.day)
        if not d1 or not d2: return None,None
    if not explicit_year and d2<TODAY:
        d1=_mk(d1.year+1,d1.strftime("%b"),d1.day); d2=_mk(d2.year+1,d2.strftime("%b"),d2.day)
        if not d1 or not d2: return None,None
    return d1,d2

def iter_date_ranges(text,default_year):
    """Yield every (start, end) date range found in text, in order of appearance.
    Dates are built from the matched parts directly; a fuzzy parser reads the
    first day of '5-7 June' as the year 2005."""
    text=clean(text); found=[]
    for m in CROSS_MONTH_RE.finditer(text):
        y2=m.group(6); y1=m.group(3) or y2 or default_year
        found.append((m.start(),m.end(),_settle(_mk(y1,m.group(2),m.group(1)),_mk(y2 or y1,m.group(5),m.group(4)),bool(m.group(3) or m.group(6)))))
    for m in SAME_MONTH_RE.finditer(text):
        y=m.group(4) or default_year
        found.append((m.start(),m.end(),_settle(_mk(y,m.group(3),m.group(1)),_mk(y,m.group(3),m.group(2)),bool(m.group(4)))))
    for rx,order in ((SINGLE_RE,(1,2,3)),(US_SINGLE_RE,(2,1,3))):
        for m in rx.finditer(text):
            day,month,year=(m.group(i) for i in order)
            d=_mk(year or default_year,month,day)
            found.append((m.start(),m.end(),_settle(d,d,bool(year))))
    # Prefer the longest match at each position, and drop matches inside another.
    found.sort(key=lambda x:(x[0],-(x[1]-x[0])))
    last_end=-1
    for start,end,(d1,d2) in found:
        if start<last_end: continue
        last_end=end
        if d1 and d2: yield d1,d2

def parse_date_range(text, default_year):
    return next(iter_date_ranges(text,default_year),(None,None))
def location_key(s):
    s=norm(s)
    aliases={"brighton and hove":"brighton","brighton & hove":"brighton","east sussex":"east sussex"}
    return aliases.get(s,s)
def classify(text):
    h=clean(text).lower()
    if any(k in h for k in ("wellness","wellbeing","yoga","meditation","holistic","self-care","spiritual")): return "Wellness"
    if any(k in h for k in ("food","drink","sausage","cider","gastronomy","chef","culinary")): return "Food & Drink"
    if any(k in h for k in ("family","kids","children","parent")): return "Family"
    if any(k in h for k in ("film","cinema","documentary")): return "Film"
    if any(k in h for k in ("comedy","stand-up","stand up","comedian")): return "Comedy"
    if any(k in h for k in ("arts","art","theatre","theater","literature","poetry","culture","performance","ideas","reenactment","larp")): return "Arts & Culture"
    if any(k in h for k in ("running","trail","cycling","equestrian","horse trials","motorsport","sport","outdoor","adventure","surf")): return "Sport & Outdoor"
    if any(k in h for k in ("music","rock","pop","indie","electronic","folk","jazz","blues","metal","dance","dj","house","techno","punk","ska","soul","r&b")): return "Music"
    return "Other"
# Text that is part of the page layout, not a festival name: month/day group
# headings ("April", "June 2027") and buttons ("More Details", "Book now").
MONTH_DAY=r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs(?:day)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
CTA=r"(?:more details|more info(?:rmation)?|find out more|view (?:details|event|festival|more)|see (?:details|more)|learn more|book now|buy now|book tickets?|buy tickets?|get tickets?|details|info|tickets?)"
def is_layout_text(t):
    h=norm(t)
    # Only month/day names and numbers ("April", "June 2027", "Sat 14 June"), or a button label.
    return bool(re.fullmatch(rf"(?:(?:{MONTH_DAY}|\d{{1,4}}(?:st|nd|rd|th)?)\s*)+",h) or re.fullmatch(CTA,h))
def title_from_url(href):
    """'/festival/all-points-east/' -> 'All Points East' (used when a card's heading is a month)."""
    slug=urlparse(href).path.rstrip("/").split("/")[-1]
    slug=re.sub(r"-p\d+$","",slug)
    words=[w for w in re.split(r"[-_]+",slug) if w]
    if not words: return ""
    small={"and","of","the","on","in","at","by","for","a"}
    return " ".join(w.capitalize() if i==0 or w not in small else w for i,w in enumerate(words))

def valid_title(t):
    t=clean(t); h=t.lower()
    if is_layout_text(t): return False
    if not (len(t)>=4 and len(t)<=180): return False
    if h in GENERIC or h.startswith(("2026 edition","2027 tickets","check tickets")): return False
    if "@" in t or re.fullmatch(r"[a-z]-[a-z](?: [a-z]-[a-z])*",h): return False
    return bool(re.search(r"[a-z]{3}",h))
def extract_card(h3):
    node=h3
    for _ in range(6):
        node=node.parent
        if not node: return None
        text=clean(node.get_text(" ",strip=True))
        if 50<=len(text)<=1800 and node.find("a",href=True): return node
    return None
def card_data(card,title,default_year,source):
    text=clean(card.get_text(" ",strip=True))
    d,date_end=parse_date_range(text,default_year)
    if not d: return None
    lines=[clean(x) for x in card.stripped_strings if clean(x)]
    idx=next((i for i,x in enumerate(lines) if norm(x)==norm(title)),0)
    location=""
    for x in lines[idx+1:idx+7]:
        lx=x.lower()
        if x and len(x)<80 and not DATE_RE.search(x) and not any(y in lx for y in ("featured","hidden gem","festival","cap","tickets","edition","source checked","source check pending","details")):
            location=x; break
    if not location:
        location="UK"
    ticket=""
    detail=""
    for a in card.find_all("a",href=True):
        label=clean(a.get_text(" ",strip=True)).lower()
        href=urljoin(source,a["href"])
        if "ticket" in label and not ticket: ticket=href
        if ("details" in label or "/festival/" in href) and not detail: detail=href
    if not ticket: ticket=detail
    return {"title":title,"date":d.isoformat(),"date_end":date_end.isoformat(),"location":location,"category":classify(text),"ticket_url":ticket or detail or source,"source":source}

def is_brighton_location(location):
    h=clean(location).lower()
    return any(k in h for k in ("brighton","hove","stanmer park","preston park","east brighton","madeira drive","banjo groyne"))

def extract_visitbrighton(html,url):
    soup=BeautifulSoup(html,"html.parser"); out=[]
    for a in soup.find_all("a",href=True):
        href=a.get("href","")
        if not re.search(r"/whats-on/[^/?#]+-p\d+",href,re.I): continue
        title=clean(a.get_text(" ",strip=True))
        if not valid_title(title): continue
        # Climb to this listing's own card. Stop (and skip the link) as soon as
        # the block holds a second listing: a date or address found beyond that
        # point belongs to a neighbouring card.
        parent=a; card=None
        for _ in range(5):
            parent=parent.parent
            if not parent: break
            listings={x.get("href","").split("?")[0] for x in parent.find_all("a",href=True) if re.search(r"/whats-on/[^/?#]+-p\d+",x.get("href",""),re.I)}
            if len(listings)>1: break
            text=clean(parent.get_text(" ",strip=True))
            if 80 <= len(text) <= 1800 and DATE_RE.search(text): card=parent; break
        if card is None: continue
        text=clean(card.get_text(" ",strip=True))
        d,date_end=parse_date_range(text,TODAY.year)
        if not d: continue
        m=re.search(r"Address\s+(.+?)(?:\s+Telephone\b|\s+Type\b|\s+Website\b)",text,re.I)
        address=clean(m.group(1)) if m else ""
        if not is_brighton_location(address): continue
        detail=urljoin(url,href)
        out.append({"title":title,"date":d.isoformat(),"date_end":(date_end or d).isoformat(),"location":address,"category":classify(text),"ticket_url":detail,"source":url,"detail_url":detail})
    return out

def extract_brightonscoop(html,url):
    soup=BeautifulSoup(html,"html.parser"); out=[]; current_year=TODAY.year
    for node in soup.find_all(["h2","h3","p","li"]):
        text=clean(node.get_text(" ",strip=True))
        if re.fullmatch(r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}",text,re.I):
            current_year=int(re.search(r"20\d{2}",text).group()); continue
        if "|" not in text: continue
        parts=[clean(x) for x in text.split("|")]
        if len(parts)<2: continue
        title=re.sub(r"^[^A-Za-z0-9]+","",parts[0]).strip()
        if not valid_title(title) or "festival" not in title.lower(): continue
        location=parts[1]
        if not is_brighton_location(location): continue
        d,date_end=parse_date_range(text,current_year)
        if not d: continue
        link=""
        for a in node.find_all("a",href=True):
            label=clean(a.get_text(" ",strip=True)).lower()
            if "ticket" in label or "info" in label:
                link=urljoin(url,a["href"]); break
        if not link: continue
        out.append({"title":title,"date":d.isoformat(),"date_end":(date_end or d).isoformat(),"location":location,"category":classify(text),"ticket_url":link,"source":url,"detail_url":link})
    return out

def extract_fezzy(html,url):
    soup=BeautifulSoup(html,"html.parser"); out=[]
    for heading in soup.find_all(["h2","h3","button"]):
        title=clean(heading.get_text(" ",strip=True))
        layout=is_layout_text(title)  # e.g. a month group heading such as "April"
        if not layout and not valid_title(title): continue
        card=extract_card(heading)
        if not card: continue
        detail=None
        for a in card.find_all("a",href=True):
            href=a.get("href","")
            if re.search(r"/festival/[^/?#]+/?$",href,re.I):
                detail=urljoin(url,href); break
        if not detail: continue
        if layout:
            # The heading was a month, so the real name is the festival's own
            # address. merge() folds it into the proper record if there is one.
            title=title_from_url(detail)
            if not valid_title(title): continue
            # Its date and place came from the month block, not this festival:
            # validate_candidate() re-reads the dates from the festival's own page.
        e=card_data(card,title,TODAY.year,url)
        if e:
            if layout: e["_derived"]=True
            e["detail_url"]=detail
            e["ticket_url"]=detail
            out.append(e)
    return out
def extract_efestivals(html,url):
    # eFestivals listing cards contain the title, date range, location and ticket
    # link in one compact text block. Keep only links that actually sit inside
    # a dated festival listing so navigation/footer links cannot become records.
    soup=BeautifulSoup(html,"html.parser"); out=[]
    for a in soup.find_all("a",href=True):
        title=clean(a.get_text(" ",strip=True))
        if not valid_title(title) or len(title)>120: continue
        # eFestivals exposes lots of navigation links; festival names generally
        # sit in links whose parent block also contains a date and ticket text.

        parent=a; card=None
        for _ in range(5):
            parent=parent.parent
            if not parent: break
            text=clean(parent.get_text(" ",strip=True))
            if len(text)>900: break
            if len(text)>=80: card=parent; break
        if card is None: continue
        text=clean(card.get_text(" ",strip=True))
        d,date_end=parse_date_range(text,TODAY.year+1)
        if not d: continue
        # eFestivals puts the location immediately after the dated portion.
        location="UK"
        date_tail=re.search(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+to\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}",text,re.I)
        if date_tail:
            tail=text[date_tail.end():]
            candidate=re.split(r"\s+(?:£\s?\d|not yet on sale|sold out|early bird|tier \d|varies by|tickets? go-|registration|on sale|free)",tail,1,flags=re.I)[0]
            candidate=clean(candidate)
            if candidate and len(candidate)<180: location=candidate
        ticket=urljoin(url,a["href"])
        if not ticket or not re.search(r"/festivals/[^/]+/|tickets|ticket", a.get("href",""), re.I): continue
        out.append({"title":title,"date":d.isoformat(),"date_end":(date_end or d).isoformat(),"location":location,"category":"Music","ticket_url":ticket,"source":url,"detail_url":ticket})
    return out
async def validate_candidate(browser,e):
    url=e.get("detail_url") or e.get("ticket_url")
    if not url or not re.match(r"^https?://",url,re.I): return False
    page=await browser.new_page()
    page.set_default_timeout(15000)
    try:
        response=await page.goto(url,wait_until="domcontentloaded",timeout=20000)
        if not response or response.status >= 400: return False
        try: await page.wait_for_load_state("networkidle",timeout=5000)
        except PlaywrightTimeoutError: pass
        body=clean(await page.locator("body").inner_text())
        if e.get("_derived"):
            # Named from its address because the card heading was a month: take
            # the dates from the festival's own page (first upcoming range).
            found=next(((a,b) for a,b in iter_date_ranges(body,TODAY.year) if a and TODAY<=a<=END),None)
            if not found: return False
            e["date"]=found[0].isoformat(); e["date_end"]=(found[1] or found[0]).isoformat()
        title_norm=norm(e["title"])
        body_norm=norm(body)
        title_words=[w for w in title_norm.split() if len(w)>2]
        if not title_words or sum(w in body_norm.split() for w in title_words) < max(1,min(3,len(title_words))):
            return False
        d=date.fromisoformat(e["date"])
        date_tokens=(d.strftime("%d %B %Y"),d.strftime("%-d %B %Y"),d.strftime("%d %b %Y"),d.strftime("%-d %b %Y"))
        if not any(norm(x) in body_norm for x in date_tokens):
            default_year=d.year
            if not any(start==d for start,_ in iter_date_ranges(body,default_year)): return False
        if is_brighton_location(e["location"]) and not is_brighton_location(body):
            return False
        return True
    except Exception:
        return False
    finally:
        await page.close()

def add_curated(festivals):
    """Hand-confirmed Brighton festivals (brighton-festivals.json) are always
    published until they end, replacing any scraped copy of the same festival.
    Before this, festivals added by hand to festivals.json were wiped out by the
    next daily refresh."""
    try: curated=json.loads(CURATED.read_text()).get("festivals",[])
    except Exception as exc:
        print("Curated festivals unavailable:",exc); return festivals
    keep=[]
    for c in curated:
        try: d=date.fromisoformat(c["date"]); de=date.fromisoformat(c.get("date_end") or c["date"])
        except Exception: continue
        if de<TODAY or d>END: continue
        keep.append(dict(c,date_end=de.isoformat(),source=c.get("source") or c.get("detail_url") or c.get("ticket_url")))
    names={norm(c["title"]) for c in keep}; ids={c["id"] for c in keep}
    out=[f for f in festivals if norm(f["title"]) not in names and f["id"] not in ids]
    print(f"Curated Brighton festivals: {len(keep)} published, {len(festivals)-len(out)} scraped copies replaced")
    return sorted(out+keep,key=lambda x:(x["date"],x["title"]))

def merge(items):
    chosen=[]
    items=[e for e in items if not is_layout_text(e.get("title",""))]
    # One record per festival page, preferring a properly read card over one
    # named from its address.
    by_page={}
    for e in sorted(items,key=lambda x:bool(x.get("_derived"))):
        key=(e.get("detail_url") or "").split("#")[0].rstrip("/") or id(e)
        if key not in by_page: by_page[key]=e
    items=list(by_page.values())
    for e in items: e.pop("_derived",None)
    for e in sorted(items,key=lambda x:(x["date"],x["title"])):
        if not (TODAY<=date.fromisoformat(e["date"])<=END): continue
        en=norm(e["title"]); el=location_key(e["location"])
        duplicate=False
        for old in chosen:
            if old["date"]!=e["date"]: continue
            on=norm(old["title"]); ol=location_key(old["location"])
            # Whole-word containment only, so "Folk Fest 2" never swallows "Folk Fest 22".
            short,long_=sorted((en,on),key=len)
            similar=(en==on or (len(short.split())>=2 and f" {short} " in f" {long_} ") or (re.sub(r"\D","",en)==re.sub(r"\D","",on) and SequenceMatcher(None,en,on).ratio()>=0.92))
            same_loc=(el=="uk" or ol=="uk" or el==ol or SequenceMatcher(None,el,ol).ratio()>=0.8)
            if similar and same_loc:
                duplicate=True
                # Prefer a real ticket link over an aggregator detail page.
                if date.fromisoformat(e.get("date_end",e["date"])) > date.fromisoformat(old.get("date_end",old["date"])):
                    old["date_end"]=e["date_end"]
                if "efestivals" in old["ticket_url"] and "efestivals" not in e["ticket_url"]:
                    old.update({"ticket_url":e["ticket_url"],"source":e["source"]})
                break
        if not duplicate: chosen.append(e)
    result=[]; used=set()
    for e in chosen:
        slug=re.sub(r"[^a-z0-9]+","-",norm(e["title"])).strip("-")[:100]
        e["id"]="festival:"+slug+":"+e["date"]
        if e["id"] in used:
            loc=re.sub(r"[^a-z0-9]+","-",location_key(e["location"])).strip("-")[:40] or "x"
            e["id"]="festival:"+slug+"-"+loc+":"+e["date"]
        n=2
        while e["id"] in used:
            e["id"]=f"festival:{slug}-{n}:{e['date']}"; n+=1
        used.add(e["id"])
        e.setdefault("detail_url",e["ticket_url"])
        e["location_display"]=display_location(e["location"])
        result.append(e)
    return result
async def fetch_page(browser,url):
    page=await browser.new_page(); page.set_default_timeout(25000)
    try:
        await page.goto(url,wait_until="domcontentloaded",timeout=30000)
        try: await page.wait_for_load_state("networkidle",timeout=10000)
        except PlaywrightTimeoutError: pass
        for _ in range(20):
            btn=page.get_by_role("button",name=re.compile("show more festivals",re.I))
            if await btn.count()==0: break
            try:
                await btn.first.click(timeout=3000); await page.wait_for_timeout(700)
            except Exception: break
        return await page.content()
    finally: await page.close()
async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        items=[]
        try:
            for url in VISITBRIGHTON_SOURCES:
                try:
                    html=await fetch_page(browser,url)
                    found=extract_visitbrighton(html,url)
                    items+=found
                    print("VisitBrighton",url,"candidates:",len(found))
                except Exception as exc:
                    print("VisitBrighton failed:",url,exc)
            for url in BRIGHTONSCOOP_SOURCES:
                try:
                    html=await fetch_page(browser,url)
                    found=extract_brightonscoop(html,url)
                    items+=found
                    print("Brighton Scoop",url,"candidates:",len(found))
                except Exception as exc:
                    print("Brighton Scoop failed:",url,exc)
            for fezzy_url in FEZZY_SOURCES:
                try:
                    html=await fetch_page(browser,fezzy_url)
                    found=extract_fezzy(html,fezzy_url)
                    items+=found
                    print("Fezzy",fezzy_url,"candidates:",len(found))
                except Exception as exc:
                    print("Fezzy failed:",fezzy_url,exc)
            for url in EFESTIVALS:
                try:
                    html=await fetch_page(browser,url)
                    found=extract_efestivals(html,url)
                    items+=found
                    print("eFestivals",url,"candidates:",len(found))
                except Exception as exc:
                    print("eFestivals failed:",url,exc)
            sem=asyncio.Semaphore(8)
            async def checked(e):
                async with sem:
                    return e if await validate_candidate(browser,e) else None
            checked_items=await asyncio.gather(*(checked(e) for e in items))
            validated=[e for e in checked_items if e]
            print(f"Validated {len(validated)} of {len(items)} scraped candidates.")
            festivals=add_curated(merge(validated))
            existing=0
            try: existing=len(json.loads(OUT.read_text()).get("festivals",[]))
            except Exception: pass
            if len(festivals)<MIN_FESTIVALS:
                raise SystemExit(f"Only {len(festivals)} festivals validated (minimum {MIN_FESTIVALS}); keeping the existing festivals.json")
            if existing and len(festivals)<existing*MAX_DROP:
                raise SystemExit(f"Festival count fell from {existing} to {len(festivals)}; keeping the existing festivals.json")
            OUT.write_text(json.dumps({"updated":TODAY.isoformat(),"range_start":TODAY.isoformat(),"range_end":END.isoformat(),"sources":["VisitBrighton","Brighton Scoop","Fezzy","eFestivals"],"festivals":festivals},ensure_ascii=False,indent=2)+"\n")
            print(f"Published {len(festivals)} unique validated festivals.")
        finally:
            await browser.close()
if __name__=="__main__": asyncio.run(main())
