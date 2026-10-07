#!/usr/bin/env python3
"""Add Brighton events discovered from broad public calendars.

This complements the venue-first scraper. Discovery sources are filtered back
to Brighton Weekend's known venues so broad city calendars do not flood the app
with events outside Brighton or with venues we do not support yet.
"""
import asyncio, json, re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from event_matching import same_show as same_show_at_venue

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'events.json'; TZ=ZoneInfo('Europe/London'); NOW=datetime.now(TZ); START=NOW.date(); END=(NOW+timedelta(days=280)).date()
SOURCE_CONFIG=json.loads((ROOT/'event-sources.json').read_text())
VENUES={s['venue'] for s in SOURCE_CONFIG} | {"Amex Stadium"}
VENUE_ALIASES={
 "concorde2":"Concorde 2","concorde 2":"Concorde 2","theatre royal":"Theatre Royal Brighton",
 "theatre royal - brighton":"Theatre Royal Brighton","the hope and ruin":"The Hope & Ruin",
 "brighton komedia":"Komedia","corn exchange":"Brighton Dome","brighton dome":"Brighton Dome",
 "old albion":"Old Albion","the old albion":"Old Albion","the brighton centre":"Brighton Centre",
 "the pipeline":"The Pipeline","pipeline brighton":"The Pipeline","volks club":"Volks","the volks":"Volks",
 "patterns brighton":"Patterns","dust brighton":"DUST","alphabet":"A L P H A B E T","alphabet brighton":"A L P H A B E T","hope & ruin":"The Hope & Ruin","the hope & ruin":"The Hope & Ruin",
 "prince albert":"The Prince Albert","folklore rooms":"The Folklore Rooms","cowley club":"The Cowley Club","rose hill brighton":"The Rose Hill",
 "bees mouth":"The Bee's Mouth","bee's mouth":"The Bee's Mouth","waterbear venue":"The Waterbear","the waterbear":"The Waterbear","daltons bar":"Daltons",
 "caroline of brunswick":"Caroline of Brunswick","resident music":"Resident",
}
# Names too ordinary to find inside other text ('resident DJs'): matched only
# when a source gives the venue on its own, as Rival Cults does.
EXACT_ONLY_VENUES={"Resident"}
SOURCES=[
 "https://www.visitbrighton.com/whats-on/Brighton",
 "https://www.eventbrite.co.uk/d/united-kingdom--brighton/events/",
 "https://www.ticketmaster.co.uk/discover/brighton",
 "https://www.skiddle.com/whats-on/Brighton/",
 "https://www.joyconcerts.com/listings",  # JOY. Concerts, promoter: gigs at Concorde 2, Volks, Hope & Ruin, Green Door Store and more
 "https://www.tickettailor.com/events/beatdown",  # Beat Down Promotions (hip-hop), sells through Ticket Tailor
 "https://www.rivalcults.com/gigs",  # Rival Cults: one big table of Brighton gigs across ~25 venues
]
# Promoters whose own listings we read: their gigs get the promoter's sticker in the app
# (PROMOTER_STICKERS in index.html), also when a venue's listing of the same gig is the one kept.
PROMOTERS={'joyconcerts.com':'JOY. Concerts','tickettailor.com/events/beatdown':'Beat Down Promotions'}
# Ticket Tailor shows automated browsers a security check ("Just a moment...",
# HTTP 403) but serves its static listing pages to a plain request.
PLAIN_FETCH=('tickettailor.com/',)
def fetch_plain(url):
 from urllib.request import Request,urlopen
 req=Request(url,headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36','Accept':'text/html'})
 with urlopen(req,timeout=30) as r:return r.read().decode('utf-8','replace')
def promoter_for(page_url):return next((name for key,name in PROMOTERS.items() if key in page_url),None)
BRIGHTON_POSTCODE=re.compile(r'\bBN(?:1|2|3|41|42)\b',re.I)  # Brighton & Hove
MONTHS=r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
DATE_RE=re.compile(rf"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\.?\s*(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s*(?:\d{{4}})?|(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?|\d{{1,2}}/\d{{1,2}}/(?:\d{{4}}|\d{{2}}))\b",re.I); TIME_RE=re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",re.I)
GENERIC_TITLES={'comedy','classical music','music','talks & debate','talks and debate','dance','theatre','family',"what's on",'events','upcoming events','get tickets','buy tickets','book tickets','learn more','more info','more info & tickets','find out more','event details','sold out','on sale','on sale today','tickets','read more','view event'}
CTA_PREFIXES=('get tickets','buy tickets','book tickets','learn more','more info','find out more','event details','on sale','sold out')
def clean(s):return re.sub(r"\s+"," ",s or "").strip()
def valid_title(title):
 t=clean(title);low=t.lower()
 if not t or low in GENERIC_TITLES:return False
 if any(low.startswith(p) for p in CTA_PREFIXES):return False
 return 3<=len(t)<=180
def title_key(title):return re.sub(r'[^a-z0-9]+',' ',clean(title).lower()).strip()
def to_hhmm(value):
 # '7:30pm' -> '19:30' so discovery times match the venue scraper's format
 m=re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?',clean(value).lower())
 if not m:return ''
 h=int(m.group(1));mi=int(m.group(2) or 0)
 if m.group(3)=='pm' and h<12:h+=12
 if m.group(3)=='am' and h==12:h=0
 return f'{h:02d}:{mi:02d}' if h<24 and mi<60 else ''
def fuller_title(a,b):
 ka,kb=title_key(a),title_key(b)
 if ka==kb:return a if len(a)>=len(b) else b
 if ka and kb and (ka.startswith(kb+' ') or kb.startswith(ka+' ')):
  return a if len(ka)>len(kb) else b
 return None
def prefer_fuller_titles(events):
 groups={}
 for e in events:groups.setdefault((e.get('venue','').lower(),e.get('date',''),e.get('time') or ''),[]).append(e)
 kept=[]
 for group in groups.values():
  group=sorted(group,key=lambda e:len(title_key(e.get('title',''))),reverse=True);chosen=[]
  for e in group:
   if not valid_title(e.get('title','')):continue
   if not any(fuller_title(x.get('title',''),e.get('title','')) for x in chosen):chosen.append(e)
  kept.extend(chosen)
 return kept
STALE_DAYS=3  # same rule as scrape-events.py
def same_show(a,b,venue=''):
 # 'Kepler at Concorde 2 - Brighton' (Skiddle) is the venue's 'Kepler': see event_matching.py
 ka,kb=title_key(a),title_key(b)
 if not ka or not kb:return False
 if ka==kb or ka.startswith(kb+' ') or kb.startswith(ka+' '):return True
 from difflib import SequenceMatcher
 return SequenceMatcher(None,ka,kb).ratio()>=0.85 or same_show_at_venue(a,b,venue)
ROLLOVER_DAYS=60  # same rule as scrape-events.py: "15 Jan" seen in October means next January
def parse_date(s):
 try:
  v=clean(s);iso=bool(re.match(r'\d{4}-\d{1,2}-\d{1,2}',v))  # 2026-12-10 is year-month-day, never year-day-month
  d=dateparser.parse(v,dayfirst=not iso,yearfirst=iso,fuzzy=True,default=datetime(START.year,1,1))
  if not d:return None
  if not re.search(r'\b\d{4}\b',str(s)) and d.date()<START-timedelta(days=ROLLOVER_DAYS):
   try:d=d.replace(year=d.year+1)
   except ValueError:d=d.replace(year=d.year+1,day=28)
  return d.date()
 except Exception:return None
def has_name(name,low):
 # whole words only, so 'dust' doesn't match 'industry'
 return re.search(r'(?<![a-z0-9])'+re.escape(name)+r'(?![a-z0-9])',low) is not None
def venue_from_text(text):
 low=clean(text).lower().replace('\u2019',"'")
 for alias,venue in sorted(VENUE_ALIASES.items(),key=lambda x:len(x[0]),reverse=True):
  if venue in VENUES and venue not in EXACT_ONLY_VENUES and has_name(alias,low):return venue
 for v in sorted(VENUES,key=len,reverse=True):
  if v not in EXACT_ONLY_VENUES and has_name(v.lower(),low):return v
 return None
def category(title,text):
 h=(title+' '+text).lower()
 if any(x in h for x in ('comedy','comedian','stand-up','stand up')):return 'Comedy'
 if any(x in h for x in ('theatre','theater','play','musical')):return 'Theatre'
 if any(x in h for x in ('dj','club','rave','techno','house night','party')):return 'Club'
 if any(x in h for x in ('concert','gig','live','band','festival','orchestra','singer')):return 'Music'
 return 'Other'
def make_event(title,date,time,url,venue,text):
 if not valid_title(title) or not date or date<START or date>END or not venue:return None
 time=to_hhmm(time)
 ident=re.sub(r'[^a-z0-9]+','-',f'{date}-{venue}-{title}'.lower()).strip('-')[:180]
 return {'id':ident,'title':title,'date':date.isoformat(),'venue':venue,'source':'discovery','time':time,'finish_time':'','category':category(title,text),'ticket_url':url}
def joy_cards(soup,page_url):
 """JOY. Concerts listings: one <article> per gig with the act in <h2>, venue
 and town in <li>s, the date as dd/mm/yy in <datetime>, and a Buy link. The
 promoter also books London, Bristol, Worthing etc., so only Brighton/Hove gigs
 at venues Brighton Weekend knows are kept. The listing shows no start times;
 when the venue's own site lists the gig, its time is used (prepare-events.py)."""
 out=[]
 for card in soup.find_all('article'):
  h=card.find('h2');dt=card.find('datetime')
  items=[clean(li.get_text(' ',strip=True)) for li in card.find_all('li')]
  if not h or not dt or len(items)<2:continue
  if not re.fullmatch(r'(?:brighton|hove|brighton\s*(?:&|and)\s*hove)',items[-1],re.I):continue
  venue=venue_from_text(items[0])
  if not venue:continue
  title=clean(h.get_text(' ',strip=True))
  page=card.find('a',title=re.compile(r'^View event',re.I))
  buy=next((a for a in card.find_all('a',href=True) if re.search(r'\b(?:buy|tickets?|book)\b',a.get_text(' ',strip=True),re.I)),None)
  url=urljoin(page_url,(buy or page or {}).get('href') or page_url)
  e=make_event(title,parse_date(dt.get_text(strip=True)),'',url,venue,'')
  if e:
   e['promoter']=promoter_for(page_url)  # shown as a sticker on the event card
   if e['category']=='Other' and not re.search(r'wrestling|quiz|market|talk',title,re.I):e['category']='Music'
   out.append(e)
 return out
def tickettailor_cards(soup,page_url):
 """A promoter's Ticket Tailor page: one <li class="events-listing__item"> per
 gig, titled 'ACT // DATE // VENUE // TOWN', with the date in
 .event-meta__date ('Mon 26 Oct 2026 6:30 PM - 10:00 PM') and the place in
 .event-meta__location ('Chalk, BN1 1NJ'). Only Brighton & Hove postcodes at
 venues Brighton Weekend knows are kept."""
 out=[]
 for card in soup.select('li.events-listing__item'):
  link=card.select_one('a.event__link');when=card.select_one('.event-meta__date');where=card.select_one('.event-meta__location')
  if not link or not when or not where:continue
  place=clean(where.get_text(' ',strip=True))
  if not BRIGHTON_POSTCODE.search(place):continue
  venue=venue_from_text(place.split(',')[0])
  if not venue:continue
  title=clean(link.get_text(' ',strip=True).split('//')[0])
  stamp=clean(when.get_text(' ',strip=True))
  tm=TIME_RE.search(stamp)
  e=make_event(title,parse_date(re.sub(r'\d{1,2}(?::\d{2})?\s*(?:am|pm).*$','',stamp,flags=re.I)),tm.group(1) if tm else '',urljoin(page_url,link.get('href')),venue,'')
  if e:
   e['promoter']=promoter_for(page_url)
   if e['category']=='Other':e['category']='Music'
   out.append(e)
 return out
# Rival Cults lists each venue under its own short name. Every name it uses
# maps to one Brighton Weekend venue, so the same place is never added twice
# (Alphabet = A L P H A B E T, Chalk = CHALK, every Dome room = Brighton Dome).
RIVALCULTS_VENUES={
 "alphabet":"A L P H A B E T","brighton centre":"Brighton Centre","chalk":"CHALK","concorde 2":"Concorde 2",
 "dust":"DUST","green door store":"Green Door Store","hope & ruin":"The Hope & Ruin","hope and ruin":"The Hope & Ruin",
 "komedia":"Komedia","patterns":"Patterns","prince albert":"The Prince Albert","the prince albert":"The Prince Albert",
 "quarters":"Quarters","the old market":"The Old Market","old market":"The Old Market","the pipeline":"The Pipeline",
 "pipeline":"The Pipeline","volks":"Volks","the brunswick":"The Brunswick","brunswick":"The Brunswick",
 "caroline of brunswick":"Caroline of Brunswick","cowley club":"The Cowley Club","the cowley club":"The Cowley Club",
 "daltons":"Daltons","folklore rooms":"The Folklore Rooms","the folklore rooms":"The Folklore Rooms",
 "fortune of war":"Fortune of War","resident":"Resident","rose hill":"The Rose Hill","the rose hill":"The Rose Hill",
 "rossi bar":"Rossi Bar","the bee's mouth":"The Bee's Mouth","bee's mouth":"The Bee's Mouth",
 "waterbear venue":"The Waterbear","waterbear":"The Waterbear","the waterbear":"The Waterbear",
}
RIVALCULTS_UNKNOWN=set()  # venue names it lists that we don't map yet (printed, and kept in discovery_report)
def rivalcults_venue(name):
 low=clean(name).lower().replace('’',"'")
 if low.startswith('brighton dome'):return 'Brighton Dome'  # 'Brighton Dome - Corn Exchange' etc.
 v=RIVALCULTS_VENUES.get(low)
 return v if v in VENUES else None
def rivalcults_rows(soup,page_url):
 """Rival Cults gig list: a table with Date ('06 Oct', no year), Title,
 Location and Link columns. Unknown venue names are reported, not guessed."""
 out=[]
 for table in soup.find_all('table'):
  rows=table.find_all('tr')
  if not rows:continue
  head=[clean(c.get_text(' ',strip=True)).lower() for c in rows[0].find_all(['th','td'])]
  col=lambda *names,default=None:next((i for i,h in enumerate(head) if any(n in h for n in names)),default)
  di,ti,vi=col('date',default=0),col('title','artist','event',default=1),col('location','venue',default=2)
  for row in rows:
   cells=row.find_all(['td','th'])
   if len(cells)<=max(di,ti,vi):continue
   d=parse_date(cells[di].get_text(' ',strip=True)) if DATE_RE.search(cells[di].get_text(' ',strip=True)) else None
   if not d:continue  # header or blank row
   place=clean(cells[vi].get_text(' ',strip=True));venue=rivalcults_venue(place)
   if not venue:
    if place:RIVALCULTS_UNKNOWN.add(place)
    continue
   title=clean(cells[ti].get_text(' ',strip=True))
   link=next((a['href'] for a in row.find_all('a',href=True) if 'rivalcults.com' not in a['href']),None)
   e=make_event(title,d,'',urljoin(page_url,link or page_url),venue,'')
   if e:
    if e['category']=='Other' and not re.search(r'wrestling|quiz|market|talk|cabaret|burlesque|drag|film',title,re.I):e['category']='Music'
    out.append(e)
 return out
def extract_cards(html,page_url):
 soup=BeautifulSoup(html,'html.parser');out=[]
 if 'joyconcerts.com' in page_url:return joy_cards(soup,page_url)
 if 'tickettailor.com/events/' in page_url:return tickettailor_cards(soup,page_url)
 if 'rivalcults.com' in page_url:return rivalcults_rows(soup,page_url)
 for tag in soup.find_all('script',attrs={'type':re.compile('ld\\+json',re.I)}):
  try:data=json.loads(tag.string or tag.get_text())
  except Exception:continue
  stack=data if isinstance(data,list) else [data]
  while stack:
   obj=stack.pop()
   if isinstance(obj,list):stack.extend(obj);continue
   if not isinstance(obj,dict):continue
   if isinstance(obj.get('@graph'),list):stack.extend(obj['@graph'])
   for key in ('event','events','subEvent','itemListElement','item','mainEntity'):  # events nested in a venue or list record
    if isinstance(obj.get(key),(list,dict)):stack.append(obj[key])
   typ=obj.get('@type','');types=typ if isinstance(typ,list) else [typ]
   if not any(str(t).lower()=='event' or str(t).lower().endswith('event') for t in types):continue  # MusicEvent, ComedyEvent…
   title=clean(obj.get('name') or obj.get('headline'));start=obj.get('startDate') or obj.get('start_date')
   if not valid_title(title) or not start:continue
   d=parse_date(start);loc=obj.get('location') or {};locs=loc if isinstance(loc,list) else [loc]
   for location in locs:
    lname=clean(location.get('name') if isinstance(location,dict) else '');venue=venue_from_text(lname)
    if venue:
     tm=TIME_RE.search(str(start));e=make_event(title,d,tm.group(1) if tm else '',urljoin(page_url,obj.get('url') or page_url),venue,clean(obj.get('description')))
     if e:out.append(e)
     break
 for node in soup.find_all(['article','li','div'],limit=20000):
  text=clean(node.get_text(' ',strip=True))
  if len(text)<20 or len(text)>900:continue
  dm=DATE_RE.search(text);d=parse_date(dm.group(1)) if dm else None
  if not d or not (START<=d<=END):continue
  venue=venue_from_text(text)
  if not venue:continue
  title='';url=page_url
  for a in node.find_all('a',href=True):
   t=clean(a.get_text(' ',strip=True))
   if valid_title(t):title=t;url=urljoin(page_url,a['href']);break
  if not title:
   h=node.find(['h1','h2','h3','h4']);title=clean(h.get_text(' ',strip=True)) if h else ''
  tm=TIME_RE.search(text);e=make_event(title,d,tm.group(1) if tm else '',url,venue,text)
  if e:out.append(e)
 return out
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True);all_events=[];ok_sources=0
  for url in SOURCES:
   if any(k in url for k in PLAIN_FETCH):
    try:events=extract_cards(fetch_plain(url),url);all_events.extend(events);ok_sources+=1;print(f'Discovery {url}: {len(events)} usable events')
    except Exception as exc:print(f'Discovery failed {url}: {exc}')
    continue
   page=await browser.new_page();page.set_default_timeout(25000)
   try:
    await page.goto(url,wait_until='domcontentloaded',timeout=30000)
    try:await page.wait_for_load_state('networkidle',timeout=10000)
    except PlaywrightTimeoutError:pass
    await page.wait_for_timeout(2000);events=extract_cards(await page.content(),page.url);all_events.extend(events);ok_sources+=1;print(f'Discovery {url}: {len(events)} usable events')
   except Exception as exc:print(f'Discovery failed {url}: {exc}')
   finally:await page.close()
  await browser.close()
 data=json.loads(OUT.read_text());merged={}
 key_of=lambda e:(e.get('venue','').lower(),e.get('date',''),title_key(e.get('title','')),e.get('time') or '')
 today=NOW.date().isoformat();stale_before=(NOW-timedelta(days=STALE_DAYS)).date().isoformat()
 # When the calendars loaded properly, a discovery event they have not listed
 # for STALE_DAYS days in a row is dropped (cancelled or moved). If they mostly
 # failed, nothing is dropped.
 healthy=ok_sources>=max(1,len(SOURCES)//2) and len(all_events)>=10
 removed_stale=0;matched=set();brand_new=set()
 for e in data.get('events',[]):
  if not valid_title(e.get('title','')):continue
  e.setdefault('last_seen',today)
  key=key_of(e)
  if key not in merged:merged[key]=e
 for e in all_events:
  key=key_of(e);old=merged.get(key)
  if old is None:
   old=next((x for x in merged.values() if (x.get('venue','').lower(),x.get('date',''))==(e.get('venue','').lower(),e.get('date','')) and id(x) not in matched and same_show(x.get('title',''),e.get('title',''),e.get('venue',''))),None)
  if old is None:merged[key]=dict(e,last_seen=today);matched.add(id(merged[key]));brand_new.add(id(merged[key]));continue
  matched.add(id(old));old['last_seen']=today
  if e.get('promoter'):old['promoter']=e['promoter']  # a venue's listing of a Joy gig gets the Joy sticker
  if not old.get('time') and e.get('time'):old['time']=e['time']  # e.g. Beat Down gives the start the venue page lacks
  if old.get('source')=='discovery':
   # Found again: keep the id, take today's link and details.
   k=key_of(old);merged[k]=dict(e,id=old['id'],last_seen=today,**({'also_ids':old['also_ids']} if old.get('also_ids') else {}),**({'promoter':e.get('promoter') or old['promoter']} if (e.get('promoter') or old.get('promoter')) else {}));matched.add(id(merged[k]))
 for k,e in list(merged.items()):
  if healthy and e.get('source')=='discovery' and id(e) not in matched and str(e.get('last_seen',today))<=stale_before:
   del merged[k];removed_stale+=1
 data['discovery_report']={'calendars_loaded':ok_sources,'calendars':len(SOURCES),'events_found':len(all_events),'rivalcults_unknown_venues':sorted(RIVALCULTS_UNKNOWN)}
 if RIVALCULTS_UNKNOWN:print('Rival Cults venues not in Brighton Weekend yet (add to event-sources.json, index.html and scrape-discovery.py):',', '.join(sorted(RIVALCULTS_UNKNOWN)))
 # Keep ids unique: an existing record keeps its id (saved choices); a new one gets a suffix.
 used=set()
 for e in sorted(merged.values(),key=lambda x:id(x) in brand_new):  # existing records first
  base_id=e['id'];n=2
  while e['id'] in used:e['id']=f'{base_id}-{n}';n+=1
  used.add(e['id'])
 events=prefer_fuller_titles(list(merged.values()))
 data['events']=sorted(events,key=lambda x:(x['date'],x.get('time') or '99:99',x['venue'],x['title']));data['venues']=sorted({e['venue'] for e in events});data['updated']=NOW.date().isoformat();OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');print(f'Merged {len(all_events)} discovery events from {ok_sources}/{len(SOURCES)} calendars; removed after {STALE_DAYS} days unlisted: {removed_stale}; events.json now has {len(events)} events')
if __name__=='__main__':asyncio.run(main())
