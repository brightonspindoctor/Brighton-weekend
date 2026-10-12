#!/usr/bin/env python3
"""Get each event's ticket link as close to buying as possible, and mark
sold-out shows. Runs after prepare-events.py, before the event pages are built.

For each upcoming event it follows the ticket link, at most three steps:

1. A homepage or listings page (Brighton Centre's homepage, an ents24 venue
   page): find this event's card on it (its title, and its date when the card
   shows one) and follow the card's link.
2. An event page on a venue's site: follow its one clear "Book tickets" /
   "Get tickets" / "Buy from ..." button to where tickets are sold (AXS, DICE,
   Ticketsolve, Eventbrite...). Menus, footers and "you might also like" blocks
   are ignored.
3. A ticketing page: stop.

Sold out is only ever set when a page says so, never guessed:
- the seller's structured data (schema.org) gives every ticket type as sold
  out (on DICE, every ticket type on the waiting list); or
- with no such data, the event's page or its card on the venue's listings
  page shows a "Sold out" / "Fully booked" label of its own, and the page has
  no booking button that is still live. Sentences ("they sold out their last
  tour") and one sold-out ticket type among others don't count.
Seller data saying tickets are on sale always wins over a label.

Results are kept in ticket-cache.json, so events more than three weeks away
are rechecked every few days and nearer ones daily, within a time limit.
Pages that can't be read (some sites block automated visits) leave the event
as it was.
"""
import asyncio, importlib.util, json, re, sys, time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))  # scrape-events.py imports event_matching
_spec = importlib.util.spec_from_file_location('scrape_events', ROOT / 'scripts' / 'scrape-events.py')
se = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(se)

EVENTS = ROOT / 'events.json'
CACHE = ROOT / 'ticket-cache.json'
SOURCES = json.loads((ROOT / 'event-sources.json').read_text())
TODAY = se.NOW.date()
NEAR_DAYS = 21          # events this close are rechecked every run
RECHECK_DAYS = 4        # others when their result is this old
TIME_BUDGET = 20 * 60   # seconds of fetching per run
MAX_HOPS = 3

TICKET_HOSTS = se.TICKET_HOSTS + ('axs.com', 'shotgun.live', 'ticketsolve', 'link.dice.fm', 'tickets.', 'myshopify.com',
                                  'songkick', 'eventim-light', 'tixr', 'ticketing.')
INFO_PATHS = re.compile(r'/(?:booking-tickets|booking-info|faqs?|help|contact|about|access|visiting(?:-us)?|terms|privacy|login|account|basket|cart|gift[\w-]*|membership|venue|venues|location|tour|artist|artists|promoters?|organi[sz]ers?)(?:/|$)|^/f/\d+/?$', re.I)
# Sites that list events but don't sell tickets: never the place to send people.
NOT_SELLERS = ('datathistle', 'visitbrighton', 'list.co.uk', 'bandsintown', 'allevents', 'whatsonwhen', 'queue-it.net')
CHROME = re.compile(r'(^|[-_ ])(nav|navbar|menu|site-header|masthead|footer|breadcrumbs?|cookie\w*|newsletter|related|recommend\w*|similar|more-events|you-may\w*|upsell|sidebar|mega)([-_ ]|$)', re.I)

# A label that says the show itself is sold out: "Sold out", "SOLD OUT - join
# the waiting list", "Fully booked", "This event is sold out".
SOLD_LABEL = re.compile(r"""^\W*(?:sorry[,!.]?\s*)?(?:(?:this|the)\s+(?:event|show|performance|gig)\s+(?:is|has)\s+(?:now\s+)?)?
    (?:sold[\s-]*out|fully[\s-]*booked)
    (?:\s*[-–:|!.]?\s*(?:join\s+(?:the\s+|our\s+)?wait(?:ing)?[\s-]*list|wait(?:ing)?[\s-]*list(?:\s+only)?|online|returns?\s+only|resale\s+only
        |for\s+resale\s+tickets.*|limited\s+tickets?\s+on\s+the\s+door|tickets?\s+(?:may\s+be\s+)?available\s+on\s+the\s+door))?\W*$""", re.I | re.X)
# A heading that ends with the marker: "Girl In The Year Above *SOLD OUT*", "Band (Sold Out)", "Band - SOLD OUT".
SOLD_IN_HEADING = re.compile(r'(?:\*+\s*sold[\s-]*out\s*\*+|\(\s*sold[\s-]*out\s*\)|[-–|:]\s*sold[\s-]*out!?)\s*$', re.I)
# Buttons and links that take you to buy (or that are this page's booking control).
CTA = re.compile(r"""^\W*(?:
     (?:book|buy|get|find\s+and\s+book|view|select)\s+(?:your\s+|my\s+)?(?:tickets?|seats?)\b.*
    |book(?:ing)?\s+(?:now|here|online)\b.*|buy\s+now|book\s+at\s+\S.*
    |buy\s+from\s+\S.*|direct\s+ticket\s+link|tickets?(?:\s*(?:[£€$]\s?\d.*|from\b.*|here|now|available|on\s+sale.*|&\s+info))?
    |get\s+tickets?\s+now|reserve\s+(?:a\s+)?(?:tickets?|seats?|spot)
)\W*$""", re.I | re.X)
UNAVAILABLE_CTA = re.compile(r'sold|wait|notify|remind|off\s*sale|unavailable|closed', re.I)
SOLD_OUT_LD = {'soldout', 'outofstock', 'discontinued'}
AVAILABLE_LD = {'instock', 'limitedavailability', 'preorder', 'presale', 'onlineonly', 'instoreonly'}


def norm_avail(v):
    return re.sub(r'[^a-z]', '', str(v).replace('\\u002F', '/').rsplit('/', 1)[-1].lower())


def host_of(u):
    return urlparse(u).netloc.lower()


def is_ticket_site(u):
    h = host_of(u)
    return any(t in h for t in TICKET_HOSTS)


def unwrap(u):
    """Brighton Dome's booking button goes through a queue page that carries the real address."""
    p = urlparse(u)
    if 'queue-it.net' in p.netloc:
        t = parse_qs(p.query).get('t')
        if t and unquote(t[0]).startswith('http'):
            return unquote(t[0])
    return u


def generic_url(u):
    """A homepage, listings page or general info page: not one event's own page."""
    p = urlparse(u); segs = [x for x in p.path.split('/') if x]
    if is_ticket_site(u) and len(segs) >= 3 and segs[-1].lower() in ('calendar', 'tickets', 'dates', 'performances'):
        return False  # a show's own booking calendar (ATG: /shows/<show>/<venue>/calendar/)
    if se.is_listing_or_home(u, ''):
        return True
    return bool(INFO_PATHS.search(p.path)) and not re.search(r'\d{4,}', p.path)


def soup_of(html):
    soup = BeautifulSoup(html, 'html.parser')
    return soup


def strip_chrome(soup):
    """Remove menus, the site header and footer and 'more events' blocks (in place)."""
    for t in soup(['script', 'style', 'noscript', 'svg', 'template', 'iframe']):
        t.decompose()
    for t in soup.find_all('nav'):
        t.decompose()
    for t in soup.find_all(['header', 'footer', 'aside']):
        if t.decomposed:
            continue
        # An event's own header (inside its article/main) holds its title and labels: keep it.
        if t.name != 'aside' and t.find_parent(['article', 'main']) is not None and len(t.find_all('a', href=True)) < 8:
            continue
        t.decompose()
    for t in soup.find_all(True):
        if t.decomposed or t.name in ('html', 'body', 'main', 'article'):
            continue
        label = ' '.join(t.get('class', []) or []) + ' ' + str(t.get('id', '') or '') + ' ' + str(t.get('role', '') or '')
        if CHROME.search(label) or str(t.get('role', '')).lower() in ('navigation', 'banner', 'contentinfo'):
            t.decompose()
    return soup


def ld_events(soup):
    out = []
    for tag in soup.find_all('script', attrs={'type': re.compile(r'ld\+json', re.I)}):
        try:
            data = json.loads(tag.string or tag.get_text())
        except Exception:
            continue
        stack = [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, list):
                stack.extend(obj); continue
            if not isinstance(obj, dict):
                continue
            for key in ('@graph', 'event', 'events', 'subEvent', 'itemListElement', 'item', 'mainEntity'):
                if isinstance(obj.get(key), (list, dict)):
                    stack.append(obj[key])
            typ = obj.get('@type', ''); types = typ if isinstance(typ, list) else [typ]
            if any(str(t).lower().endswith('event') for t in types):
                out.append(obj)
    return out


def ld_verdict(soup, event, url):
    """True (sold out), False (on sale) or None (the page doesn't say) from schema.org offers."""
    evs = ld_events(soup)
    if not evs:
        return None
    dated = [o for o in evs if str(o.get('startDate', ''))[:10] == event['date']]
    if dated:
        evs = dated
    elif len(evs) > 1 or any(re.match(r'\d{4}-\d{2}-\d{2}', str(o.get('startDate', ''))) for o in evs):
        return None  # other dates only: not this performance
    titled = [o for o in evs if se.same_show(str(o.get('name', '')), event['title'], event.get('venue', ''))]
    if titled:
        evs = titled
    elif len(evs) > 1:
        return None
    avails = []
    for o in evs:
        offers = o.get('offers')
        offers = offers if isinstance(offers, list) else [offers]
        for of in offers:
            if isinstance(of, dict) and of.get('availability'):
                avails.append(norm_avail(of['availability']))
            if isinstance(of, dict) and isinstance(of.get('offers'), list):  # AggregateOffer
                avails += [norm_avail(x.get('availability')) for x in of['offers'] if isinstance(x, dict) and x.get('availability')]
    avails = [a for a in avails if a]
    if not avails:
        return None
    if any(a in AVAILABLE_LD for a in avails):
        return False
    gone = SOLD_OUT_LD | ({'backorder'} if 'dice.fm' in host_of(url) else set())
    if all(a in gone for a in avails):
        return True
    return None


def own_text(el):
    return se.clean(el.get_text(' ', strip=True))


def sold_labels(root):
    """Elements in root that are a sold-out label of their own."""
    found = []
    for el in root.find_all(True):
        t = own_text(el)
        if not t or len(t) > 60:
            continue
        if SOLD_LABEL.match(t):
            # Report the outermost element of a label only once.
            if not any(p in found for p in el.parents):
                found.append(el)
    for h in root.find_all(['h1', 'h2', 'h3']):
        if SOLD_IN_HEADING.search(own_text(h)) and h not in found:
            found.append(h)
    return found


def live_ctas(root, page_url):
    """Booking links/buttons that still work and are specific to an event (not a venue-wide page)."""
    out = []
    for el in root.find_all(['a', 'button']):
        t = own_text(el) or se.clean(el.get('aria-label', ''))
        if not t or len(t) > 60 or not CTA.match(t) or UNAVAILABLE_CTA.search(t):
            continue
        if el.has_attr('disabled') or 'disabled' in ' '.join(el.get('class', []) or []).lower():
            continue
        if el.name == 'a':
            href = (el.get('href') or '').strip()
            if not href or href.startswith(('mailto:', 'tel:', 'javascript:')):
                continue
            u = unwrap(urljoin(page_url, href).split('#')[0])
            if href.startswith('#'):
                out.append((el, page_url, t)); continue
            p = urlparse(u)
            if p.scheme not in ('http', 'https') or any(h in p.netloc.lower() for h in se.SKIP_HOSTS) or generic_url(u):
                continue
            out.append((el, u, t))
        else:
            out.append((el, page_url, t))
    return out


def booking_link(root, page_url, event):
    """The one link on an event's page that goes on to where tickets are sold, or None."""
    here = page_url.split('#')[0].rstrip('/')
    cands = []
    for el, u, t in live_ctas(root, page_url):
        if el.name != 'a' or u.rstrip('/') == here:
            continue
        if host_of(u) == host_of(page_url) and not is_ticket_site(u):
            continue  # another page on the same site ("Booking info"), not the seller
        if any(n in host_of(u) for n in NOT_SELLERS) or 'queue-it.net' in host_of(el.get('href') or ''):
            continue  # a listings site, or a queue in front of the venue's own booking (the page is the place to book)
        cands.append(u)
    seen = []
    for u in cands:
        if u not in seen:
            seen.append(u)
    if not seen:
        return None
    # Several sellers for one show (Hope & Ruin: Fatsoma, DICE, Gigantic): the venue lists its main one first.
    return seen[0]


def cards_for(root, event, other_keys):
    """Smallest blocks on a listing page that are this event's card."""
    key = se.title_key(event['title'])
    if len(key) < 3:
        return []
    cards = []
    for el in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'span', 'div', 'p', 'strong']):
        t = own_text(el)
        if not t or len(t) > 200:
            continue
        tk = se.title_key(t)
        if not (tk == key or tk.startswith(key + ' ') or (len(key) > 12 and key in tk) or se.same_show(t, event['title'], event.get('venue', ''))):
            continue
        if any(el in c.descendants for c in cards):
            continue
        card = el
        for _ in range(6):
            parent = card.parent
            if parent is None or parent.name in ('body', 'html', '[document]'):
                break
            ptext = se.title_key(parent.get_text(' ', strip=True))
            if any(k != key and len(k) > 6 and k in ptext and k not in key for k in other_keys):
                break  # the parent holds another event too
            card = parent
            if card.find('a', href=True) and len(ptext) > len(key) + 15:
                break
        # Widen to the whole card (ATG puts its "Sold out" badge above the card's
        # content) while the wider block still holds only this show's headings.
        for _ in range(3):
            parent = card.parent
            if parent is None or parent.name in ('body', 'html', '[document]'):
                break
            heads = {se.title_key(own_text(h)) for h in parent.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])} - {''}
            if any(not se.same_show(h, key) for h in heads):
                break
            if len({a['href'] for a in parent.find_all('a', href=True)}) > 4:
                break
            card = parent
        cards.append(card)
    good = []
    for card in cards:
        text = own_text(card)
        dates = set()
        for m in se.DATE_RE.finditer(text):
            d = se.parse_dt(m.group(1))
            if d:
                dates.add(d.date().isoformat())
        if dates and event['date'] not in dates:
            continue
        good.append(card)
    return good


def card_link(card, page_url, event):
    best = None; score = -1
    links = card.find_all('a', href=True)
    if card.name == 'a' and card.get('href'):
        links = [card] + links
    # One destination in the whole card: its "View tickets" button is this event's.
    single = len({urljoin(page_url, a['href'].strip()).split('#')[0] for a in links
                  if not a['href'].strip().startswith(('#', 'mailto:', 'tel:', 'javascript:'))}) == 1
    for a in links:
        href = a['href'].strip()
        if not href or href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
            continue
        u = unwrap(urljoin(page_url, href).split('#')[0])
        p = urlparse(u)
        if p.scheme not in ('http', 'https') or any(h in p.netloc.lower() for h in se.SKIP_HOSTS) or generic_url(u):
            continue
        if u.rstrip('/') == page_url.split('#')[0].rstrip('/'):
            continue
        t = own_text(a)
        if any(n in p.netloc.lower() for n in NOT_SELLERS):
            continue
        words = {w for w in se.title_key(event['title']).split() if len(w) >= 4}
        where = se.title_key(t + ' ' + unquote(p.path).replace('-', ' ').replace('_', ' '))
        if words and not any(w in where.split() for w in words) and not (CTA.match(t or '') and single):
            continue  # a link to some other event in the same block
        s = 1
        if event['date'] in u or event['date'].replace('-', '') in u:
            s += 3  # this date's own booking link (Gigantic: /2026-12-12-19-00)
        if is_ticket_site(u):
            s += 3
        if CTA.match(t or ''):
            s += 3
        if t and se.same_show(t, event['title'], event.get('venue', '')):
            s += 2
        if s > score:
            best, score = u, s
    return best


class Fetcher:
    def __init__(self, browser):
        self.browser = browser; self.mem = {}; self.sem = asyncio.Semaphore(8); self.hosts = {}
        self.started = time.monotonic(); self.count = 0; self.fails = 0; self.pending = {}

    def out_of_time(self):
        return time.monotonic() - self.started > TIME_BUDGET

    async def get(self, url):
        if url in self.mem:
            return self.mem[url]
        if url in self.pending:
            return await self.pending[url]
        fut = asyncio.get_running_loop().create_future(); self.pending[url] = fut
        result = ('', url)
        try:
            hs = self.hosts.setdefault(host_of(url), asyncio.Semaphore(2))
            async with hs:              # at most 2 at a time per site (polite), then
                async with self.sem:    # at most 8 overall
                    if not self.out_of_time():
                        result = await asyncio.wait_for(self._fetch(url), timeout=75)
        except Exception:
            self.fails += 1
        finally:
            self.mem[url] = result; fut.set_result(result); del self.pending[url]
        return result

    async def _fetch(self, url):
        html, final, err = await se.get_html(self.browser, url)
        if err or len(html) < 5000 or 'Just a moment' in html[:3000]:
            try:
                h2, f2 = await asyncio.wait_for(asyncio.to_thread(se.fetch_plain, url), timeout=40)
                if len(h2) > len(html):
                    html, final, err = h2, f2, None
            except Exception:
                pass
        self.count += 1
        if not html or len(html) < 3000:
            self.fails += 1; html = ''
        return html, final


async def check_event(fx, event, start_url, generic, other_keys, listing_hints):
    """(closest url, sold_out or None) for one event."""
    url = start_url; sold = None; label_sold = False; steps = []
    # 1. A listings page or homepage: find the event's card.
    if generic:
        pages = [url] + [u for u in listing_hints if u != url]
        if not urlparse(url).path.strip('/'):
            pages += [urljoin(url, '/whats-on/'), urljoin(url, '/events/')]  # a homepage shows only some events
        for lu in pages:
            html, final = await fx.get(lu)
            if not html:
                continue
            root = strip_chrome(soup_of(html))
            cards = cards_for(root, event, other_keys)
            if len(cards) != 1:
                continue
            if sold_labels(cards[0]):
                label_sold = True
            nxt = card_link(cards[0], final, event)
            if nxt:
                url = nxt; steps.append(nxt); break
        else:
            return (None if url == start_url else url), (True if label_sold else None)
    # 2–3. Follow the booking button to the seller.
    for _ in range(MAX_HOPS):
        html, final = await fx.get(url)
        if not html:
            break
        raw = soup_of(html)
        verdict = ld_verdict(raw, event, final)
        root = strip_chrome(raw)
        if verdict is not None:
            sold = verdict
        else:
            labels = sold_labels(root)
            if any(l.name in ('h1', 'h2', 'h3') and SOLD_IN_HEADING.search(own_text(l)) for l in labels):
                label_sold = True  # the venue put it in the show's name: "Band *SOLD OUT*"
            elif labels and not [c for c in live_ctas(root, final) if c[1] != final or c[0].name == 'button']:
                label_sold = True
        if is_ticket_site(final) and verdict is not None:
            break
        nxt = booking_link(root, final, event)
        if not nxt or nxt in steps or nxt == start_url:
            break
        url = nxt; steps.append(nxt)
    if sold is None and not label_sold and not generic:
        # The seller's page didn't say: the venue's own listing may label the show (ATG, Quarters).
        for lu in listing_hints:
            html, final = await fx.get(lu)
            if not html:
                continue
            cards = cards_for(strip_chrome(soup_of(html)), event, other_keys)
            if len(cards) == 1 and sold_labels(cards[0]):
                label_sold = True
                break
    if sold is None and label_sold:
        sold = True
    closest = steps[-1] if steps else None
    return closest, sold


def cache_key(e, url):
    return f"{url}|{e['date']}|{se.title_key(e['title'])}"


async def main():
    data = json.loads(EVENTS.read_text())
    events = data['events']
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    cache = {k: v for k, v in cache.items() if k.split('|')[-2] >= TODAY.isoformat()}

    upcoming = [e for e in events if e.get('date', '') >= TODAY.isoformat() and str(e.get('ticket_url', '')).startswith('http')]
    by_venue = {}
    for e in events:
        by_venue.setdefault(se.canonical_venue(e.get('venue', '')), []).append(e)
    url_titles = {}
    for e in upcoming:
        url_titles.setdefault(e['ticket_url'], set()).add(se.title_key(e['title']))
    hints = {}
    for s in SOURCES:
        if not s.get('disabled'):
            hints.setdefault(se.canonical_venue(s['venue']), []).append(s['url'])

    def due(e):
        c = cache.get(cache_key(e, e['ticket_url']))
        if not c:
            return True
        age = (TODAY - date.fromisoformat(c['checked'])).days
        near = (date.fromisoformat(e['date']) - TODAY).days <= NEAR_DAYS
        return age >= (1 if near else RECHECK_DAYS)

    todo = sorted([e for e in upcoming if due(e)], key=lambda e: e['date'])
    print(f'{len(upcoming)} upcoming events with a ticket link; {len(todo)} to check this run')
    async with se.async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        fx = Fetcher(browser)

        async def one(e):
            url = e['ticket_url']; venue = se.canonical_venue(e.get('venue', ''))
            generic = generic_url(url) or len(url_titles.get(url, ())) > 1
            others = {se.title_key(x['title']) for x in by_venue.get(venue, [])} - {se.title_key(e['title'])}
            try:
                closest, sold = await check_event(fx, e, url, generic, others, hints.get(venue, []))
            except Exception as exc:
                print(f'  ! {e["id"]}: {exc}', file=sys.stderr); return
            if fx.out_of_time() and closest is None and sold is None:
                return  # not reached in time: try again next run
            cache[cache_key(e, url)] = {'url': closest, 'sold': sold, 'checked': TODAY.isoformat()}

        done = 0
        async def counted(e):
            nonlocal done
            await one(e); done += 1
            if done % 200 == 0:
                print(f'  {done}/{len(todo)} checked, {fx.count} pages, {int(time.monotonic() - fx.started)}s', flush=True)
        tasks = [asyncio.create_task(counted(e)) for e in todo]
        _, late = await asyncio.wait(tasks, timeout=TIME_BUDGET + 240)
        for t in late:
            t.cancel()  # anything still going is checked next run
        if late:
            print(f'  {len(late)} events left for the next run')
        await browser.close()
    print(f'Fetched {fx.count} pages ({fx.fails} unreadable) in {int(time.monotonic() - fx.started)}s')

    # A link that several different shows would now share is a venue-wide page
    # (a table booking, a promo), not any one show's tickets: don't use it.
    shared = {}
    for e in upcoming:
        c = cache.get(cache_key(e, e['ticket_url']))
        if c and c.get('url'):
            shared.setdefault(c['url'], []).append(e['title'])
    venue_wide = {u for u, ts in shared.items()
                  if any(not se.same_show(a, b) for a in ts for b in ts if a != b)}
    moved = sold_n = 0
    for e in upcoming:
        c = cache.get(cache_key(e, e['ticket_url']))
        if not c:
            continue
        if c.get('url') and c['url'] != e['ticket_url'] and c['url'] not in venue_wide:
            e['ticket_url'] = c['url']; moved += 1
        if c.get('sold') is True and (e.get('status') or '').upper() != 'SOLD OUT':
            e['status'] = 'SOLD OUT'; sold_n += 1
    sold_total = sum(1 for e in upcoming if (e.get('status') or '').upper() == 'SOLD OUT')
    print(f'Ticket links moved closer to the seller: {moved}; newly marked sold out: {sold_n}; sold out in total: {sold_total}')
    CACHE.write_text(json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=1) + '\n')
    EVENTS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
