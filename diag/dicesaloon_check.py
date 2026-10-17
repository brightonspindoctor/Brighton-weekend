"""One-off: can Dice Saloon's events (dicesaloon.co.uk, a Shopify shop) be read,
and what does its robots.txt allow? Results go in diag/dicesaloon/."""
import json, re, time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

OUT = Path('diag/dicesaloon'); OUT.mkdir(parents=True, exist_ok=True)
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'


def get(url, accept='*/*'):
    req = Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'en-GB,en;q=0.9'})
    try:
        with urlopen(req, timeout=40) as r:
            return r.status, dict(r.headers), r.read().decode('utf-8', 'replace'), r.geturl()
    except HTTPError as e:
        return e.code, dict(e.headers or {}), e.read().decode('utf-8', 'replace')[:20000], url
    except Exception as e:
        return None, {}, f'ERROR {e}', url


report = {}
for name, url, ext in [('robots', 'https://dicesaloon.co.uk/robots.txt', 'txt'),
                       ('collection', 'https://dicesaloon.co.uk/collections/events', 'html'),
                       ('products', 'https://dicesaloon.co.uk/collections/events/products.json?limit=250', 'json')]:
    st, h, body, final = get(url)
    (OUT / f'{name}.{ext}').write_text(body[:4_000_000])
    info = {'status': st, 'final_url': final, 'content_type': h.get('Content-Type') or h.get('content-type'), 'length': len(body)}
    if name == 'collection':
        info['jsonld_blocks'] = len(re.findall(r'application/ld\+json', body))
        info['product_links'] = len(set(re.findall(r'/products/[a-z0-9-]+', body)))
    if name == 'products':
        try:
            prods = json.loads(body).get('products', [])
            info['products'] = len(prods)
            info['sample'] = [{'title': p.get('title'), 'handle': p.get('handle'), 'published_at': p.get('published_at'),
                               'tags': p.get('tags'), 'variants': [{'title': v.get('title'), 'available': v.get('available'), 'price': v.get('price')} for v in p.get('variants', [])[:6]],
                               'body': re.sub(r'<[^>]+>', ' ', p.get('body_html') or '')[:400]} for p in prods[:60]]
        except Exception as exc:
            info['parse_error'] = str(exc)
    report[name] = info
    time.sleep(2)
(OUT / 'report.json').write_text(json.dumps(report, indent=1, ensure_ascii=False))
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'sample'} for k, v in report.items()}, indent=1))
