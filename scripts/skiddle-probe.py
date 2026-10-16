#!/usr/bin/env python3
"""What does the Skiddle API list in Brighton & Hove?

A one-off check, before anything from the API goes into the app: for each
Skiddle event code (Bar/Pub, Comedy, The Arts...) it fetches the next six
months of events within five miles of central Brighton, keeps those with a
Brighton & Hove postcode, and writes skiddle-report.json: how many there are,
at which venues (and whether the app knows each venue), and sample listings.

Needs a free key from https://www.skiddle.com/api/join.php in the
SKIDDLE_API_KEY environment variable (a repository secret in GitHub Actions).
Without one it says so and writes nothing. The key is never printed.

Skiddle's API documentation: https://github.com/Skiddle/web-api/wiki
"""
import json, os, re, sys, time
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'skiddle-report.json'
API = 'https://www.skiddle.com/api/v1/events/search/'
CENTRE = (50.8225, -0.1372)  # central Brighton
RADIUS_MILES = 5
MONTHS_AHEAD_DAYS = 183
PAGE = 100
MAX_PAGES = 10
CODES = {  # Skiddle's own labels, in the order they're reported
    'BARPUB': 'Bar/Pub event', 'COMEDY': 'Comedy', 'ARTS': 'The Arts', 'THEATRE': 'Theatre/Dance',
    'EXHIB': 'Exhibitions and Attractions', 'DATE': 'Dating event', 'LGB': 'Gay/Lesbian event',
    'KIDS': 'Kids/Family event', 'LIVE': 'Live music', 'CLUB': 'Clubbing/Dance music',
    'FEST': 'Festivals', 'SPORT': 'Sporting event',
}
MUSIC_CODES = {'LIVE', 'CLUB'}
BRIGHTON_POSTCODE = re.compile(r'^\s*BN(?:1|2|3|41|42)\b', re.I)
BRIGHTON_TOWNS = {'brighton', 'hove', 'brighton and hove', 'brighton & hove', 'portslade', 'rottingdean', 'saltdean'}


def norm(name):
    s = re.sub(r'[^a-z0-9]+', ' ', (name or '').lower()).strip()
    return re.sub(r'^the ', '', s)


def known_venues():
    names = {norm(s.get('venue')) for s in json.loads((ROOT / 'event-sources.json').read_text())}
    m = re.search(r'const VENUES=\[(.*?)\];', (ROOT / 'index.html').read_text(encoding='utf-8'))
    if m:
        names |= {norm(v) for v in re.findall(r'"([^"]+)"', m.group(1))}
    names.discard('other')
    return names


def fetch(params, key):
    url = API + '?' + urlencode({**params, 'api_key': key})
    req = Request(url, headers={'User-Agent': 'BrightonWeekend/1.0 (+https://github.com/brightonspindoctor/brighton-weekend)',
                                'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8', 'replace')), None
    except HTTPError as exc:
        body = exc.read().decode('utf-8', 'replace')[:300]
        return None, f'HTTP {exc.code}: {body}'.replace(key, '***')
    except (URLError, TimeoutError, ValueError) as exc:
        return None, str(exc).replace(key, '***')


def time_of(ev):
    start = str(ev.get('startdate') or '')
    m = re.search(r'T(\d{2}:\d{2})', start)
    if m and m.group(1) != '00:00':
        return m.group(1)
    doors = ((ev.get('openingtimes') or {}).get('doorsopen') or '').strip()
    return doors[:5] if re.fullmatch(r'\d{2}:\d{2}(:\d{2})?', doors) else ''


def in_brighton_hove(venue):
    pc = venue.get('postcode') or venue.get('postcode_lookup') or ''
    if pc:
        return bool(BRIGHTON_POSTCODE.match(pc))
    return norm(venue.get('town')) in {norm(t) for t in BRIGHTON_TOWNS}


def main():
    key = (os.environ.get('SKIDDLE_API_KEY') or '').strip()
    if not key:
        print('No SKIDDLE_API_KEY yet: add it as a repository secret, then run this again. Nothing written.')
        return 0
    today = date.today()
    base = {'latitude': CENTRE[0], 'longitude': CENTRE[1], 'radius': RADIUS_MILES,
            'minDate': today.isoformat(), 'maxDate': (today + timedelta(days=MONTHS_AHEAD_DAYS)).isoformat(),
            'description': 1, 'limit': PAGE}
    known = known_venues()
    report = {'generated': today.isoformat(), 'area': f'{RADIUS_MILES} miles of central Brighton, Brighton & Hove postcodes only',
              'dates': f"{base['minDate']} to {base['maxDate']}", 'codes': {}, 'errors': []}
    seen_ids = set()
    unknown_non_music = {}
    for code, label in CODES.items():
        rows, reported, err = [], None, None
        for page in range(MAX_PAGES):
            data, err = fetch({**base, 'eventcode': code, 'offset': page * PAGE}, key)
            if err:
                report['errors'].append(f'{code}: {err}')
                break
            if str(data.get('error', '0')) not in ('0', 'False', 'false', ''):
                err = f"{code}: API error {data.get('error')}: {data.get('errormessage') or ''}"
                report['errors'].append(err)
                break
            batch = data.get('results') or []
            reported = int(data.get('totalcount') or 0)
            rows.extend(batch)
            if len(batch) < PAGE or len(rows) >= reported:
                break
            time.sleep(0.5)
        kept, venues, cancelled = [], {}, 0
        for ev in rows:
            v = ev.get('venue') or {}
            if not in_brighton_hove(v):
                continue
            if str(ev.get('cancelled') or '0') not in ('0', ''):
                cancelled += 1
                continue
            name = (v.get('name') or '').strip()
            is_known = norm(name) in known
            entry = venues.setdefault(name, {'venue': name, 'postcode': v.get('postcode') or '', 'events': 0, 'in_app': is_known})
            entry['events'] += 1
            if code not in MUSIC_CODES and not is_known:
                unknown_non_music[name] = unknown_non_music.get(name, 0) + 1
            seen_ids.add(ev.get('id'))
            kept.append({'date': ev.get('date') or '', 'time': time_of(ev), 'title': (ev.get('eventname') or '').strip(),
                         'venue': name, 'price': (ev.get('entryprice') or '').strip(), 'link': ev.get('link') or '',
                         'genres': [g.get('name') for g in (ev.get('genres') or []) if isinstance(g, dict) and g.get('name')]})
        kept.sort(key=lambda e: (e['date'], e['time'], e['title']))
        report['codes'][code] = {
            'label': label, 'reported_nearby': reported, 'fetched': len(rows), 'in_brighton_hove': len(kept),
            'cancelled_left_out': cancelled, 'venues': sorted(venues.values(), key=lambda x: (-x['events'], x['venue'])),
            'samples': kept[: (15 if code in MUSIC_CODES else 80)],
        }
        print(f"{code:8} {label:28} nearby {reported if reported is not None else '?':>5}  Brighton & Hove {len(kept):>4}  venues {len(venues):>3}" + (f'  ERROR {err}' if err else ''))
        time.sleep(0.5)
    report['unique_events'] = len(seen_ids)
    report['venues_not_in_app'] = [{'venue': k, 'events': n} for k, n in sorted(unknown_non_music.items(), key=lambda x: (-x[1], x[0]))]
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(f'Wrote {OUT.name}: {len(seen_ids)} events in all; {len(unknown_non_music)} non-music venues the app does not list yet.')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        lines = ['## Skiddle API: Brighton & Hove, next six months', '', '| Code | Skiddle category | Events | Venues | Not in the app |', '|---|---|---|---|---|']
        for code, r in report['codes'].items():
            lines.append(f"| {code} | {r['label']} | {r['in_brighton_hove']} | {len(r['venues'])} | {sum(1 for v in r['venues'] if not v['in_app'])} |")
        if report['errors']:
            lines += ['', '**Errors:** ' + '; '.join(report['errors'])]
        with open(summary, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    return 1 if report['errors'] and not seen_ids else 0


if __name__ == '__main__':
    sys.exit(main())
