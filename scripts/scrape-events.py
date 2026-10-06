#!/usr/bin/env python3
"""Refresh Brighton Weekend events from configured venue sites."""
import asyncio, json, re, sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

ROOT=Path(__file__).resolve().parents[1]
# Sources marked "disabled" stay listed (the discovery scraper still recognises
# their venue) but are not fetched.
SOURCES=[s for s in json.loads((ROOT/'event-sources.json').read_text()) if not s.get('disabled')]
OUT=ROOT/'events.json'
TZ=ZoneInfo('Europe/London')
NOW=datetime.now(TZ)
RANGE_START=NOW.date(); RANGE_END=(NOW+timedelta(days=280)).date()
MONTHS=r'Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?'
# '10 Oct 2026', 'October 10th, 2026' and UK numeric dates such as '10/10/26'.
DATE_RE=re.compile(rf'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\.?\s*(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s*(?:\d{{4}})?|(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?|\d{{1,2}}/\d{{1,2}}/(?:\d{{4}}|\d{{2}}))\b',re.I)
TIME_RE=re.compile(r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b',re.I)
CATEGORIES={'Comedy':['comedy','comedian','stand-up','stand up','laughs'],'Club':['club','dj','dnb','drum & bass','rave','techno','house night','party'],'Theatre':['theatre','theater','play','musical','west end'],'Dance':['dance','ballet','contemporary dance'],'Family':['family','kids','children','storytelling','baby'],'Talk':['talk','in conversation','lecture','spoken word','author'],'Sport':['football','boxing','wrestling','sport','racecourse'],'Music':['gig','live','band','concert','tour','festival','dj set','orchestra','singer']}
GENERIC_TITLES={'comedy','classical music','music','talks & debate','talks and debate','dance','theatre','family',"what's on",'events','upcoming events','get tickets','buy tickets','book tickets','learn more','more info','more info & tickets','find out more','event details','sold out','on sale','on sale today','tickets','read more','view event'}
CTA_PREFIXES=('get tickets','get ticket','buy tickets','buy ticket','book tickets','book ticket','book now','learn more','more info','more details','find out more','event details','on sale','sold out','sign up','subscribe','join our','join the mailing','newsletter','mailing list')

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def valid_title(title):
    t=clean(title); low=t.lower()
    if not t or low in GENERIC_TITLES:return False
    if any(low.startswith(p) for p in CTA_PREFIXES):return False
    if len(t)<3 or len(t)>180:return False
    if not re.search(r'[^\W\d_]{2}',low):return False  # a year or number on its own, e.g. "2026"
    return True

def title_key(title): return re.sub(r'[^a-z0-9]+',' ',clean(title).lower()).strip()
TRAILING_DATE=re.compile(rf'\s*(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?\s+)?\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\.?\s+\d{{4}}\b.*$',re.I)
def strip_listing_date(title):
    """Drop a trailing "Fri 25 Sep 2026 8:00 PM ( Doors: 7:00 PM )" from a title."""
    cleaned=TRAILING_DATE.sub('',clean(title)).strip(' -–|·')
    return cleaned if len(cleaned)>=3 else clean(title)
VENUE_ALIASES={'Brighton Dome - Concert Hall':'Brighton Dome'}  # same as prepare-events.py and index.html
def canonical_venue(v): return VENUE_ALIASES.get(v,v)
def event_key(e): return (canonical_venue(e.get('venue','')).lower(),e.get('date',''),title_key(e.get('title','')),e.get('time') or '')
def day_key(e): return (canonical_venue(e.get('venue','')).lower(),e.get('date',''))
def same_show(a,b):
    """True when two titles on the same venue and day are the same show, e.g.
    'Wot Italian?' and 'Wot Italian? Boothby Graffoe, Antonio Forcione'."""
    ka,kb=title_key(a),title_key(b)
    if not ka or not kb:return False
    if ka==kb or ka.startswith(kb+' ') or kb.startswith(ka+' '):return True
    from difflib import SequenceMatcher
    return SequenceMatcher(None,ka,kb).ratio()>=0.85
def swapped_date(iso):
    """2026-11-10 -> 2026-10-11 (for repairing records saved with day and month swapped)."""
    try:
        y,m,d=(int(x) for x in iso.split('-'))
        return None if d>12 or d==m else f'{y:04d}-{d:02d}-{m:02d}'
    except Exception:return None
# Drop an event only after its venue has stopped listing it for this many days
# in a row (while the venue's own site was loading fine). One flaky night must
# not remove real events.
STALE_DAYS=3
def fuller_title(a,b):
    """Return the fuller title when one title is a clear prefix of the other."""
    ka,kb=title_key(a),title_key(b)
    if ka==kb:return a if len(a)>=len(b) else b
    if ka and kb and (ka.startswith(kb+' ') or kb.startswith(ka+' ')):
        return a if len(ka)>len(kb) else b
    return None

def prefer_fuller_titles(events):
    """Collapse same-venue/date duplicates where one title extends the other."""
    groups={}
    for e in events: groups.setdefault((e.get('venue','').lower(),e.get('date',''),e.get('time') or ''),[]).append(e)
    kept=[]
    for group in groups.values():
        group=sorted(group,key=lambda e:len(title_key(e.get('title',''))),reverse=True)
        chosen=[]
        for e in group:
            duplicate=False
            for existing in chosen:
                if fuller_title(existing.get('title',''),e.get('title','')):
                    duplicate=True;break
            if not duplicate:chosen.append(e)
        kept.extend(chosen)
    return kept

# ---- Choosing the ticket link -------------------------------------------
# An event card on a listings page usually holds several links. Pick the one
# that gets people closest to buying: a ticketing site or a "Tickets"/"Book"
# button first, then the link whose text is the event's name (its own page).
# Never the listings page itself, the venue's homepage or social media.
TICKET_HOSTS=('seetickets','ticketmaster','skiddle','dice.fm','eventbrite','ticketweb','gigantic','fatsoma',
              'ra.co','residentadvisor','wegottickets','ents24','atgtickets','ticketsource','tickettailor',
              'universe.com','fixr','tixr','billetto','ticketline','eventim','ticketsolve','spektrix',
              'kililive','stagedates','ticketebo','ticketsellers','designmynight','headfirstbristol')
SKIP_HOSTS=('facebook.','instagram.','twitter.','x.com','tiktok.','youtube.','youtu.be','spotify.','soundcloud.',
            'google.','apple.com','linktr.ee','mailchimp','wa.me','whatsapp','threads.net','bsky.')
LISTING_SLUGS={'whats-on','whatson','events','event','shows','listings','calendar','gigs','club','tickets',
               'comedy','music','search','programme','all-events','upcoming'}
def is_listing_or_home(u,page_url=''):
    p=urlparse(u);path=p.path.strip('/')
    if not path:return True
    if page_url and u.split('#')[0].rstrip('/')==page_url.split('#')[0].rstrip('/'):return True
    return path.split('/')[-1].lower() in LISTING_SLUGS and p.query==''
def best_link(node,page_url,title):
    """Return the best ticket/event link inside an event card, or None."""
    scored={}
    for a in node.find_all('a',href=True):
        raw=a['href'].strip()
        if not raw or raw.startswith(('#','mailto:','tel:','javascript:','sms:')):continue
        u=urljoin(page_url,raw).split('#')[0];p=urlparse(u);host=p.netloc.lower()
        if p.scheme not in ('http','https') or any(h in host for h in SKIP_HOSTS):continue
        ticket_site=any(h in host for h in TICKET_HOSTS)
        if is_listing_or_home(u,page_url) and not (ticket_site and p.path.strip('/')):continue
        text=clean(a.get_text(' ',strip=True)).lower() or clean(a.get('aria-label','')).lower() or clean(a.get('title','')).lower()
        score=1
        if ticket_site:score+=4
        if re.search(r'\b(tickets?|book(?:ing)?|buy)\b',text):score+=3
        if title and title_key(text) and (title_key(text)==title_key(title) or title_key(title) in title_key(text)):score+=2
        scored[u]=max(score,scored.get(u,0))
    if not scored:return None
    best=max(scored,key=scored.get)
    # A block holding many different event links is a whole listing, not one
    # event's card: only trust a link there if it is clearly this event's.
    if len(scored)>4 and scored[best]<3:return None
    return best

TITLE_CLASS=re.compile(r'(^|[-_ ])(title|name|headline|heading|artist)([-_ ]|$)',re.I)
def card_title(node,page_url):
    """Title and link for an event card that has no h1-h4 heading. Tries, in
    order: an element styled as a title (class 'title', 'name'...), h5/h6 or
    bold text, the text of a link to the event's own page or a ticketing site,
    and finally the event page's address ('/event/the-wanted-2-0'). Blocks that
    link to several different events are skipped: each event's own card is read
    separately, and a whole list must not become one event."""
    cands=[]
    for a in node.find_all('a',href=True):
        raw=a['href'].strip()
        if not raw or raw.startswith(('#','mailto:','tel:','javascript:')):continue
        u=urljoin(page_url,raw).split('#')[0];p=urlparse(u);host=p.netloc.lower()
        if p.scheme not in ('http','https') or any(h in host for h in SKIP_HOSTS) or is_listing_or_home(u,page_url):continue
        ticket_site=any(h in host for h in TICKET_HOSTS)
        if not ticket_site and len([x for x in p.path.split('/') if x])<2:continue  # '/about', '/contact'
        cands.append((u,clean(a.get_text(' ',strip=True)),ticket_site))
    if len({u for u,_,_ in cands})>3:return '',page_url
    link=next((u for u,_,_ in cands),None)
    el=node.find(class_=TITLE_CLASS) or node.find(['h5','h6']) or node.find(['strong','b'])
    t=clean(el.get_text(' ',strip=True)) if el else ''
    if valid_title(t) and not DATE_RE.fullmatch(t):return t,(link or page_url)
    for u,text,_ in cands:
        if valid_title(text):return text,u
    for u,_,ticket_site in cands:
        t=slug_title(u)
        if not ticket_site and valid_title(t):return t,u
    return '',page_url

def offer_url(raw):
    offers=raw.get('offers')
    for o in (offers if isinstance(offers,list) else [offers]):
        if isinstance(o,dict) and re.match(r'https?://',str(o.get('url',''))):return o['url']
    return None

def slug_title(url):
    slug=urlparse(url).path.rstrip('/').split('/')[-1]
    slug=re.sub(r'^[A-Za-z0-9_-]+-', '', slug)
    slug=re.sub(r'[-_]+',' ',slug).strip()
    if not slug:return ''
    return clean(slug.title())

def category(title,text=''):
    hay=clean(f'{title} {text}').lower()
    for cat,words in CATEGORIES.items():
        if any(w in hay for w in words): return cat
    return 'Other'

# A listing that leaves out the year ("Fri 15 Jan") means the next one: in
# October, "15 Jan" is January NEXT year, not a date that has already passed.
# Only dates well in the past are moved on, so a stale "last week" listing is
# not turned into a phantom event next year.
ROLLOVER_DAYS=60
def roll_year_forward(dt,text):
    if re.search(r'\b\d{4}\b',str(text)) or dt.date()>=(NOW-timedelta(days=ROLLOVER_DAYS)).date():return dt
    try:return dt.replace(year=dt.year+1)
    except ValueError:return dt.replace(year=dt.year+1,day=28)  # 29 Feb

def parse_dt(value):
    if not value:return None
    try:
        v=clean(str(value))
        # ISO dates (2026-12-10, as in structured event data and the page-text
        # route below) are year-month-day. dayfirst=True makes dateutil read them
        # as year-DAY-month, swapping day and month whenever the day is 12 or
        # under, so day-first reading is only used for text such as "10/12/2026".
        iso=bool(re.match(r'\d{4}-\d{1,2}-\d{1,2}',v))
        dt=dateparser.parse(v,dayfirst=not iso,yearfirst=iso,fuzzy=True,default=datetime(NOW.year,1,1))
        if not dt:return None
        dt=roll_year_forward(dt,value)
        return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
    except Exception:return None

def normalise(raw,venue,page_url):
    title=strip_listing_date(raw.get('name') or raw.get('title')); start_raw=raw.get('startDate') or raw.get('start_date') or raw.get('date'); start=parse_dt(start_raw)
    if not valid_title(title) or not start or not (RANGE_START<=start.date()<=RANGE_END):return None
    blob=clean(' '.join(str(raw.get(k,'')) for k in ('name','description','status'))).lower()
    if any(x in blob for x in ('cancelled','canceled','postponed','event cancelled')):return None
    end=parse_dt(raw.get('endDate') or raw.get('end_date'))
    # Closest to the tickets first: the ticket offer, then the event's own page,
    # and the listings page only as a last resort.
    candidates=[offer_url(raw),raw.get('url')]
    url=next((urljoin(page_url,c) for c in candidates if c and not is_listing_or_home(urljoin(page_url,c),page_url)),None) or urljoin(page_url,raw.get('url') or page_url)
    ident=re.sub(r'[^a-z0-9]+','-',f'{start.date()}-{venue}-{title}'.lower()).strip('-')[:180]
    return {'id':ident,'title':title,'date':start.date().isoformat(),'venue':venue,'source':'venue','time':start.strftime('%H:%M') if start_raw and re.search(r'T|\d{1,2}:\d{2}|am|pm',str(start_raw),re.I) else '','finish_time':end.strftime('%H:%M') if end else '','category':category(title,raw.get('description','')),'ticket_url':url}

def location_text(obj):
    """All the names and address text in a schema.org event's location, lower case."""
    parts=[];stack=[obj.get('location')]
    while stack:
        x=stack.pop()
        if isinstance(x,list):stack.extend(x)
        elif isinstance(x,dict):stack.extend(v for k,v in x.items() if k in ('name','address','streetAddress','addressLocality','postalCode'))
        elif isinstance(x,str):parts.append(x)
    return clean(' '.join(parts)).lower()

def jsonld_events(html,venue,page_url,match_location=None):
    """Events from schema.org data. With match_location (used for ticketing-site
    pages that can also show other venues' events), only events whose location
    mentions it are kept."""
    soup=BeautifulSoup(html,'html.parser');out=[]
    for tag in soup.find_all('script',attrs={'type':re.compile(r'ld\+json',re.I)}):
        try:data=json.loads(tag.string or tag.get_text())
        except Exception:continue
        stack=data if isinstance(data,list) else [data]
        while stack:
            obj=stack.pop()
            if isinstance(obj,list):stack.extend(obj);continue
            if not isinstance(obj,dict):continue
            if isinstance(obj.get('@graph'),list):stack.extend(obj['@graph'])
            typ=obj.get('@type','');types=typ if isinstance(typ,list) else [typ]
            if any(str(t).lower()=='event' or str(t).lower().endswith('event') for t in types):
                if match_location and match_location.lower() not in location_text(obj):continue
                e=normalise(obj,venue,page_url)
                if e:out.append(e)
    return out

def dom_events(html,venue,page_url,detail_only=False):
    soup=BeautifulSoup(html,'html.parser');out=[]
    for node in soup.find_all(['article','li','div'],limit=15000):
        text=clean(node.get_text(' ',strip=True))
        if len(text)<12 or len(text)>1000:continue
        dm=DATE_RE.search(text)
        if not dm:continue
        dt=parse_dt(dm.group(1))
        if not dt or not (RANGE_START<=dt.date()<=RANGE_END):continue
        links=node.find_all('a',href=True)
        if detail_only:links=[a for a in links if '/whats-on/' in urlparse(urljoin(page_url,a['href'])).path]
        h=node.find(['h1','h2','h3','h4'])
        title=clean(h.get_text(' ',strip=True)) if h else ''
        href=page_url
        if not valid_title(title):
            title=''
            for a in links:
                t=clean(a.get_text(' ',strip=True)); u=urljoin(page_url,a['href'])
                if valid_title(t) and '/whats-on/' in urlparse(u).path:
                    title=t;href=u;break
            if not title and links:
                for a in links:
                    u=urljoin(page_url,a['href']); candidate=slug_title(u)
                    if valid_title(candidate) and '/whats-on/' in urlparse(u).path:
                        title=candidate;href=u;break
        if not valid_title(title) and not detail_only:
            title,href=card_title(node,page_url)
            if valid_title(title):href=best_link(node,page_url,title) or href  # a ticket link in the card beats the event page
        if not valid_title(title):continue
        if href==page_url and not detail_only:
            href=best_link(node,page_url,title) or page_url
        # Ignore "Doors: 7pm" style times; they are not start or finish times.
        timed_text=re.sub(r'doors?\s*(?:open)?\s*[:\-]?\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)',' ',text,flags=re.I)
        times=TIME_RE.findall(timed_text);tm=times[0] if times else None;end_tm=times[-1] if len(times)>1 else None
        raw={'name':title,'startDate':f'{dt.date().isoformat()}T{tm or "00:00"}','url':href,'description':text}
        if end_tm:raw['endDate']=f'{dt.date().isoformat()}T{end_tm}'
        e=normalise(raw,venue,page_url)
        if e:
            if not tm:e['time']=''
            if e['finish_time']==e['time']:e['finish_time']=''
            out.append(e)
    return out

async def get_html(browser,url):
    page=await browser.new_page();page.set_default_timeout(25000)
    try:
        await page.goto(url,wait_until='domcontentloaded',timeout=30000)
        try:await page.wait_for_load_state('networkidle',timeout=10000)
        except PlaywrightTimeoutError:pass
        await page.wait_for_timeout(1200)
        return await page.content(),page.url,None
    except Exception as exc:return '',url,str(exc)
    finally:await page.close()

async def scrape_detail_urls(browser,venue,urls):
    sem=asyncio.Semaphore(8)
    async def one(url):
        async with sem:
            html,final,err=await get_html(browser,url)
            if err:return [],err
            ev=jsonld_events(html,venue,final)
            if not ev:ev=dom_events(html,venue,final)
            return ev,None
    results=await asyncio.gather(*(one(u) for u in urls));out=[];fails=0
    for ev,err in results:
        if err:fails+=1
        out.extend(ev)
    return out,fails

async def scrape_source(browser,source):
    html,final,err=await get_html(browser,source['url'])
    if err:return [],err
    venue=source['venue'];is_dome_search='brightondome.org' in source['url']
    events=jsonld_events(html,venue,final,source.get('match_location'))
    # "jsonld_only" sources are ticketing-site pages (Skiddle, Songkick): only
    # their structured event data is trusted, never the page layout.
    if not source.get('jsonld_only'):
        events.extend(dom_events(html,venue,final,detail_only=is_dome_search))
    if venue=='Brighton Dome':
        soup=BeautifulSoup(html,'html.parser');urls=set()
        for a in soup.find_all('a',href=True):
            u=urljoin(final,a['href']);parsed=urlparse(u)
            if 'brightondome.org' in parsed.netloc and '/whats-on/' in parsed.path:urls.add(u.split('#')[0])
        detail,failed=await scrape_detail_urls(browser,venue,sorted(urls));events.extend(detail)
        print(f'Brighton Dome detail crawl: {len(urls)} pages, {len(detail)} events, {failed} failures')
    return events,None

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True);results=await asyncio.gather(*(scrape_source(browser,s) for s in SOURCES));await browser.close()
    all_events=[];successful=0;failures=[];failed_venues=set()
    report=[]
    for source,(events,err) in zip(SOURCES,results):
        report.append({'venue':source['venue'],'url':source['url'],'events':len(events),'error':(err or '').split('\n')[0][:200],
                       'sample':[{'title':e['title'],'date':e['date'],'time':e.get('time',''),'link':e.get('ticket_url','')} for e in events[:3]]})
        if err:failures.append(f"{source['venue']}: {err}");failed_venues.add(canonical_venue(source['venue']));continue
        successful+=1;all_events.extend(events);print(f"{source['venue']}: {len(events)} events")
    scraped={}
    for e in all_events:
        key=event_key(e)
        if key not in scraped:scraped[key]=e
    scraped=prefer_fuller_titles(list(scraped.values()))
    existing=json.loads(OUT.read_text()) if OUT.exists() else {};removed_generic=0;removed_stale=0
    today=NOW.date().isoformat();stale_before=(NOW-timedelta(days=STALE_DAYS)).date().isoformat()
    # A venue is "healthy" when every one of its sources loaded and it returned at
    # least half as many upcoming events as last time. Only for healthy venues are
    # missing events counted towards removal, so a site outage can't empty the app.
    def future(evs):return [e for e in evs if RANGE_START.isoformat()<=str(e.get('date',''))<=RANGE_END.isoformat()]
    before={};now_count={}
    for e in future(existing.get('events',[])):
        if e.get('source')!='discovery':v=canonical_venue(e.get('venue',''));before[v]=before.get(v,0)+1
    for e in scraped:v=canonical_venue(e.get('venue',''));now_count[v]=now_count.get(v,0)+1
    healthy={v for v in {canonical_venue(s['venue']) for s in SOURCES}
             if v not in failed_venues and now_count.get(v,0)>=max(1,before.get(v,0)//2)}
    # Existing upcoming events. Older records have no last_seen yet: start their clock today.
    kept={}
    for e in existing.get('events',[]):
        try:d=datetime.fromisoformat(e['date']).date()
        except Exception:continue
        if not (RANGE_START<=d<=RANGE_END):continue
        if not valid_title(e.get('title','')):removed_generic+=1;continue
        e=dict(e,title=strip_listing_date(e.get('title','')));e.setdefault('last_seen',today)
        kept.setdefault(e['id'],e)
    by_exact={event_key(e):e for e in kept.values()}
    by_day={}
    for e in kept.values():by_day.setdefault(day_key(e),[]).append(e)
    # Match today's results to existing events. A match keeps the existing id (so
    # saved Interested/Going choices still match) even if the time or the wording
    # of the title has changed, and takes today's details and ticket link.
    matched=set();new=[];pending=[];redated=0
    def adopt(old,e):
        fresh=dict(e,id=old['id'],last_seen=today)
        if is_listing_or_home(fresh.get('ticket_url',''),'') and not is_listing_or_home(old.get('ticket_url',''),''):
            fresh['ticket_url']=old['ticket_url']
        kept[old['id']]=fresh;matched.add(old['id'])
    for e in scraped:
        old=by_exact.get(event_key(e))
        if old is None or old['id'] in matched:
            old=next((c for c in by_day.get(day_key(e),[]) if c['id'] not in matched and same_show(c['title'],e['title'])),None)
        if old is None:pending.append(e)
        else:adopt(old,e)
    # Second pass, only for events still unmatched: an earlier version saved
    # some dates with day and month swapped (10 Nov for 11 Oct). If the same show
    # is stored, unmatched, on the swapped date, it is this event: move it to the
    # right date and keep its id, so saved choices follow it.
    for e in pending:
        sw=swapped_date(e.get('date',''))
        old=next((c for c in by_day.get((day_key(e)[0],sw),[]) if c['id'] not in matched and same_show(c['title'],e['title'])),None) if sw else None
        if old is None:new.append(dict(e,last_seen=today))
        else:adopt(old,e);redated+=1
    for eid,e in list(kept.items()):
        if eid in matched or e.get('source')=='discovery':continue  # discovery events: see scrape-discovery.py
        if canonical_venue(e.get('venue','')) in healthy and str(e.get('last_seen',today))<=stale_before:
            del kept[eid];removed_stale+=1
    # A new event's id is built from its date, venue and title, so it can equal
    # the id of an existing record (e.g. one moved to its correct date keeps the
    # id it was created with). Existing ids carry people's saved choices, so the
    # new event gets a suffix instead.
    used=set(kept)
    for e in new:
        base_id=e['id'];n=2
        while e['id'] in used:e['id']=f'{base_id}-{n}';n+=1
        used.add(e['id'])
    events=prefer_fuller_titles(list(kept.values())+new)
    events=sorted(events,key=lambda x:(x['date'],x.get('time') or '99:99',x['venue'],x['title']))
    existing_future=sum(1 for e in existing.get('events',[]) if e.get('date','')>=RANGE_START.isoformat() and valid_title(e.get('title','')))
    print(f'Successful sources: {successful}/{len(SOURCES)}; scraped: {len(scraped)}; matched existing: {len(matched)} (re-dated {redated}); new: {len(new)}; retained future: {existing_future}; removed generic: {removed_generic}; removed after {STALE_DAYS} days unlisted: {removed_stale}; healthy venues: {len(healthy)}; final: {len(events)}')
    if failures:
        print('Source failures:',file=sys.stderr)
        for f in failures:print(' - '+f,file=sys.stderr)
    if successful<max(12,int(len(SOURCES)*.70)):raise SystemExit('Too many venue sources failed; refusing to replace events.json')
    if len(scraped)<80:raise SystemExit('Too few events scraped; refusing to refresh events.json')
    # A substantial reduction is expected when collapsing duplicate title variants.
    # Only refuse a refresh if the result loses more than 30% of the retained data.
    if existing_future and len(events)<int(existing_future*.70):raise SystemExit('Unexpected loss of future events; refusing to replace events.json')
    # source_report: how each venue's scrape went, so a venue that silently
    # returns nothing is visible in the data (the app ignores this field).
    OUT.write_text(json.dumps({'updated':NOW.date().isoformat(),'range_start':RANGE_START.isoformat(),'range_end':RANGE_END.isoformat(),'venues':sorted({e['venue'] for e in events}),'source_report':report,'events':events},ensure_ascii=False,indent=2)+'\n')
    print(f'Wrote {OUT} with {len(events)} events')

if __name__=='__main__':asyncio.run(main())
