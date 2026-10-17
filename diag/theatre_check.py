"""One-off: do Theatre Royal (ATG), The Old Market and Brighton Dome say each
show's genre on their own pages? Results go in diag/theatre/."""
import asyncio, json, re
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path('diag/theatre'); OUT.mkdir(parents=True, exist_ok=True)
PAGES = {
    'atg_whatson': 'https://www.atgtickets.com/venues/theatre-royal-brighton/whats-on/',
    'atg_musicals': 'https://www.atgtickets.com/venues/theatre-royal-brighton/whats-on/uk/musical/',
    'atg_plays': 'https://www.atgtickets.com/venues/theatre-royal-brighton/whats-on/uk/play/',
    'atg_talk': 'https://www.atgtickets.com/venues/theatre-royal-brighton/whats-on/uk/talk/',
    'atg_show_gareth': 'https://www.atgtickets.com/shows/gareth-malone/theatre-royal-brighton/',
    'atg_show_six': 'https://www.atgtickets.com/shows/six/theatre-royal-brighton/',
    'oldmarket_shows': 'https://www.theoldmarket.com/shows',
    'dome_whatson': 'https://brightondome.org/whats-on/',
}
KNOWN = ['Gareth Malone', 'Six', 'The Mousetrap', 'Swan Lake', 'Yacht Rock', 'Popera', 'Eddi Reader', 'Congregational', 'The Gift', 'Clara', 'Signalman']


async def main():
    report = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36')
        for name, url in PAGES.items():
            page = await ctx.new_page()
            info = {'url': url}
            try:
                resp = await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                try:
                    await page.wait_for_load_state('networkidle', timeout=15000)
                except Exception:
                    pass
                await page.wait_for_timeout(2000)
                html = await page.content()
                info.update({'status': resp.status if resp else None, 'final': page.url, 'length': len(html)})
                (OUT / f'{name}.html').write_text(html[:4_000_000])
                types = re.findall(r'"@type"\s*:\s*"([A-Za-z]+Event)"', html)
                info['jsonld_event_types'] = {t: types.count(t) for t in set(types)}
                for key in ('genre', 'category', 'categories', 'eventType', 'showType', 'tags'):
                    vals = re.findall(r'"' + key + r'"\s*:\s*("[^"]{1,60}"|\[[^\]]{0,200}\])', html)
                    if vals:
                        info[f'json_{key}'] = sorted(set(vals))[:40]
                text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))
                info['near_titles'] = {k: [text[max(0, m.start() - 160):m.end() + 160] for m in list(re.finditer(re.escape(k), text))[:2]] for k in KNOWN if k in text}
            except Exception as exc:
                info['error'] = str(exc)[:300]
            report[name] = info
            await page.close()
        await b.close()
    (OUT / 'report.json').write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ('near_titles',)} for k, v in report.items()}, indent=1)[:6000])

asyncio.run(main())
