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
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"festivals.json"
TZ=ZoneInfo("Europe/London")
TODAY=datetime.now(TZ).date()
END=date(TODAY.year+1,12,31)
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
    "https://www.efestivals.co.uk/festivals/festivals.php?area=S&year=2027",
    "https://www.efestivals.co.uk/festivals/festivals.php?area=S&year=now",
]
MONTHS="Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
DATE_RE=re.compile(rf"\b(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:\s+\d{{4}})?|(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?)\b",re.I)
RANGE_RE=re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?(?:\s*[–-]\s*\d{{1,2}}(?:st|nd|rd|th)?)?\s+(?:{MONTHS})(?:\s+\d{{4}})?\b",re.I)
GENERIC={"festival","details","tickets","buy tickets","2027 tickets","check tickets","more","show more festivals","source checked","source check pending"}

def clean(s): return re.sub(r"\s+"," ",str(s or "")).strip()
def norm(s):
    s=re.sub(r"\b(?:19|20)\d{2}\b","",clean(s).lower())
    return re.sub(r"[^a-z0-9]+"," ",s).strip()
def parse_date_range(text, default_year):
    text=clean(text)
    cross=re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS})\s*[–-]\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS})(?:\s+(\d{{4}}))?\b",text,re.I)
    if cross:
        year=int(cross.group(5) or default_year)
        try:
            d1=dateparser.parse(f"{cross.group(1)} {cross.group(2)} {year}",dayfirst=True).date()
            d2=dateparser.parse(f"{cross.group(3)} {cross.group(4)} {year}",dayfirst=True).date()
            if d1 and d2:return d1,d2
        except Exception: pass
    m=re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*[–-]\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:\s+(\d{{4}}))?\b",text,re.I)
    if m:
        raw=m.group(0)
        try:
            d1=dateparser.parse(raw,dayfirst=True,default=datetime(default_year,1,1),fuzzy=True)
            month=re.search(rf"(?:{MONTHS})",raw,re.I).group(0)
            end_day=int(re.search(r"[–-]\s*(\d{1,2})",raw).group(1))
            d2=dateparser.parse(f"{end_day} {month} {d1.year}",dayfirst=True)
            if d1 and d2:return d1.date(),d2.date()
        except Exception: pass
    candidates=DATE_RE.findall(text)
    for raw in candidates:
        try:
            d=dateparser.parse(raw,dayfirst=True,default=datetime(default_year,1,1),fuzzy=True)
            if d:return d.date(),d.date()
        except Exception: pass
    return None,None
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
def valid_title(t):
    t=clean(t); return len(t)>=3 and len(t)<=180 and t.lower() not in GENERIC and not t.lower().startswith(("2026 edition","2027 tickets","check tickets"))
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
        title=clean(a.get_text(" ",strip=True))
        if not valid_title(title) or title.lower() in {"festivals in brighton","more details"}: continue
        parent=a
        for _ in range(7):
            parent=parent.parent
            if not parent: break
            text=clean(parent.get_text(" ",strip=True))
            if re.search(r"Type\s*:??\s*Festival\b",text,re.I) and len(text)<=3000: break
        if not parent: continue
        text=clean(parent.get_text(" ",strip=True))
        if not re.search(r"Type\s*:??\s*Festival\b",text,re.I): continue
        d,date_end=parse_date_range(text,TODAY.year)
        if not d: continue
        m=re.search(r"Address\s+(.+?)(?:\s+Telephone\b|\s+Type\b)",text,re.I)
        address=clean(m.group(1)) if m else ""
        if not is_brighton_location(address): continue
        detail=urljoin(url,a["href"])
        out.append({"title":title,"date":d.isoformat(),"date_end":(date_end or d).isoformat(),"location":address,"category":classify(text),"ticket_url":detail,"source":url})
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

def extract_fezzzy(html,url):
    soup=BeautifulSoup(html,"html.parser"); out=[]
    for h3 in soup.find_all(["h2","h3"]):
        title=clean(h3.get_text(" ",strip=True))
        if not valid_title(title): continue
        card=extract_card(h3)
        if card:
            e=card_data(card,title,TODAY.year,url)
            if e: out.append(e)
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

        parent=a
        for _ in range(5):
            parent=parent.parent
            if not parent: break
            text=clean(parent.get_text(" ",strip=True))
            if len(text)>=80 and len(text)<=900: break
        if not parent: continue
        text=clean(parent.get_text(" ",strip=True))
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
        title_norm=norm(e["title"])
        body_norm=norm(body)
        title_words=[w for w in title_norm.split() if len(w)>2]
        if not title_words or sum(w in body_norm.split() for w in title_words) < max(1,min(3,len(title_words))):
            return False
        d=date.fromisoformat(e["date"])
        date_tokens=(d.strftime("%d %B %Y"),d.strftime("%-d %B %Y"),d.strftime("%d %b %Y"),d.strftime("%-d %b %Y"))
        if not any(norm(x) in body_norm for x in date_tokens):
            parsed_start,_=parse_date_range(body,TODAY.year)
            if parsed_start != d: return False
        if is_brighton_location(e["location"]) and not is_brighton_location(body):
            return False
        return True
    except Exception:
        return False
    finally:
        await page.close()

def merge(items):
    chosen=[]
    for e in sorted(items,key=lambda x:(x["date"],x["title"])):
        if not (TODAY<=date.fromisoformat(e["date"])<=END): continue
        en=norm(e["title"]); el=location_key(e["location"])
        duplicate=False
        for old in chosen:
            if old["date"]!=e["date"]: continue
            on=norm(old["title"]); ol=location_key(old["location"])
            similar=(en==on or en in on or on in en or SequenceMatcher(None,en,on).ratio()>=0.88)
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
    result=[]
    for e in chosen:
        slug=re.sub(r"[^a-z0-9]+","-",norm(e["title"])).strip("-")[:100]
        e["id"]="festival:"+slug+":"+e["date"]
        e["location_display"]=e["location"]
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
                    found=extract_fezzzy(html,fezzy_url)
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
        finally:
            await browser.close()
    validated=[]
    for e in items:
        if await validate_candidate(browser,e):
            validated.append(e)
    print(f"Validated {len(validated)} of {len(items)} scraped candidates.")
    festivals=merge(validated)
    OUT.write_text(json.dumps({"updated":TODAY.isoformat(),"range_start":TODAY.isoformat(),"range_end":END.isoformat(),"sources":["VisitBrighton","Brighton Scoop","Fezzy","eFestivals"],"festivals":festivals},ensure_ascii=False,indent=2)+"\n")
    print(f"Published {len(festivals)} unique validated festivals.")
if __name__=="__main__": asyncio.run(main())
