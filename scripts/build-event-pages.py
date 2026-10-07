#!/usr/bin/env python3
"""Build the static, shareable pages that link previews and Google can read.

The app itself is one JavaScript page, so a WhatsApp, Instagram or Facebook
preview of any link only ever saw "Brighton Weekend", and Google had nothing
to index per event. This script writes plain HTML that needs no JavaScript:

  e/<event id>/index.html   one page per event in events.json, with Open Graph
                            tags (the preview card) and schema.org Event data
  this-weekend/index.html   everything on this Friday to Sunday, for searches
                            like "gigs in Brighton this weekend"
  sitemap.xml               every page above, for Google Search Console

A shared event link carries ?share=1 (and any group invite). Someone who taps
it is sent straight on into the app; crawlers and Google never run that
script, so they read the page itself.

The e/ folder is rebuilt from scratch each run, so pages for events that have
dropped out of events.json disappear. 404.html sends those old links into the
app, which already handles unknown or merged event ids.

Run from the repo root:  python scripts/build-event-pages.py [--today YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SITE = 'https://brightonweekend.co.uk'
LONDON = ZoneInfo('Europe/London')
ROOT = Path(__file__).resolve().parent.parent
OG_IMAGE = f'{SITE}/og-image.jpg'
ID_OK = re.compile(r'^[a-z0-9][a-z0-9-]{0,150}$')
TIME_OK = re.compile(r'^\d\d:\d\d$')

# How each category reads in a sentence ("3 gigs, 2 comedy nights").
CATEGORY_NOUNS = {
    'Music': ('gig', 'gigs'), 'Music/Club': ('gig', 'gigs'),
    'Club': ('club night', 'club nights'), 'Comedy': ('comedy night', 'comedy nights'),
    'Theatre': ('theatre show', 'theatre shows'), 'Family': ('family event', 'family events'),
    'Talk': ('talk', 'talks'), 'Dance': ('dance show', 'dance shows'), 'Sport': ('sports event', 'sports events'),
}

esc = html.escape


def long_date(d: date) -> str:
    return f'{d:%A} {d.day} {d:%B %Y}'


def short_date(d: date) -> str:
    return f'{d:%a} {d.day} {d:%b}'


def iso_at(d: date, hhmm: str) -> str:
    h, m = map(int, hhmm.split(':'))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=LONDON).isoformat()


def time_text(e: dict) -> str:
    start, end = e.get('time') or '', e.get('finish_time') or ''
    if TIME_OK.match(start) and TIME_OK.match(end):
        return f'{start} – {end}'
    return start if TIME_OK.match(start) else ''


def ticket_url(e: dict) -> str:
    u = (e.get('ticket_url') or '').strip()
    return u if u.startswith(('https://', 'http://')) else ''


def event_url(e: dict) -> str:
    return f'{SITE}/e/{e["id"]}/'


def summary(e: dict, d: date) -> str:
    """One line for the preview card and meta description."""
    bits = [short_date(d)]
    if TIME_OK.match(e.get('time') or ''):
        bits.append(e['time'])
    bits.append(f'{e["venue"]}, Brighton')
    line = ' · '.join(bits)
    if (e.get('status') or '').upper() == 'SOLD OUT':
        line += ' · Sold out'
    return line + '. Plan it with your mates on Brighton Weekend.'


def event_json_ld(e: dict, d: date) -> str:
    start = e.get('time') or ''
    data = {
        '@context': 'https://schema.org',
        '@type': 'Event',
        'name': e['title'],
        'startDate': iso_at(d, start) if TIME_OK.match(start) else d.isoformat(),
        'eventAttendanceMode': 'https://schema.org/OfflineEventAttendanceMode',
        'eventStatus': 'https://schema.org/EventScheduled',
        'location': {
            '@type': 'Place',
            'name': e['venue'],
            # Town only: street addresses aren't in the data, and we don't guess.
            'address': {'@type': 'PostalAddress', 'addressLocality': 'Brighton and Hove',
                        'addressRegion': 'East Sussex', 'addressCountry': 'GB'},
        },
        'image': [OG_IMAGE],
        'description': f'{e.get("category") or "Event"} at {e["venue"]}, Brighton, on {long_date(d)}.',
        'url': event_url(e),
    }
    end = e.get('finish_time') or ''
    if TIME_OK.match(start) and TIME_OK.match(end):
        end_day = d + timedelta(days=1) if end <= start else d  # club nights run past midnight
        data['endDate'] = iso_at(end_day, end)
    if ticket_url(e):
        offer = {'@type': 'Offer', 'url': ticket_url(e)}
        if (e.get('status') or '').upper() == 'SOLD OUT':
            offer['availability'] = 'https://schema.org/SoldOut'
        data['offers'] = offer
    if e.get('promoter'):
        data['organizer'] = {'@type': 'Organization', 'name': e['promoter']}
    # "</" inside a <script> block would end it early.
    return json.dumps(data, ensure_ascii=False, indent=1).replace('</', '<\\/')


STYLE = """
@font-face{font-family:"Plus Jakarta Sans";font-style:normal;font-weight:400 800;font-display:swap;src:url("/fonts/plus-jakarta-sans-latin.woff2") format("woff2")}
:root{--abyss:#08141F;--navy:#0B1D2F;--card:#102536;--raised:#173347;--line:#294657;--cream:#F3E4C9;--muted:#A7B5BE;--subtle:#8095A3;--coral:#FF7767;--coral-ink:#0B1D2F;--teal:#4DB6AC}
*{box-sizing:border-box}
body{margin:0;background:var(--abyss);color:var(--cream);font-family:"Plus Jakarta Sans",system-ui,sans-serif;line-height:1.55}
a{color:var(--teal)}
.bar{background:var(--navy);border-bottom:1px solid var(--line);padding:12px 16px}
.bar a{display:flex;align-items:center;gap:12px;max-width:760px;margin:auto;color:var(--cream);text-decoration:none;font-weight:800;letter-spacing:.02em}
.bar img{width:40px;height:40px;border-radius:11px}
main{max-width:760px;margin:24px auto 48px;padding:0 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:24px}
.pill{display:inline-block;font-size:13px;font-weight:700;color:var(--muted);background:var(--raised);border-radius:999px;padding:3px 11px;margin:0 6px 10px 0}
.pill.sold{color:#FFB5B0;background:#351F24}
h1{font-size:30px;line-height:1.2;margin:0 0 14px;overflow-wrap:anywhere}
h2{font-size:19px;margin:30px 0 10px}
.facts{margin:0;padding:0;list-style:none;color:var(--muted)}
.facts li{margin:3px 0}.facts strong{color:var(--cream)}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}
.btn{display:inline-block;border-radius:12px;padding:12px 18px;font-weight:700;text-decoration:none}
.btn.go{background:var(--coral);color:var(--coral-ink)}
.btn.alt{border:1px solid var(--line);color:var(--cream)}
.list{list-style:none;margin:0;padding:0}
.list li{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--line)}
.list .t{flex:0 0 48px;color:var(--subtle);font-variant-numeric:tabular-nums}
.list a{color:var(--cream);font-weight:700;text-decoration:none}.list a:hover{text-decoration:underline}
.list .v{display:block;color:var(--muted);font-size:14px}
.lede{color:var(--muted);margin:-6px 0 18px}
footer{max-width:760px;margin:0 auto 40px;padding:0 16px;color:var(--subtle);font-size:14px}
footer a{color:var(--subtle);margin-right:14px}
@media(max-width:600px){h1{font-size:25px}.card{padding:18px}}
"""

STYLE_VERSION = __import__('hashlib').sha1(STYLE.encode()).hexdigest()[:8]

CSP = ("default-src 'self'; script-src 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; object-src 'none'")


def page(*, title: str, description: str, url: str, og_title: str, body: str,
         head_extra: str = '', script: str = '') -> str:
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Brighton Weekend">
<meta property="og:locale" content="en_GB">
<meta property="og:url" content="{esc(url)}">
<meta property="og:title" content="{esc(og_title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Brighton Weekend">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0B1D2F">
<link rel="icon" type="image/png" sizes="32x32" href="/icons/icon-32.png?v=70">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png?v=70">
{head_extra}<link rel="stylesheet" href="/pages.css?v={STYLE_VERSION}">
</head>
<body>
<header class="bar"><a href="/"><img src="/icons/icon-192.png?v=70" alt="">BRIGHTON WEEKEND</a></header>
<main>
{body}
</main>
<footer><a href="/">Open the app</a><a href="/this-weekend/">This weekend</a><a href="/about.html">About</a><a href="/privacy.html">Privacy</a></footer>
{script}</body>
</html>
"""


def listing(items: list[tuple[dict, date]], show_day: bool = False) -> str:
    rows = []
    for e, d in items:
        t = e['time'] if TIME_OK.match(e.get('time') or '') else ''
        cat = e.get('category') if e.get('category') not in (None, '', 'Other') else ''
        venue = ' · '.join(x for x in (e['venue'], cat) if x)
        when = short_date(d) if show_day else t
        rows.append(f'<li><span class="t">{esc(when)}</span><span><a href="/e/{e["id"]}/">{esc(e["title"])}</a>'
                    f'<span class="v">{esc(venue)}</span></span></li>')
    return '<ul class="list">' + ''.join(rows) + '</ul>'


def sort_key(item):
    e, d = item
    t = e.get('time') or ''
    return (d, t if TIME_OK.match(t) else '99:99', e['title'].lower())


def event_page(e: dict, d: date, same_day: list[tuple[dict, date]]) -> str:
    cat = e.get('category') if e.get('category') not in (None, '', 'Other') else ''
    pills = ''.join(f'<span class="pill">{esc(p)}</span>' for p in (cat, e.get('genre') or '') if p)
    if (e.get('status') or '').upper() == 'SOLD OUT':
        pills += '<span class="pill sold">Sold out</span>'
    facts = [f'<li><strong>{esc(long_date(d))}</strong></li>']
    if time_text(e):
        facts.append(f'<li>{esc(time_text(e))}</li>')
    facts.append(f'<li>{esc(e["venue"])}, Brighton</li>')
    if e.get('price'):
        facts.append(f'<li>{esc(e["price"])}</li>')
    if e.get('promoter'):
        facts.append(f'<li>Promoted by {esc(e["promoter"])}</li>')
    tickets = f'<a class="btn alt" href="{esc(ticket_url(e))}" rel="noopener">Tickets ↗</a>' if ticket_url(e) else ''
    app_link = f'/?event={e["id"]}'
    others = [x for x in same_day if x[0]['id'] != e['id']][:8]
    more = f'<h2>Also on {d:%A}</h2>{listing(others)}' if others else ''
    body = f"""<article class="card">
{pills and f'<div>{pills}</div>'}
<h1>{esc(e['title'])}</h1>
<ul class="facts">{''.join(facts)}</ul>
<div class="actions"><a class="btn go" href="{esc(app_link)}">Plan it with friends</a>{tickets}</div>
{more}
<p style="margin-top:26px"><a href="/this-weekend/">See everything on in Brighton this weekend →</a></p>
</article>"""
    # People arriving from a shared link go straight into the app (with any
    # group invite). Crawlers don't run this, so they read the page above.
    script = f"""<script>(function(){{var q=new URLSearchParams(location.search);if(!q.has('share')&&!q.has('group_invite'))return;q.delete('share');q.set('event',{json.dumps(e['id'])});location.replace('/?'+q.toString());}})();</script>
"""
    title = f'{e["title"]} – {e["venue"]}, Brighton, {short_date(d)} | Brighton Weekend'
    return page(title=title, description=summary(e, d), url=event_url(e), og_title=e['title'], body=body,
                head_extra=f'<script type="application/ld+json">\n{event_json_ld(e, d)}\n</script>\n', script=script)


def weekend_window(today: date) -> tuple[date, date]:
    """Friday to Sunday of this weekend; from Friday onwards, today to Sunday."""
    wd = today.weekday()  # Monday 0 … Sunday 6
    if wd >= 4:
        return today, today + timedelta(days=6 - wd)
    return today + timedelta(days=4 - wd), today + timedelta(days=6 - wd)


def count_phrase(items: list[tuple[dict, date]]) -> str:
    counts: dict[tuple, int] = {}
    for e, _ in items:
        noun = CATEGORY_NOUNS.get(e.get('category') or '')
        if noun:
            counts[noun] = counts.get(noun, 0) + 1
    parts = [f'{n} {noun[0] if n == 1 else noun[1]}' for noun, n in sorted(counts.items(), key=lambda kv: -kv[1])][:3]
    if not parts:
        return ''
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]


def weekend_page(items: list[tuple[dict, date]], start: date, end: date) -> str:
    span = f'{start:%A} {start.day} – {end:%A} {end.day} {end:%B}' if start != end else long_date(start)
    counts = count_phrase(items)
    desc = (f'{counts} in Brighton & Hove, {span}. ' if counts else f'What’s on in Brighton & Hove, {span}. ') + \
        'Gigs, comedy, club nights and theatre, updated every morning.'
    days = []
    d = start
    while d <= end:
        today_items = [x for x in items if x[1] == d]
        days.append(f'<h2>{esc(long_date(d))}</h2>' +
                    (listing(today_items) if today_items else '<p class="lede">Nothing listed yet.</p>'))
        d += timedelta(days=1)
    body = f"""<article class="card">
<h1>What’s on in Brighton this weekend</h1>
<p class="lede">{esc(span)} · gigs, comedy, club nights and theatre across Brighton &amp; Hove</p>
<div class="actions" style="margin:0 0 6px"><a class="btn go" href="/">Plan your weekend with friends</a></div>
{''.join(days)}
</article>"""
    return page(title=f'What’s on in Brighton this weekend: gigs, comedy & club nights ({short_date(start)}–{short_date(end)}) | Brighton Weekend',
                description=desc, url=f'{SITE}/this-weekend/', og_title='What’s on in Brighton this weekend', body=body)


def sitemap(urls: list[str], today: date) -> str:
    rows = ''.join(f'<url><loc>{esc(u)}</loc>{f"<lastmod>{today.isoformat()}</lastmod>" if lm else ""}</url>\n'
                   for u, lm in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}</urlset>\n'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--today', help='Pretend it is this date (YYYY-MM-DD), for testing')
    args = ap.parse_args()
    today = date.fromisoformat(args.today) if args.today else datetime.now(LONDON).date()

    data = json.loads((ROOT / 'events.json').read_text(encoding='utf-8'))
    items, seen = [], set()
    for e in data.get('events', []):
        try:
            d = date.fromisoformat(e.get('date') or '')
        except ValueError:
            continue
        if not ID_OK.match(str(e.get('id') or '')) or e['id'] in seen or not e.get('title') or not e.get('venue'):
            continue
        if d < today:
            continue
        seen.add(e['id'])
        items.append((e, d))
    items.sort(key=sort_key)

    by_day: dict[date, list] = {}
    for x in items:
        by_day.setdefault(x[1], []).append(x)

    (ROOT / 'pages.css').write_text(STYLE.lstrip(), encoding='utf-8')
    out = ROOT / 'e'
    if out.exists():
        shutil.rmtree(out)
    for e, d in items:
        p = out / e['id']
        p.mkdir(parents=True)
        (p / 'index.html').write_text(event_page(e, d, by_day[d]), encoding='utf-8')

    start, end = weekend_window(today)
    weekend = [x for x in items if start <= x[1] <= end]
    wk = ROOT / 'this-weekend'
    wk.mkdir(exist_ok=True)
    (wk / 'index.html').write_text(weekend_page(weekend, start, end), encoding='utf-8')

    urls = [(f'{SITE}/', True), (f'{SITE}/this-weekend/', True), (f'{SITE}/about.html', False)]
    urls += [(event_url(e), False) for e, _ in items]
    (ROOT / 'sitemap.xml').write_text(sitemap(urls, today), encoding='utf-8')
    print(f'Built {len(items)} event pages, this-weekend ({len(weekend)} events, {start}–{end}) and sitemap.xml')


if __name__ == '__main__':
    main()
