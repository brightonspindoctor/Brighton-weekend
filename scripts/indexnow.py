#!/usr/bin/env python3
"""Tell Bing (and the other IndexNow search engines) which pages changed.

Google finds new pages through sitemap.xml and Search Console. Bing, Yandex,
Seznam and Naver also accept IndexNow: a single request listing new or changed
addresses, so new event pages show up in Bing within hours rather than weeks.

The key is public by design: IndexNow checks it by fetching
https://brightonweekend.co.uk/<key>.txt, which is in the repo root.

What is sent: every address in sitemap.xml that wasn't in the previous
commit's sitemap.xml (new event pages, new venue pages), plus the guide pages
that change every day. Run after the daily refresh has been pushed:

  python scripts/indexnow.py [--dry-run]

It never fails the workflow: problems are printed and it exits 0.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = 'brightonweekend.co.uk'
SITE = f'https://{HOST}'
ENDPOINT = 'https://api.indexnow.org/indexnow'
# Pages whose content changes with every refresh.
DAILY = ['/', '/tonight/', '/this-weekend/', '/gigs/', '/comedy/', '/club-nights/', '/theatre/', '/venues/']
LOC = re.compile(r'<loc>([^<]+)</loc>')


def find_key() -> str:
    keys = [p.stem for p in ROOT.glob('*.txt') if re.fullmatch(r'[0-9a-f]{32}', p.stem)
            and p.read_text(encoding='utf-8').strip() == p.stem]
    return keys[0] if len(keys) == 1 else ''


def urls_in(xml: str) -> set[str]:
    return {u.strip() for u in LOC.findall(xml) if u.startswith(SITE + '/')}


def previous_sitemap() -> str:
    try:
        return subprocess.run(['git', 'show', 'HEAD~1:sitemap.xml'], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='Print what would be sent')
    args = ap.parse_args()
    key = find_key()
    if not key:
        print('IndexNow: no key file (<32 hex characters>.txt) in the repo root; skipping.')
        return 0
    now = urls_in((ROOT / 'sitemap.xml').read_text(encoding='utf-8'))
    new = sorted(now - urls_in(previous_sitemap()))
    urls = [SITE + p for p in DAILY if SITE + p in now or p == '/'] + [u for u in new if u.removeprefix(SITE) not in DAILY]
    urls = list(dict.fromkeys(urls))[:10000]  # IndexNow takes up to 10,000 per request
    print(f'IndexNow: {len(urls)} addresses ({len(new)} new since the last sitemap).')
    if args.dry_run:
        print('\n'.join(urls[:40]))
        return 0
    body = json.dumps({'host': HOST, 'key': key, 'keyLocation': f'{SITE}/{key}.txt', 'urlList': urls}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method='POST',
                                 headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f'IndexNow: accepted ({r.status}).')
    except urllib.error.HTTPError as e:
        # 202 = accepted, key not yet checked; 403 = key file not found yet (the
        # site may still be deploying); 422 = an address isn't on this host.
        print(f'IndexNow: {e.code} {e.reason}. {e.read()[:300].decode(errors="replace")}')
    except OSError as e:
        print(f'IndexNow: could not reach the service ({e}).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
