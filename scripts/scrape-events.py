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
SOURCES=json.loads((ROOT/'event-sources.json').read_text())
OUT=ROOT/'events.json'
TZ=ZoneInfo('Europe/London')
NOW=datetime.now(TZ)
RANGE_START=NOW.date(); RANGE_END=(NOW+timedelta(days=280)).date()
MONTHS=r'Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?'
DATE_RE=re.compile(rf'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\.?\s*(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s*(?:\d{{4}})?|(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?)\b',re.I)
TIME_RE=re.compile(r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b',re.I)
CATEGORIES={'Comedy':['comedy','comedian','stand-up','stand up','laughs'],'Club':['club','dj','dnb','drum & bass','rave','techno','house night','party'],'Theatre':['theatre','theater','play','musical','west end'],'Dance':['dance','ballet','contemporary dance'],'Family':['family','kids','children','storytelling','baby'],'Talk':['talk','in conversation','lecture','spoken word','author'],'Sport':['football','boxing','wrestling','sport','racecourse'],'Music':['gig','live','band','concert','tour','festival','dj set','orchestra','singer']}
GENERIC_TITLES={'comedy','classical music','music','talks & debate','talks and debate','dance','theatre','family',"what's on",'events','upcoming events','get tickets','buy tickets','book tickets','learn more','more info','more info & tickets','find out more','event details','sold out','on sale','on sale today','tickets','read more','view event'}
CTA_PREFIXES=('get tickets','buy tickets','book tickets','learn more','more info','find out more','event details','on sale','sold out')

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def valid_title(title):
    t=clean(title); low=t.lower()
    if not t or low in GENERIC_TITLES:return False
    if any(low.startswith(p) for p in CTA_PREFIXES):return False
    if len(t)<3 or len(t)>180:return False
    return True

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

def parse_dt(value):
    if not value:return None
    try:
        dt=dateparser.parse(clean(str(value)),dayfirst=True,fuzzy=True,default=datetime(NOW.year,1,1))
        if not dt:return None
        return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
    except Exception:return None

def normalise(raw,venue,page_url):
    title=clean(raw.get('name') or raw.get('title')); start_raw=raw.get('startDate') or raw.get('start_date') or raw.get('date'); start=parse_dt(start_raw)
    if not valid_title(title) or not start or not (RANGE_START<=start.date()<=RANGE_END):return None
    blob=clean(' '.join(str(raw.get(k,'')) for k in ('name','description','status'))).lower()
    if any(x in blob for x in ('cancelled','canceled','postponed','event cancelled')):return None
    end=parse_dt(raw.get('endDate') or raw.get('end_date')); offers=raw.get('offers'); offer_url=offers.get('url') if isinstance(offers,dict) else None
    url=urljoin(page_url,raw.get('url') or offer_url or page_url)
    ident=re.sub(r'[^a-z0-9]+','-',f'{start.date()}-{venue}-{title}'.lower()).strip('-')[:180]
    return {'id':ident,'title':title,'date':start.date().isoformat(),'venue':venue,'time':start.strftime('%H:%M') if start_raw and re.search(r'T|\d{1,2}:\d{2}|am|pm',str(start_raw),re.I) else '','finish_time':end.strftime('%H:%M') if end else '','category':category(title,raw.get('description','')),'ticket_url':url}

def jsonld_events(html,venue,page_url):
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
            if any(str(t).lower()=='event' for t in types):
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
        if not valid_title(title):continue
        times=TIME_RE.findall(text);tm=times[0] if times else None;end_tm=times[-1] if len(times)>1 else None
        raw={'name':title,'startDate':f'{dt.date().isoformat()}T{tm or "00:00"}','url':href,'description':text}
        if end_tm:raw['endDate']=f'{dt.date().isoformat()}T{end_tm}'
        e=normalise(raw,venue,page_url)
        if e:
            if not tm:e['time']=''
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
    venue=source['venue'];is_dome_search='brightondome.org/search/' in source['url']
    events=jsonld_events(html,venue,final)
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
    all_events=[];successful=0;failures=[]
    for source,(events,err) in zip(SOURCES,results):
        if err:failures.append(f"{source['venue']}: {err}");continue
        successful+=1;all_events.extend(events);print(f"{source['venue']}: {len(events)} events")
    scraped={}
    for e in all_events:
        key=(e['venue'].lower(),e['date'],re.sub(r'[^a-z0-9]+',' ',e['title'].lower()).strip());old=scraped.get(key)
        if old is None or (not old.get('time') and e.get('time')):scraped[key]=e
    existing=json.loads(OUT.read_text()) if OUT.exists() else {};retained={};removed_generic=0
    for e in existing.get('events',[]):
        try:d=datetime.fromisoformat(e['date']).date()
        except Exception:continue
        if RANGE_START<=d<=RANGE_END:
            if not valid_title(e.get('title','')):
                removed_generic+=1;continue
            key=(e.get('venue','').lower(),e.get('date',''),re.sub(r'[^a-z0-9]+',' ',e.get('title','').lower()).strip());retained[key]=e
    for k,e in scraped.items():
        old=retained.get(k)
        if old is None or (not old.get('time') and e.get('time')):retained[k]=e
    events=sorted(retained.values(),key=lambda x:(x['date'],x.get('time') or '99:99',x['venue'],x['title']))
    existing_future=sum(1 for e in existing.get('events',[]) if e.get('date','')>=RANGE_START.isoformat() and valid_title(e.get('title','')))
    print(f'Successful sources: {successful}/{len(SOURCES)}; scraped: {len(scraped)}; retained future: {existing_future}; removed generic: {removed_generic}; final: {len(events)}')
    if failures:
        print('Source failures:',file=sys.stderr)
        for f in failures:print(' - '+f,file=sys.stderr)
    if successful<max(12,int(len(SOURCES)*.70)):raise SystemExit('Too many venue sources failed; refusing to replace events.json')
    if len(scraped)<80:raise SystemExit('Too few events scraped; refusing to refresh events.json')
    if existing_future and len(events)<int(existing_future*.95):raise SystemExit('Unexpected loss of future events; refusing to replace events.json')
    OUT.write_text(json.dumps({'updated':NOW.date().isoformat(),'range_start':RANGE_START.isoformat(),'range_end':RANGE_END.isoformat(),'venues':sorted({e['venue'] for e in events}),'events':events},ensure_ascii=False,indent=2)+'\n')
    print(f'Wrote {OUT} with {len(events)} events')

if __name__=='__main__':asyncio.run(main())