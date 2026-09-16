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

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'events.json'; TZ=ZoneInfo('Europe/London'); NOW=datetime.now(TZ); START=NOW.date(); END=(NOW+timedelta(days=280)).date()
VENUES={"Brighton Centre","CHALK","Concorde 2","The Old Market","Green Door Store","Volks","Quarters","Patterns","DUST","Komedia","The Forge Comedy Club","Theatre Royal Brighton","The Hope & Ruin","The Prince Albert","A L P H A B E T","The Pipeline","Brighton Racecourse","The Gladstone","Babble","Shelter Hall","Amex Stadium"}
SOURCES=["https://www.visitbrighton.com/whats-on/Brighton","https://www.eventbrite.co.uk/d/united-kingdom--brighton/events/"]
MONTHS=r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
DATE_RE=re.compile(rf"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\.?\s*(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s*(?:\d{{4}})?|(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?)\b",re.I); TIME_RE=re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",re.I)
GENERIC_TITLES={'comedy','classical music','music','talks & debate','talks and debate','dance','theatre','family',"what's on",'events','upcoming events','get tickets','buy tickets','book tickets','learn more','more info','more info & tickets','find out more','event details','sold out','on sale','on sale today','tickets','read more','view event'}
CTA_PREFIXES=('get tickets','buy tickets','book tickets','learn more','more info','find out more','event details','on sale','sold out')
def clean(s):return re.sub(r"\s+"," ",s or "").strip()
def valid_title(title):
 t=clean(title);low=t.lower()
 if not t or low in GENERIC_TITLES:return False
 if any(low.startswith(p) for p in CTA_PREFIXES):return False
 return 3<=len(t)<=180
def title_key(title):return re.sub(r'[^a-z0-9]+',' ',clean(title).lower()).strip()
def fuller_title(a,b):
 ka,kb=title_key(a),title_key(b)
 if ka==kb:return a if len(a)>=len(b) else b
 if ka and kb and (ka.startswith(kb+' ') or kb.startswith(ka+' ')):
  return a if len(ka)>len(kb) else b
 return None
def prefer_fuller_titles(events):
 groups={}
 for e in events:groups.setdefault((e.get('venue','').lower(),e.get('date','')),[]).append(e)
 kept=[]
 for group in groups.values():
  group=sorted(group,key=lambda e:len(title_key(e.get('title',''))),reverse=True);chosen=[]
  for e in group:
   if not valid_title(e.get('title','')):continue
   if not any(fuller_title(x.get('title',''),e.get('title','')) for x in chosen):chosen.append(e)
  kept.extend(chosen)
 return kept
def parse_date(s):
 try:
  d=dateparser.parse(clean(s),dayfirst=True,fuzzy=True,default=datetime(START.year,1,1));return d.date() if d else None
 except Exception:return None
def venue_from_text(text):
 low=clean(text).lower()
 for v in sorted(VENUES,key=len,reverse=True):
  if v.lower() in low:return v
 for a,v in {"concorde2":"Concorde 2","concorde 2":"Concorde 2","theatre royal":"Theatre Royal Brighton"}.items():
  if a in low:return v
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
 ident=re.sub(r'[^a-z0-9]+','-',f'{date}-{venue}-{title}'.lower()).strip('-')[:180]
 return {'id':ident,'title':title,'date':date.isoformat(),'venue':venue,'time':time or '','finish_time':'','category':category(title,text),'ticket_url':url}
def extract_cards(html,page_url):
 soup=BeautifulSoup(html,'html.parser');out=[]
 for tag in soup.find_all('script',attrs={'type':re.compile('ld\\+json',re.I)}):
  try:data=json.loads(tag.string or tag.get_text())
  except Exception:continue
  stack=data if isinstance(data,list) else [data]
  while stack:
   obj=stack.pop()
   if isinstance(obj,list):stack.extend(obj);continue
   if not isinstance(obj,dict):continue
   if isinstance(obj.get('@graph'),list):stack.extend(obj['@graph'])
   typ=obj.get('@type','');types=typ if isinstance(typ,list) else [typ]
   if not any(str(t).lower()=='event' for t in types):continue
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
  browser=await p.chromium.launch(headless=True);all_events=[]
  for url in SOURCES:
   page=await browser.new_page();page.set_default_timeout(25000)
   try:
    await page.goto(url,wait_until='domcontentloaded',timeout=30000)
    try:await page.wait_for_load_state('networkidle',timeout=10000)
    except PlaywrightTimeoutError:pass
    await page.wait_for_timeout(2000);events=extract_cards(await page.content(),page.url);all_events.extend(events);print(f'Discovery {url}: {len(events)} usable events')
   except Exception as exc:print(f'Discovery failed {url}: {exc}')
   finally:await page.close()
  await browser.close()
 data=json.loads(OUT.read_text());merged={}
 for e in data.get('events',[]):
  if not valid_title(e.get('title','')):continue
  key=(e.get('venue','').lower(),e.get('date',''),title_key(e.get('title','')));old=merged.get(key)
  if old is None or (not old.get('time') and e.get('time')):merged[key]=e
 for e in all_events:
  key=(e['venue'].lower(),e['date'],title_key(e['title']));old=merged.get(key)
  if old is None or (not old.get('time') and e.get('time')):merged[key]=e
 events=prefer_fuller_titles(list(merged.values()))
 data['events']=sorted(events,key=lambda x:(x['date'],x.get('time') or '99:99',x['venue'],x['title']));data['venues']=sorted({e['venue'] for e in events});data['updated']=NOW.date().isoformat();OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');print(f'Merged {len(all_events)} discovery events; events.json now has {len(events)} events')
if __name__=='__main__':asyncio.run(main())
