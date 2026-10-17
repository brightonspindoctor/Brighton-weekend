"""One-off: how does Meetup publish Brighton Pub Boardgamers' events, and what
do Meetup's and Dice Saloon's robots.txt files allow? Results go in diag/meetup/."""
import json, re, time, asyncio
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

OUT = Path('diag/meetup'); OUT.mkdir(parents=True, exist_ok=True)
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'
GROUP = 'https://www.meetup.com/brighton-pub-boardgamers/'


def get(url, accept='*/*'):
    req = Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'en-GB,en;q=0.9'})
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read().decode('utf-8', 'replace'), r.geturl()
    except HTTPError as e:
        return e.code, dict(e.headers or {}), e.read().decode('utf-8', 'replace')[:20000], url
    except Exception as e:
        return None, {}, f'ERROR {e}', url


report = {}
for name, url in [('meetup_robots', 'https://www.meetup.com/robots.txt'),
                  ('dicesaloon_robots', 'https://www.dicesaloon.com/robots.txt')]:
    st, h, body, final = get(url, 'text/plain')
    (OUT / f'{name}.txt').write_text(body)
    report[name] = {'status': st, 'length': len(body), 'final_url': final}

first_event_url = None
for name, path, ext in [('ical', 'events/ical/', 'ics'), ('rss', 'events/rss/', 'xml'), ('events_page', 'events/', 'html')]:
    st, h, body, final = get(GROUP + path)
    (OUT / f'{name}.{ext}').write_text(body[:3_000_000])
    info = {'status': st, 'final_url': final, 'content_type': h.get('Content-Type') or h.get('content-type'), 'length': len(body)}
    if name == 'ical':
        info['vevents'] = body.count('BEGIN:VEVENT')
        m = re.search(r'^URL[^:]*:(\S+)', body, re.M)
        first_event_url = first_event_url or (m.group(1) if m else None)
    if name == 'rss':
        info['items'] = body.count('<item>')
    if name == 'events_page':
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
        info['next_data'] = bool(m)
        if m:
            (OUT / 'next_data.json').write_text(m.group(1))
            info['apollo_event_keys'] = len(set(re.findall(r'"Event:\d+"', m.group(1))))
        info['jsonld_blocks'] = len(re.findall(r'application/ld\+json', body))
        m2 = re.search(r'https://www\.meetup\.com/brighton-pub-boardgamers/events/\d+/?', body)
        first_event_url = first_event_url or (m2.group(0) if m2 else None)
    report[name] = info
    time.sleep(2)


async def browser_check():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page()
        await page.goto(GROUP + 'events/', wait_until='domcontentloaded', timeout=45000)
        try:
            await page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        html = await page.content()
        (OUT / 'events_page_browser.html').write_text(html[:3_000_000])
        await b.close()
        return {'length': len(html), 'next_data': '__NEXT_DATA__' in html,
                'event_links': len(set(re.findall(r'/brighton-pub-boardgamers/events/\d+', html)))}

try:
    report['events_page_browser'] = asyncio.run(browser_check())
except Exception as exc:
    report['events_page_browser'] = {'error': str(exc)}

report['first_event_url'] = first_event_url
if first_event_url:
    st, h, body, final = get(first_event_url)
    (OUT / 'event_page.html').write_text(body[:3_000_000])
    report['event_page'] = {'status': st, 'length': len(body),
                            'jsonld': [b[:4000] for b in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', body, re.S)]}

(OUT / 'report.json').write_text(json.dumps(report, indent=1, ensure_ascii=False))
print(json.dumps({k: v for k, v in report.items() if k != 'event_page'}, indent=1))
