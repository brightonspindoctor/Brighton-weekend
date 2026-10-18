#!/usr/bin/env python3
"""Refresh Brighton Weekend events from configured venue sites."""
import asyncio, html, json, re, sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from event_matching import evening_time, same_session, same_show as same_show_at_venue
from listing_rules import GENERIC_TITLES, NOT_A_TITLE, page_key

ROOT=Path(__file__).resolve().parents[1]
# Sources marked "disabled" stay listed (the discovery scraper still recognises
# their venue) but are not fetched.
SOURCES=[s for s in json.loads((ROOT/'event-sources.json').read_text()) if not s.get('disabled')]
OUT=ROOT/'events.json'
TZ=ZoneInfo('Europe/London')
NOW=datetime.now(TZ)
RANGE_START=NOW.date(); RANGE_END=(NOW+timedelta(days=280)).date()
# A day's name, whole or short ('Fri', 'Friday'), but not 'Friends' or 'Sunset'.
WEEKDAY=r'(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\b'
MONTHS=r'Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?'
# '10 Oct 2026', 'October 10th, 2026' and UK numeric dates such as '10/10/26'.
DATE_RE=re.compile(rf'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\.?\s*(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s*(?:\d{{4}})?|(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?|\d{{1,2}}/\d{{1,2}}/(?:\d{{4}}|\d{{2}}))\b',re.I)
TIME_RE=re.compile(r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b',re.I)
# '19:30', '23:00-04:00': 24-hour times, read only when a card has no am/pm times.
# Two-digit hours only, as '7:30' alone could be morning or evening.
TIME24_RE=re.compile(r'(?<![\d:£$€.])([01]\d|2[0-3]):([0-5]\d)(?![\d:])')
# Times that aren't when the event starts or ends.
NOT_START=re.compile(r'(?:doors?(?:\s*open)?|running\s+time|duration|last\s+entry|curfew)\s*(?:at|from|approx\.?)?\s*[:\-]?\s*\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?',re.I)
def card_times(text):
    return TIME_RE.findall(text) or [f'{h}:{m}' for h,m in TIME24_RE.findall(text)]
CATEGORIES={'Comedy':['comedy','comedian','stand-up','stand up','laughs'],'Club':['club','dj','dnb','drum & bass','rave','techno','house night','party'],'Theatre':['theatre','theater','play','musical','west end'],'Dance':['dance','ballet','contemporary dance'],'Family':['family','kids','children','storytelling','baby'],'Talk':['talk','in conversation','lecture','spoken word','author'],'Sport':['football','boxing','wrestling','sport','racecourse'],'Music':['gig','live','band','concert','tour','festival','dj set','orchestra','singer']}
CTA_PREFIXES=('get tickets','get ticket','buy tickets','buy ticket','book tickets','book ticket','book now','learn more','more info','more details','find out more','event details','on sale','sold out','sign up','subscribe','join our','join the mailing','newsletter','mailing list')

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def valid_title(title):
    t=clean(title); low=t.lower()
    if not t or low in GENERIC_TITLES or NOT_A_TITLE.fullmatch(low):return False
    if any(low.startswith(p) for p in CTA_PREFIXES):return False
    if len(t)<3 or len(t)>180:return False
    if not re.search(r'[^\W\d_]{2}',low):return False  # a year or number on its own, e.g. "2026"
    # Only a date ('Mon 12 Oct 26', 'Friday October 9th'): nothing is left once it is removed.
    rest=re.sub(rf'\b{WEEKDAY}','',DATE_RE.sub('',low),flags=re.I)
    if not re.search(r'[^\W\d_]{2}',rest):return False
    return True

def title_key(title): return re.sub(r'[^a-z0-9]+',' ',clean(title).lower()).strip()
# A listing date appended to a title: '... Fri 25 Sep 2026 8:00 PM' or '... October 9, 2026'.
TRAILING_DATE=re.compile(rf'\s*(?:{WEEKDAY}\.?,?\s+)?(?:(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\.?|(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?)\s+\d{{4}}\b|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}\b).*$',re.I)
# Labels some venues put before the name in the same link: 'Club Events ZERO 7',
# 'Limited Free Tickets Fully Local', 'Sold Out: ...'.
LEADING_LABEL=re.compile(r'^(?:(?:club|live|comedy|music|theatre|family|special|featured|free)\s+events?|limited\s+(?:free\s+)?tickets?|sold\s+out|on\s+sale\s+now|just\s+announced)\s*[-:–|]?\s+',re.I)
def strip_listing_date(title):
    """Drop a trailing "Fri 25 Sep 2026 8:00 PM ( Doors: 7:00 PM )" from a title."""
    cleaned=TRAILING_DATE.sub('',clean(html.unescape(str(title or '')))).strip(' -–|·')
    while True:
        shorter=LEADING_LABEL.sub('',cleaned,count=1)
        if shorter==cleaned or len(shorter)<3:break
        cleaned=shorter
    return cleaned if len(cleaned)>=3 else clean(html.unescape(str(title or '')))
VENUE_ALIASES={'Brighton Dome - Concert Hall':'Brighton Dome'}  # same as prepare-events.py and index.html
def canonical_venue(v): return VENUE_ALIASES.get(v,v)
def event_key(e): return (canonical_venue(e.get('venue','')).lower(),e.get('date',''),title_key(e.get('title','')),e.get('time') or '')
def day_key(e): return (canonical_venue(e.get('venue','')).lower(),e.get('date',''))
def same_show(a,b,venue=''):
    """True when two titles on the same venue and day are the same show, e.g.
    'Wot Italian?' and 'Wot Italian? Boothby Graffoe, Antonio Forcione', or
    'Kepler' and 'Kepler at Concorde 2 - Brighton' (see event_matching.py)."""
    ka,kb=title_key(a),title_key(b)
    if not ka or not kb:return False
    if ka==kb or ka.startswith(kb+' ') or kb.startswith(ka+' '):return True
    from difflib import SequenceMatcher
    return SequenceMatcher(None,ka,kb).ratio()>=0.85 or same_show_at_venue(a,b,venue)
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
                if fuller_title(existing.get('title',''),e.get('title','')) and same_session(existing,e):
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
    if not scored:
        wrap=node.find_parent('a',href=True)
        if wrap is not None:
            u=urljoin(page_url,wrap['href'].strip()).split('#')[0]
            if urlparse(u).scheme in ('http','https') and not is_listing_or_home(u,page_url) and not any(h in urlparse(u).netloc.lower() for h in SKIP_HOSTS):return u
        return None
    best=max(scored,key=scored.get)
    # A block holding many different event links is a whole listing, not one
    # event's card: only trust a link there if it is clearly this event's.
    if len(scored)>4 and scored[best]<3:return None
    return best

def detail_links(node,page_url,include_self=False):
    """(url, text, is_ticket_site) for links in a block that could be an event's
    own page or tickets: not listings/home pages, social media or '/about'."""
    out=[];links=([node] if include_self else [])+node.find_all('a',href=True)
    for a in links:
        raw=(a.get('href') or '').strip()
        if not raw or raw.startswith(('#','mailto:','tel:','javascript:')):continue
        u=urljoin(page_url,raw).split('#')[0];p=urlparse(u);host=p.netloc.lower()
        if p.scheme not in ('http','https') or any(h in host for h in SKIP_HOSTS) or is_listing_or_home(u,page_url):continue
        ticket_site=any(h in host for h in TICKET_HOSTS)
        if not ticket_site and len([x for x in p.path.split('/') if x])<2:continue  # '/about', '/contact'
        out.append((u,clean(a.get_text(' ',strip=True)),ticket_site))
    return out

TITLE_CLASS=re.compile(r'(^|[-_ ])(title|name|headline|heading|artist)([-_ ]|$)',re.I)
def card_title(node,page_url):
    """Title and link for an event card that has no h1-h4 heading. Tries, in
    order: an element styled as a title (class 'title', 'name'...), h5/h6 or
    bold text, the text of a link to the event's own page or a ticketing site,
    and finally the event page's address ('/event/the-wanted-2-0'). Blocks that
    link to several different events are skipped: each event's own card is read
    separately, and a whole list must not become one event."""
    cands=detail_links(node,page_url)
    if not cands:
        wrap=node.find_parent('a',href=True)  # the whole card is one link
        if wrap is not None:cands=detail_links(wrap,page_url,include_self=True)
    if len({u for u,_,_ in cands})>3:return '',page_url
    link=next((u for u,_,_ in cands),None)
    el=node.find(class_=TITLE_CLASS) or node.find(['h5','h6'])
    t=strip_listing_date(el.get_text(' ',strip=True)) if el else ''
    if valid_title(t) and not DATE_RE.search(t) and not TIME_RE.search(t):return t,(link or page_url)
    for u,text,ticket_site in cands:
        text=strip_listing_date(text)
        if valid_title(text) and not TIME_RE.fullmatch(text):return text,u
        if DATE_RE.search(text) and not ticket_site:
            # The link text is only a date ('Mon 12 Oct 26', as at CHALK): use the
            # event page's address instead ('/event/fat-poppadaddys').
            t=slug_title(u)
            if valid_title(t):return t,u
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
    # Brighton Dome prefixes its addresses with a short mixed-case id ('LiM-ben-folds').
    m=re.match(r'^([A-Za-z0-9]{2,5})-(.+)$',slug)
    if m and re.search(r'[A-Z]',m.group(1)) and re.search(r'[a-z]',m.group(1)):slug=m.group(2)
    slug=re.sub(r'-(?:20\d\d-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}-20\d\d)$','',slug)  # '...-2026-10-24': the date, shown on the card anyway
    slug=re.sub(r'(?<=[a-z])-\d{1,2}$','',slug)  # 'cancer-bats-1': a site's suffix for a repeated name (not 'the-wanted-2-0')
    slug=re.sub(r'[-_]+',' ',slug).strip()
    if not slug:return ''
    return clean(' '.join(w[:1].upper()+w[1:] for w in slug.split()))  # not .title(): '4am-kru' is '4am Kru', not '4Am Kru'

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
    title=strip_listing_date(raw.get('name') or raw.get('title'))
    core=re.sub(r'^the\s+','',venue,flags=re.I)
    title=re.sub(rf'\s+@\s+(?:the\s+)?{re.escape(core)}\b.*$','',title,flags=re.I).strip(); start_raw=raw.get('startDate') or raw.get('start_date') or raw.get('date'); start=parse_dt(start_raw)
    if not valid_title(title) or not start or not (RANGE_START<=start.date()<=RANGE_END):return None
    blob=clean(' '.join(str(raw.get(k,'')) for k in ('name','description','status'))).lower()
    if any(x in blob for x in ('cancelled','canceled','postponed','event cancelled')):return None
    end=parse_dt(raw.get('endDate') or raw.get('end_date'))
    # Closest to the tickets first: the ticket offer, then the event's own page,
    # and the listings page only as a last resort.
    candidates=[offer_url(raw),raw.get('url')]
    url=next((urljoin(page_url,c) for c in candidates if c and not is_listing_or_home(urljoin(page_url,c),page_url)),None) or urljoin(page_url,raw.get('url') or page_url)
    if re.match(r'http://(?:www\.)?(?:songkick|skiddle|seetickets|eventbrite|ticketmaster|dice)\.',url):url='https://'+url[len('http://'):]
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
            # Events can sit inside another record: Skiddle lists a venue's gigs
            # under the venue's "event" key, item lists under "itemListElement".
            for key in ('event','events','subEvent','itemListElement','item','mainEntity'):
                if isinstance(obj.get(key),(list,dict)):stack.append(obj[key])
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
        dt=None
        for dm in DATE_RE.finditer(text):
            if text[max(0,dm.start(1)-1):dm.start(1)] in ('£','$','€'):continue  # '£15/12/10' is a price
            cand=parse_dt(dm.group(1))
            if cand and RANGE_START<=cand.date()<=RANGE_END:dt=cand;break
        if not dt:continue
        links=node.find_all('a',href=True)
        if detail_only:links=[a for a in links if '/whats-on/' in urlparse(urljoin(page_url,a['href'])).path]
        h=node.find(['h1','h2','h3','h4'])
        title=clean(h.get_text(' ',strip=True)) if h else ''
        if title and not detail_only and len({u for u,_,_ in detail_links(node,page_url)})>3:continue  # a list of events: its cards are read one by one
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
        # Start and finish from the card. "Doors: 7pm" isn't either. A time in the
        # act's name ("4am Kru ... 23:00-04:00") is used only if the card has no other.
        timed_text=NOT_START.sub(' ',text)
        outside=re.sub(re.escape(title),' ',timed_text,flags=re.I) if title else timed_text
        times=card_times(outside) or card_times(timed_text);tm=times[0] if times else None;end_tm=times[-1] if len(times)>1 else None
        raw={'name':title,'startDate':f'{dt.date().isoformat()}T{tm or "00:00"}','url':href,'description':text}
        if end_tm:raw['endDate']=f'{dt.date().isoformat()}T{end_tm}'
        e=normalise(raw,venue,page_url)
        if e:
            if not tm:e['time']=''
            if e['finish_time']==e['time']:e['finish_time']=''
            out.append(e)
    return out

# ---- The venue's own labels ---------------------------------------------------
# Theatre Royal's ATG listings, The Old Market and Brighton Dome say what kind
# of show each event is. The labels are collected here (venue -> [{key, title,
# label}]), written to events.json as venue_labels, and applied by
# prepare-events.py (listing_rules.label_category), which then drops them.
VENUE_LABELS={}
def add_labels(venue,items):
    VENUE_LABELS.setdefault(venue,[]).extend(x for x in items if x.get('label') and (x.get('key') or x.get('title')))
def atg_labels(page,page_url):
    """ATG cards: the show's link (a[aria-hidden] to /shows/<slug>/...) with its
    title, then a label line ('Concert', 'Musicals, Family'), after 'Sold out'
    when it is, then the venue and dates."""
    soup=BeautifulSoup(page,'html.parser');out=[]
    for a in soup.select('a[href*="/shows/"][aria-hidden="true"]'):
        box=a.find_parent('div');card=box.parent if box else None
        if card is None:continue
        lines=[x for x in (clean(p.get_text(' ',strip=True)) for p in card.find_all('p')) if x and x.lower()!='sold out']
        title=clean(a.get('aria-label') or a.get_text(' ',strip=True))
        if title.lower()=='sold out':title=''  # a sold-out show's badge link: the address still names the show
        if lines:out.append({'key':page_key(urljoin(page_url,a['href'])),'title':title,'label':lines[0]})
    return out
def eventlist_labels(page,page_url):
    """A Squarespace events list (The Old Market): each listing's categories
    ('.eventlist-cats a': 'Music', 'Dance', 'Theatre') beside its title link."""
    soup=BeautifulSoup(page,'html.parser');out=[]
    for item in soup.select('.eventlist-column-info'):
        link=item.select_one('.eventlist-title a[href]')
        cats=[clean(a.get_text(' ',strip=True)) for a in item.select('.eventlist-cats a')]
        if link and cats:out.append({'key':page_key(urljoin(page_url,link['href'])),'title':clean(link.get_text(' ',strip=True)),'label':', '.join(cats)})
    return out
def dome_page_label(page):
    """A Brighton Dome event page's title names its genre:
    'Congregational / Theatre / What's On | Brighton Dome'."""
    m=re.search(r'<title[^>]*>(.*?)</title>',page,re.I|re.S)
    parts=[clean(x) for x in html.unescape(m.group(1)).split(' / ')] if m else []
    return parts[-2] if len(parts)>=3 and parts[-1].lower().startswith('what') else ''
def collect_labels(venue,page,page_url):
    if 'atgtickets.com' in page_url:add_labels(venue,atg_labels(page,page_url))
    elif 'eventlist-column-info' in page:add_labels(venue,eventlist_labels(page,page_url))

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
            label=dome_page_label(html) if 'brightondome.org' in final else ''
            if label:add_labels(venue,[{'key':page_key(final),'title':e['title'],'label':label} for e in ev])
            return ev,None
    results=await asyncio.gather(*(one(u) for u in urls));out=[];fails=0
    for ev,err in results:
        if err:fails+=1
        out.extend(ev)
    return out,fails

def fetch_plain(url,accept='text/html'):
    """Plain request, for ticketing sites that show automated browsers a
    security check ("Just a moment...") but serve the page itself to this."""
    from urllib.request import Request,urlopen
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36','Accept':accept})
    with urlopen(req,timeout=30) as r:return r.read().decode('utf-8','replace'),r.geturl()
# ---- Ticketsolve feeds ------------------------------------------------------
# Venues that sell through Ticketsolve publish a feed (<venue>.ticketsolve.com/shows.xml)
# with the venue's own category for each show and the start of each performance.
# A source with "ticketsolve" in event-sources.json uses it to file its events
# (Komedia's listings rarely say whether a show is comedy or a gig) and to fill
# in a start time the listing leaves out.
TICKETSOLVE_CATEGORIES={'comedy':'Comedy','music':'Music','club':'Club','kids shows':'Family','spoken word':'Talk'}
# Labels that say less ("Workshop", "Event"): the title decides, as for any listing,
# and a cabaret or drag show the title doesn't place is filed as Theatre.
TICKETSOLVE_FALLBACK={'cabaret':'Theatre','drag':'Theatre'}
def ticketsolve_performances(feed_url):
    text,_=fetch_plain(feed_url,accept='application/xml,text/xml')
    out=[]
    for show in ET.fromstring(text).iter('show'):
        label=clean(show.findtext('event_category') or '').lower()
        cat=TICKETSOLVE_CATEGORIES.get(label) or ('Comedy' if 'comedy' in label else None)
        name=html.unescape(clean(show.findtext('name') or ''))
        for ev in show.iter('event'):
            try:start=datetime.fromisoformat(clean(ev.findtext('date_time_iso') or '')).astimezone(TZ)
            except ValueError:continue
            out.append({'show':show.get('id'),'event':ev.get('id'),'name':name,'category':cat,'label':label,
                        'date':start.date().isoformat(),'time':start.strftime('%H:%M')})
    return out

def apply_ticketsolve(events,source):
    """File the source's events by the venue's own categories and fill missing start times."""
    try:perfs=ticketsolve_performances(source['ticketsolve'])
    except Exception as exc:
        print(f"{source['venue']}: Ticketsolve feed unavailable ({str(exc)[:120]})");return
    by_event={p['event']:p for p in perfs};by_date={}
    for p in perfs:by_date.setdefault(p['date'],[]).append(p)
    matched=0
    for e in events:
        m=re.search(r'ticketsolve\.com/(?:ticketbooth/)?shows/\d+/events/(\d+)',e.get('ticket_url') or '')
        p=by_event.get(m.group(1)) if m else None
        if p is None:
            # The listing links to the venue's own page: the same show that day, by its name.
            cands=[x for x in by_date.get(e['date'],[]) if same_show_at_venue(x['name'],e['title'],source['venue'])]
            if e.get('time'):cands=[x for x in cands if x['time']==e['time']] or cands
            if len({x['show'] for x in cands})!=1:continue
            p=cands[0] if len(cands)==1 or e.get('time') else {**cands[0],'time':''}  # two performances that day: no time guessed
        matched+=1
        e['category']=p['category'] or category(e['title'])
        if e['category']=='Other':e['category']=TICKETSOLVE_FALLBACK.get(p['label'],'Other')
        if not e.get('time') and p['time']:e['time']=p['time']
    print(f"{source['venue']}: Ticketsolve feed filed {matched} of {len(events)} listings")

# ---- Glyndebourne -------------------------------------------------------------
# Its season page (/autumn/, /festival/) has one card per production with only a
# date range. Each production's page lists its performances as booking links
# ("19 Mon, Oct 2026 4:00pm On Sale", "30 Fri, Oct 2026 Limited"), and its timings
# say what it is ("Opera starts: 4.00pm", "Concert starts: 7.00pm"); that word
# files it (listing_rules.LABEL_CATEGORIES: Opera is Theatre, Concert is Music).
# A booking link without a time takes the page's start time only when the page
# gives one start time; with several (an evening and a matinee) none is guessed.
GLYNDE_PERF=re.compile(r'(\d{1,2})\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+([A-Za-z]{3,9})\s+(\d{4})(?:\s+(\d{1,2}:\d{2})\s*([ap]m))?',re.I)
GLYNDE_STARTS=re.compile(r'\b(Opera|Concert|Recital|Masterclass|Performance|Show|Talk)\s+starts:?\s*(\d{1,2})[.:](\d{2})\s*([ap]m)',re.I)
def to24(h,m,ap):return f'{int(h)%12+(12 if ap.lower()=="pm" else 0):02d}:{m}'
def glyndebourne_production(page,page_url,fallback_title=''):
    soup=BeautifulSoup(page,'html.parser')
    h1=soup.find('h1')
    # The season page's card title first: production pages' headings aren't always
    # in title case ("The barber of Seville").
    title=fallback_title or strip_listing_date(clean(h1.get_text(' ',strip=True)) if h1 else '') or slug_title(page_url)
    starts=GLYNDE_STARTS.findall(clean(soup.get_text(' ',strip=True)))
    kind=starts[0][0].title() if starts else ''
    page_times={to24(h,m,ap) for _,h,m,ap in starts}
    out=[];seen=set()
    for a in soup.find_all('a',href=True):
        link=urljoin(page_url,a['href'])
        if 'tickets.glyndebourne.com' not in link or '/performance/' not in link or link in seen:continue
        text=clean(a.get_text(' ',strip=True));m=GLYNDE_PERF.search(text)
        if not m:continue
        seen.add(link)
        time=to24(*m.group(4).split(':'),m.group(5)) if m.group(4) else (next(iter(page_times)) if len(page_times)==1 else '')
        start=parse_dt(f'{m.group(1)} {m.group(2)} {m.group(3)}')
        if not start:continue
        e=normalise({'name':title,'startDate':start.date().isoformat()+(f'T{time}' if time else ''),'url':link},'Glyndebourne',page_url)
        if not e:continue
        if re.search(r'\bsold\s*out\b',text,re.I):e['status']='SOLD OUT'
        out.append(e)
    if kind and out:add_labels('Glyndebourne',[{'key':'','title':title,'label':kind}])
    return out
async def glyndebourne_events(browser,pages):
    urls={}
    for page,page_url in pages:
        for a in BeautifulSoup(page,'html.parser').find_all('a',href=True):
            u=urljoin(page_url,a['href']).split('#')[0].split('?')[0];p=urlparse(u)
            if p.netloc.endswith('glyndebourne.com') and re.fullmatch(r'/events/[^/]+/?',p.path) and not urls.get(u):
                name=clean(a.get_text(' ',strip=True));urls[u]=name if valid_title(name) else ''
    sem=asyncio.Semaphore(4)
    async def one(url,name):
        async with sem:h,final,err=await get_html(browser,url)
        if err:print(f'Glyndebourne: {url} failed: {err[:120]}');return []
        return glyndebourne_production(h,final,name)
    found=await asyncio.gather(*(one(u,n) for u,n in urls.items()))
    events=[e for evs in found for e in evs]
    print(f'Glyndebourne: {len(urls)} productions, {len(events)} performances')
    return events

async def scrape_source(browser,source):
    html,final,err=await get_html(browser,source['url'])
    venue=source['venue'];is_dome_search='brightondome.org' in source['url']
    events=[] if err else jsonld_events(html,venue,final,source.get('match_location'))
    if source.get('jsonld_only') and not events:
        # Skiddle/Songkick blocked the browser, or it rendered no event data: try a plain request.
        try:
            html,final=await asyncio.to_thread(fetch_plain,source['url']);err=None
            events=jsonld_events(html,venue,final,source.get('match_location'))
        except Exception as exc:
            err=err or str(exc)
    if err:return [],err
    if source.get('glyndebourne'):
        # More season pages (the summer Festival as well as the autumn season):
        # productions linked from any of them are read; one that fails is skipped.
        pages=[(html,final)]
        for su in source.get('season_pages',[]):
            sh,sf,serr=await get_html(browser,su)
            if serr:print(f"{venue}: season page failed {su}: {serr[:120]}")
            else:pages.append((sh,sf))
        return await glyndebourne_events(browser,pages),None
    collect_labels(venue,html,final)
    # "label_pages": more of the venue's pages that only lend their labels
    # (Theatre Royal's genre lists on ATG, which cover its whole programme).
    for lu in source.get('label_pages',[]):
        lh,lf,lerr=await get_html(browser,lu)
        if lerr:print(f"{venue}: label page failed {lu}: {lerr[:120]}")
        else:collect_labels(venue,lh,lf)
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
    if source.get('ticketsolve'):await asyncio.to_thread(apply_ticketsolve,events,source)  # a plain request: off the event loop
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
    # Records from an earlier import (no "source") count towards "last time" too,
    # so a venue whose page shows only part of its programme (Theatre Royal's
    # first page, Brighton Centre's highlights) stays "unhealthy" and keeps them
    # until their date: a show missing from a partial page may still be on.
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
    matched=set();new=[];redated=0
    def adopt(old,e):
        fresh=dict(e,id=old['id'],last_seen=today)
        if fresh.get('time'):fresh['time']=evening_time(old.get('time'),fresh['time'])  # 11:00 for a 23:00 club night: a missing "pm"
        if old.get('also_ids'):fresh['also_ids']=old['also_ids']  # ids merged into this one (saved choices)
        if old.get('promoter'):fresh['promoter']=old['promoter']  # set by scrape-discovery.py (e.g. JOY. Concerts)
        if is_listing_or_home(fresh.get('ticket_url',''),'') and not is_listing_or_home(old.get('ticket_url',''),''):
            fresh['ticket_url']=old['ticket_url']
        kept[old['id']]=fresh;matched.add(old['id'])
    # Three passes, so a looser match can't take an event before the listing that
    # matches it best is reached: the same title and time, then a similar title
    # at the same time, then a similar title at any time. (Brighton Dome lists
    # each comedy festival show twice, once without a time. When the untimed copy
    # took the event, the timed one was added as new and kept by prepare-events.py,
    # so the show's id changed on every run.)
    pending=list(scraped)
    for same_time in (None,True,False):
        rest=[]
        for e in pending:
            if same_time is None:
                old=by_exact.get(event_key(e))
                if old is not None and old['id'] in matched:old=None
            else:
                old=next((c for c in by_day.get(day_key(e),[]) if c['id'] not in matched
                          and same_session(c,e,same_time) and same_show(c['title'],e['title'],c.get('venue',''))),None)
            if old is None:rest.append(e)
            else:adopt(old,e)
        pending=rest
    # Last, for events still unmatched: an earlier version saved
    # some dates with day and month swapped (10 Nov for 11 Oct). If the same show
    # is stored, unmatched, on the swapped date, it is this event: move it to the
    # right date and keep its id, so saved choices follow it.
    for e in pending:
        sw=swapped_date(e.get('date',''))
        old=next((c for c in by_day.get((day_key(e)[0],sw),[]) if c['id'] not in matched and same_show(c['title'],e['title'],c.get('venue',''))),None) if sw else None
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
    OUT.write_text(json.dumps({'updated':NOW.date().isoformat(),'range_start':RANGE_START.isoformat(),'range_end':RANGE_END.isoformat(),'venues':sorted({e['venue'] for e in events}),'source_report':report,'venue_labels':VENUE_LABELS,'events':events},ensure_ascii=False,indent=2)+'\n')
    print(f'Wrote {OUT} with {len(events)} events')
    print('Venue labels: '+', '.join(f'{v} {len(x)}' for v,x in sorted(VENUE_LABELS.items())))

if __name__=='__main__':asyncio.run(main())
