#!/usr/bin/env python3
"""Build the static, shareable pages that link previews and Google can read.

The app itself is one JavaScript page, so a WhatsApp, Instagram or Facebook
preview of any link only ever saw "Brighton Weekend", and Google had nothing
to index per event. This script writes plain HTML that needs no JavaScript:

  e/<event id>/index.html   one page per event in events.json, with Open Graph
                            tags (the preview card) and schema.org Event data
  this-weekend/index.html   everything on this Friday to Sunday, for searches
                            like "gigs in Brighton this weekend"
  tonight/index.html        what's on tonight ("what's on in Brighton tonight")
  gigs/, comedy/, club-nights/, theatre/
                            the next 30 days of each kind of night out
  venues/index.html         every venue, and venues/<venue>/ for each one
                            ("what's on at CHALK Brighton")
  sitemap.xml               every page above, for Google Search Console

A shared event link carries ?share=1. Someone who taps it is sent straight on
into the app; crawlers and Google never run that script, so they read the page
itself.

pages.css, written here too, is the stylesheet for these pages and for the
About, Privacy, Terms and 404 pages (which are kept by hand in the same layout).

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
    return f'{kind_text(e)} · {line}. Tickets, times and who else is going, on Brighton Weekend.'


def kind_text(e: dict) -> str:
    """'Indie & Rock gig', 'Comedy night', or plain 'Event'."""
    noun = CATEGORY_NOUNS.get(e.get('category') or '')
    kind = noun[0] if noun else 'event'
    return f'{e["genre"]} {kind}' if e.get('genre') else kind[:1].upper() + kind[1:]


def event_description(e: dict, d: date) -> str:
    when = long_date(d) + (f' at {e["time"]}' if TIME_OK.match(e.get('time') or '') else '')
    sold = ' Sold out.' if (e.get('status') or '').upper() == 'SOLD OUT' else ''
    return f'{kind_text(e)} at {e["venue"]}, Brighton, on {when}.{sold}'


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
        'description': event_description(e, d),
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
    if venue_slug(e['venue']):
        data['location']['url'] = f'{SITE}/venues/{venue_slug(e["venue"])}/'
    if e.get('promoter'):
        data['organizer'] = {'@type': 'Organization', 'name': e['promoter']}
    return json_ld(data)


def ics_escape(s: str) -> str:
    return (str(s or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r\n', '\\n').replace('\n', '\\n'))


def ics_fold(line: str) -> str:
    """Lines over 75 bytes continue on the next line after a space (RFC 5545)."""
    if len(line.encode()) <= 75:
        return line
    out, cur, n = [], '', 0
    for ch in line:
        b = len(ch.encode())
        if n + b > (74 if out else 75):
            out.append(cur)
            cur, n = '', 0
        cur += ch
        n += b
    out.append(cur)
    return '\r\n '.join(out)


def event_ics(e: dict, d: date) -> str:
    """One event as an .ics file. London times are written as UTC, so the file
    needs no time-zone block; an event with no start time is all day. DTSTAMP
    comes from the event's date, not the clock, so a file only changes when
    the event does (otherwise every daily build would rewrite all of them)."""
    utc = ZoneInfo('UTC')
    stamp = lambda t: t.astimezone(utc).strftime('%Y%m%dT%H%M%SZ')
    start, end = e.get('time') or '', e.get('finish_time') or ''
    if TIME_OK.match(start):
        h, m = map(int, start.split(':'))
        s_dt = datetime(d.year, d.month, d.day, h, m, tzinfo=LONDON)
        if TIME_OK.match(end):
            h2, m2 = map(int, end.split(':'))
            end_day = d + timedelta(days=1) if end <= start else d  # club nights run past midnight
            e_dt = datetime(end_day.year, end_day.month, end_day.day, h2, m2, tzinfo=LONDON)
        else:
            e_dt = s_dt + timedelta(hours=3)  # no published finish: assume three hours
        when = [f'DTSTART:{stamp(s_dt)}', f'DTEND:{stamp(e_dt)}']
    else:
        when = [f'DTSTART;VALUE=DATE:{d:%Y%m%d}', f'DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}']
    details = '\n'.join(x for x in (f'Tickets: {ticket_url(e)}' if ticket_url(e) else '',
                                     f'Price: {e["price"]}' if e.get('price') else '',
                                     f'More: {event_url(e)}') if x)
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Brighton Weekend//brightonweekend.co.uk//EN',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'BEGIN:VEVENT',
             f'UID:{e["id"]}@brightonweekend.co.uk', f'DTSTAMP:{d:%Y%m%d}T000000Z', *when,
             f'SUMMARY:{ics_escape(e["title"])}', f'LOCATION:{ics_escape(e["venue"] + ", Brighton")}',
             f'DESCRIPTION:{ics_escape(details)}', f'URL:{event_url(e)}', 'END:VEVENT', 'END:VCALENDAR']
    return '\r\n'.join(ics_fold(x) for x in lines) + '\r\n'


STYLE = """
@font-face{font-family:"Plus Jakarta Sans";font-style:normal;font-weight:400 800;font-display:swap;src:url("/fonts/plus-jakarta-sans-latin.woff2") format("woff2")}
:root{--abyss:#08141F;--navy:#0B1D2F;--card:#102536;--raised:#173347;--line:#294657;--cream:#F3E4C9;--muted:#A7B5BE;--subtle:#8095A3;--coral:#FF7767;--coral-ink:#0B1D2F;--teal:#4DB6AC;--pass-fg:#FFB5B0;--pass-bg:#351F24}
*{box-sizing:border-box}
body{margin:0;background:var(--abyss);color:var(--cream);font-family:"Plus Jakarta Sans",system-ui,sans-serif;line-height:1.55}
a{color:var(--teal)}
.bar{background:var(--navy);border-bottom:1px solid var(--line);padding:12px 16px}
.bar a{display:flex;align-items:center;gap:12px;max-width:760px;margin:auto;color:var(--cream);text-decoration:none;font-weight:800;letter-spacing:.02em}
.bar img{width:40px;height:40px;border-radius:11px}
main{max-width:760px;margin:24px auto 48px;padding:0 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:24px}
.pill{display:inline-block;font-size:13px;font-weight:700;color:var(--muted);background:var(--raised);border-radius:999px;padding:3px 11px;margin:0 6px 10px 0}
.pill.sold{color:var(--pass-fg);background:var(--pass-bg)}
h1{font-size:30px;line-height:1.2;margin:0 0 14px;overflow-wrap:anywhere}
h2{font-size:19px;margin:30px 0 10px}
h3{font-size:16px;margin:22px 0 6px}
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
.actions.first{margin:0 0 6px}
.more-link{margin-top:26px}
button.btn{border:0;font-family:inherit;font-size:inherit;cursor:pointer}
.note{color:var(--muted);font-size:14px;margin:8px 0 0}
/* About, Privacy and Terms */
.meta{color:var(--muted);font-size:14px;margin:0 0 18px}
.notice{background:var(--raised);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:15px;margin:12px 0}
th,td{text-align:left;vertical-align:top;padding:9px 10px;border-bottom:1px solid var(--line)}
th{background:var(--raised)}
footer a{display:inline-block;margin-bottom:6px}
.crumbs{font-size:14px;color:var(--subtle);margin:0 0 10px}.crumbs a{color:var(--muted)}
.list.dated .t{flex-basis:86px}
.hubs{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 0;padding:0;list-style:none}
.hubs a{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:6px 13px;color:var(--cream);text-decoration:none;font-size:14px;font-weight:700}
.hubs a[aria-current]{background:var(--raised)}
@media(max-width:600px){h1{font-size:25px}.card{padding:18px}}
"""

STYLE_VERSION = __import__('hashlib').sha1(STYLE.encode()).hexdigest()[:8]

SUPABASE_URL = 'https://zqvccsnfrkrtcsitfwcd.supabase.co'
SUPABASE_KEY = 'sb_publishable_IyzJ6iCrIIkCtYBhNkQUog_GelEFKo1'  # public key, same as index.html

CSP = ("default-src 'self'; script-src 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       f"img-src 'self'; font-src 'self'; connect-src {SUPABASE_URL}; "
       "base-uri 'none'; form-action 'none'; object-src 'none'")


# Every page links to the guides, so search engines find them all and people
# can move between them. The hand-kept pages (About, Privacy, Terms, 404) use
# the same footer.
FOOTER = ('<footer><a href="/">Open the app</a><a href="/tonight/">Tonight</a><a href="/this-weekend/">This weekend</a>'
          '<a href="/gigs/">Gigs</a><a href="/comedy/">Comedy</a><a href="/club-nights/">Club nights</a>'
          '<a href="/theatre/">Theatre</a><a href="/venues/">Venues</a>'
          '<a href="/about.html">About</a><a href="/privacy.html">Privacy</a><a href="/terms.html">Terms</a></footer>')


def json_ld(data: dict) -> str:
    # "</" inside a <script> block would end it early.
    return ('<script type="application/ld+json">\n'
            + json.dumps(data, ensure_ascii=False, indent=1).replace('</', '<\\/') + '\n</script>\n')


def breadcrumbs(trail: list[tuple[str, str]]) -> str:
    """schema.org BreadcrumbList, so results show "Brighton Weekend › Venues › CHALK"."""
    return json_ld({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': u} for i, (n, u) in enumerate(trail)]})


def crumb_nav(trail: list[tuple[str, str]]) -> str:
    """The same trail, visible above the heading (the last step is this page)."""
    links = [f'<a href="{esc(u.removeprefix(SITE))}">{esc(n)}</a>' for n, u in trail[:-1]]
    return f'<nav class="crumbs" aria-label="Breadcrumb">{" › ".join(links)}</nav>' if links else ''


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
{FOOTER}
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
    return f'<ul class="list{" dated" if show_day else ""}">' + ''.join(rows) + '</ul>'


def sort_key(item):
    e, d = item
    t = e.get('time') or ''
    return (d, t if TIME_OK.match(t) else '99:99', e['title'].lower())


# Venues with their own page. Sport grounds are left out (sport isn't what the
# app is for), and so is "Other".
NO_VENUE_PAGE = {'Other', 'Amex Stadium', 'Brighton Racecourse'}


def venue_slug(venue: str) -> str:
    if venue in NO_VENUE_PAGE:
        return ''
    return re.sub(r'[^a-z0-9]+', '-', venue.lower().replace('&', ' and ').replace("'", '')).strip('-')


def event_trail(e: dict) -> list[tuple[str, str]]:
    trail = [('Brighton Weekend', f'{SITE}/')]
    if venue_slug(e['venue']):
        trail += [('Venues', f'{SITE}/venues/'), (e['venue'], f'{SITE}/venues/{venue_slug(e["venue"])}/')]
    return trail + [(e['title'], event_url(e))]


def event_page(e: dict, d: date, same_day: list[tuple[dict, date]]) -> str:
    cat = e.get('category') if e.get('category') not in (None, '', 'Other') else ''
    pills = ''.join(f'<span class="pill">{esc(p)}</span>' for p in (cat, e.get('genre') or '') if p)
    if (e.get('status') or '').upper() == 'SOLD OUT':
        pills += '<span class="pill sold">Sold out</span>'
    facts = [f'<li><strong>{esc(long_date(d))}</strong></li>']
    if time_text(e):
        facts.append(f'<li>{esc(time_text(e))}</li>')
    vslug = venue_slug(e['venue'])
    facts.append(f'<li><a href="/venues/{vslug}/">{esc(e["venue"])}</a>, Brighton</li>' if vslug else f'<li>{esc(e["venue"])}, Brighton</li>')
    if e.get('price'):
        facts.append(f'<li>{esc(e["price"])}</li>')
    if e.get('promoter'):
        facts.append(f'<li>Promoted by {esc(e["promoter"])}</li>')
    tickets = f'<a class="btn alt" href="{esc(ticket_url(e))}" rel="noopener" data-ticket-event="{esc(e['id'])}">Tickets ↗</a>' if ticket_url(e) else ''
    app_link = f'/?event={e["id"]}'
    others = [x for x in same_day if x[0]['id'] != e['id']][:8]
    more = f'<h2>Also on {d:%A}</h2>{listing(others)}' if others else ''
    trail = event_trail(e)
    body = f"""<article class="card">
{crumb_nav(trail)}
{pills and f'<div>{pills}</div>'}
<h1>{esc(e['title'])}</h1>
<ul class="facts">{''.join(facts)}</ul>
<div class="actions"><a class="btn go" href="{esc(app_link)}">Plan it with friends</a>{tickets}<a class="btn alt" href="event.ics" type="text/calendar">Add to calendar</a></div>
{more}
<p class="more-link"><a href="/this-weekend/">See everything on in Brighton this weekend →</a></p>
</article>"""
    # People arriving from a shared link go straight into the app. Crawlers
    # don't run this, so they read the page above.
    script = f"""<script>(function(){{var q=new URLSearchParams(location.search);if(!q.has('share'))return;q.delete('share');q.set('event',{json.dumps(e['id'])});location.replace('/?'+q.toString());}})();</script>
<script>(function(){{function t(ev){{var a=ev.target.closest&&ev.target.closest('a[data-ticket-event]');if(!a)return;var g=null;try{{g=localStorage.getItem('bw_guest_id')}}catch(x){{}}try{{fetch({json.dumps(SUPABASE_URL + '/rest/v1/rpc/bw_track_ticket_click')},{{method:'POST',keepalive:true,headers:{{apikey:{json.dumps(SUPABASE_KEY)},Authorization:'Bearer '+{json.dumps(SUPABASE_KEY)},'Content-Type':'application/json'}},body:JSON.stringify({{p_event_id:a.getAttribute('data-ticket-event'),p_source:'event_page',p_guest_id:g||null}})}}).catch(function(){{}})}}catch(x){{}}}}document.addEventListener('click',t);document.addEventListener('auxclick',t);}})();</script>
"""
    title = f'{e["title"]} – {e["venue"]}, Brighton, {short_date(d)} | Brighton Weekend'
    return page(title=title, description=summary(e, d), url=event_url(e), og_title=e['title'], body=body,
                head_extra=event_json_ld(e, d) + breadcrumbs(trail), script=script)


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


WEEKEND_TRAIL = [('Brighton Weekend', f'{SITE}/'), ('This weekend', f'{SITE}/this-weekend/')]


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
{crumb_nav(WEEKEND_TRAIL)}
<h1>What’s on in Brighton this weekend</h1>
<p class="lede">{esc(span)} · gigs, comedy, club nights and theatre across Brighton &amp; Hove</p>
<div class="actions first"><a class="btn go" href="/">Plan your weekend with friends</a></div>
{hubs_nav('this-weekend')}
{''.join(days)}
</article>"""
    return page(title=f'What’s on in Brighton this weekend: gigs, comedy & club nights ({short_date(start)}–{short_date(end)}) | Brighton Weekend',
                description=desc, url=f'{SITE}/this-weekend/', og_title='What’s on in Brighton this weekend', body=body,
                head_extra=breadcrumbs(WEEKEND_TRAIL))


# ---- Guide pages: tonight, each kind of night out, and each venue ----
# Each answers a search people make ("comedy in Brighton", "what's on at
# Concorde 2"), lists real upcoming events and links to their pages.
GUIDES = [  # path, link text, categories shown (None: tonight)
    ('tonight', 'Tonight', None),
    ('gigs', 'Gigs', {'Music', 'Music/Club'}),
    ('comedy', 'Comedy', {'Comedy'}),
    ('club-nights', 'Club nights', {'Club', 'Music/Club'}),
    ('theatre', 'Theatre', {'Theatre', 'Dance'}),
]
GUIDE_COPY = {
    'gigs': ('Gigs in Brighton', 'Live music in Brighton & Hove: gigs over the next 30 days',
             'gigs at Concorde 2, CHALK, the Brighton Dome, the Prince Albert and more'),
    'comedy': ('Comedy in Brighton', 'Stand-up and comedy nights in Brighton & Hove over the next 30 days',
               'stand-up at Komedia, the Forge, the Brighton Dome and more'),
    'club-nights': ('Club nights in Brighton', 'Club nights and DJs in Brighton & Hove over the next 30 days',
                    'club nights at Patterns, Volks, DUST, CHALK and more'),
    'theatre': ('Theatre in Brighton', 'Theatre, cabaret and dance in Brighton & Hove over the next 30 days',
                'shows at the Theatre Royal, the Old Market, the Brighton Dome and more'),
}
GUIDE_DAYS = 30
GUIDE_NOUNS = {'gigs': ('gig', 'gigs'), 'comedy': ('comedy night', 'comedy nights'),
               'club-nights': ('club night', 'club nights'), 'theatre': ('show', 'shows')}
TONIGHT_FROM = '17:00'  # same as the app's Tonight chip


def hubs_nav(current: str = '') -> str:
    links = [('this-weekend', 'This weekend')] + [(path, label) for path, label, _ in GUIDES] + [('venues', 'Venues')]
    return '<ul class="hubs">' + ''.join(
        f'<li><a href="/{p}/"{" aria-current=\"page\"" if p == current else ""}>{esc(l)}</a></li>' for p, l in links) + '</ul>'


def by_day_sections(items: list[tuple[dict, date]], empty: str) -> str:
    if not items:
        return f'<p class="lede">{esc(empty)}</p>'
    out, day = [], None
    for e, d in items:
        if d != day:
            out.append(('</ul>' if day else '') + f'<h2>{esc(long_date(d))}</h2><ul class="list">')
            day = d
        out.append(listing([(e, d)])[len('<ul class="list">'):-len('</ul>')])
    return ''.join(out) + '</ul>'


def guide_page(path: str, label: str, items: list[tuple[dict, date]], today: date) -> str:
    url = f'{SITE}/{path}/'
    trail = [('Brighton Weekend', f'{SITE}/'), (label, url)]
    if path == 'tonight':
        h1, title = 'What’s on in Brighton tonight', f'What’s on in Brighton tonight ({short_date(today)}) | Brighton Weekend'
        lede = f'{long_date(today)} · gigs, comedy, club nights and theatre across Brighton & Hove'
        counts = count_phrase(items)
        desc = (f'{counts} in Brighton & Hove tonight, {long_date(today)}. ' if counts else
                f'What’s on in Brighton & Hove tonight, {long_date(today)}. ') + 'Updated every morning.'
        body_list = listing(items) if items else '<p class="lede">Nothing listed for tonight yet.</p>'
    else:
        h1, sub, examples = GUIDE_COPY[path]
        title = f'{h1}: what’s on in the next 30 days | Brighton Weekend'
        lede = sub
        n = len(items)
        one, many = GUIDE_NOUNS[path]
        desc = (f'{n} upcoming {one if n == 1 else many} in Brighton & Hove, '
                f'including {examples}. Dates, times and tickets, updated every morning.')
        body_list = by_day_sections(items, f'Nothing listed in the next {GUIDE_DAYS} days yet.')
    body = f"""<article class="card">
{crumb_nav(trail)}
<h1>{esc(h1)}</h1>
<p class="lede">{esc(lede)}</p>
<div class="actions first"><a class="btn go" href="/">Plan it with friends</a></div>
{hubs_nav(path)}
{body_list}
</article>"""
    return page(title=title, description=desc, url=url, og_title=h1, body=body, head_extra=breadcrumbs(trail))


def venue_page(venue: str, slug: str, items: list[tuple[dict, date]]) -> str:
    url = f'{SITE}/venues/{slug}/'
    trail = [('Brighton Weekend', f'{SITE}/'), ('Venues', f'{SITE}/venues/'), (venue, url)]
    counts = count_phrase(items)
    nxt = ', '.join(e['title'] for e, _ in items[:3])
    desc = (f'What’s on at {venue}, Brighton: {counts or str(len(items)) + " upcoming events"}'
            + (f', including {nxt}' if nxt else '') + '. Dates, times and tickets, updated every morning.')
    shown = items[:150]
    more = f'<p class="note">Showing the next {len(shown)} of {len(items)}. The app has the rest.</p>' if len(items) > len(shown) else ''
    body = f"""<article class="card">
{crumb_nav(trail)}
<h1>What’s on at {esc(venue)}</h1>
<p class="lede">Upcoming events at {esc(venue)}, Brighton</p>
<div class="actions first"><a class="btn go" href="/">Plan it with friends</a></div>
{listing(shown, show_day=True) if shown else '<p class="lede">Nothing listed here at the moment.</p>'}{more}
{hubs_nav()}
</article>"""
    return page(title=f'What’s on at {venue}, Brighton: upcoming events | Brighton Weekend', description=desc, url=url,
                og_title=f'What’s on at {venue}', body=body, head_extra=breadcrumbs(trail))


def venues_index(venues: list[tuple[str, str, int]]) -> str:
    url = f'{SITE}/venues/'
    trail = [('Brighton Weekend', f'{SITE}/'), ('Venues', url)]
    rows = ''.join(f'<li><span class="t">{n}</span><span><a href="/venues/{slug}/">{esc(v)}</a>'
                   f'<span class="v">{n} upcoming event{"" if n == 1 else "s"}</span></span></li>' for v, slug, n in venues)
    body = f"""<article class="card">
{crumb_nav(trail)}
<h1>Brighton venues: what’s on where</h1>
<p class="lede">Gig venues, comedy clubs, theatres and pubs across Brighton & Hove, with everything coming up at each</p>
<ul class="list">{rows}</ul>
{hubs_nav('venues')}
</article>"""
    return page(title='Brighton venues: gigs, comedy and club nights at each venue | Brighton Weekend',
                description=f'What’s on at {len(venues)} Brighton & Hove venues, from Concorde 2 and CHALK to Komedia and the Theatre Royal. Updated every morning.',
                url=url, og_title='Brighton venues: what’s on where', body=body, head_extra=breadcrumbs(trail))


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
        # newline='' keeps the CRLF line endings calendar files need.
        (p / 'event.ics').write_text(event_ics(e, d), encoding='utf-8', newline='')

    start, end = weekend_window(today)
    weekend = [x for x in items if start <= x[1] <= end]
    wk = ROOT / 'this-weekend'
    wk.mkdir(exist_ok=True)
    (wk / 'index.html').write_text(weekend_page(weekend, start, end), encoding='utf-8')

    urls = [(f'{SITE}/', True), (f'{SITE}/this-weekend/', True)]

    # Guides: tonight, then the next 30 days of each kind of night out.
    horizon = today + timedelta(days=GUIDE_DAYS - 1)
    for path, label, cats in GUIDES:
        if cats is None:
            chosen = [x for x in items if x[1] == today and (x[0].get('time') or '99:99') >= TONIGHT_FROM]
        else:
            chosen = [x for x in items if x[1] <= horizon and x[0].get('category') in cats]
        folder = ROOT / path
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir()
        (folder / 'index.html').write_text(guide_page(path, label, chosen, today), encoding='utf-8')
        urls.append((f'{SITE}/{path}/', True))

    # Venues: one page each, and an A to Z of them.
    by_venue: dict[str, list] = {}
    for x in items:
        if venue_slug(x[0]['venue']):
            by_venue.setdefault(x[0]['venue'], []).append(x)
    vdir = ROOT / 'venues'
    if vdir.exists():
        shutil.rmtree(vdir)
    vdir.mkdir()
    venue_rows = []
    for venue in sorted(by_venue, key=lambda v: re.sub(r'^the\s+', '', v.lower())):
        slug = venue_slug(venue)
        (vdir / slug).mkdir()
        (vdir / slug / 'index.html').write_text(venue_page(venue, slug, by_venue[venue]), encoding='utf-8')
        venue_rows.append((venue, slug, len(by_venue[venue])))
        urls.append((f'{SITE}/venues/{slug}/', True))
    (vdir / 'index.html').write_text(venues_index(venue_rows), encoding='utf-8')
    urls.append((f'{SITE}/venues/', True))

    urls.append((f'{SITE}/about.html', False))
    urls += [(event_url(e), False) for e, _ in items]
    (ROOT / 'sitemap.xml').write_text(sitemap(urls, today), encoding='utf-8')
    print(f'Built {len(items)} event pages, this-weekend ({len(weekend)} events, {start}–{end}), '
          f'{len(GUIDES)} guides, {len(venue_rows)} venue pages and sitemap.xml')


if __name__ == '__main__':
    main()
