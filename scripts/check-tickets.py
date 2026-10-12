#!/usr/bin/env python3
"""Get each event's ticket link as close to buying as possible, and mark
sold-out shows. Runs after prepare-events.py, before the event pages are built.

For each upcoming event it follows the ticket link, at most three steps:

1. A homepage or listings page (Brighton Centre's homepage, an ents24 venue
   page): find this event's card on it (its title, and its date when the card
   shows one) and follow the card's link.
2. An event page on a venue's site: follow its "Book tickets" / "Get tickets"
   / "Buy from ..." button to where tickets are sold (AXS, DICE, Ticketsolve,
   Eventbrite...). On a page listing several performances, only the button in
   this performance's row (its date, and its time when two are on one day).
   Menus, footers and "you might also like" blocks are ignored, and so are
   venue, promoter, artist and tour pages, which list many events.
3. A ticketing page: stop.

Sold out is only ever set when a page says so, never guessed:
- the seller's structured data (schema.org) gives every ticket type as sold
  out (on DICE, every ticket type on the waiting list); or
- with no such data, a "Sold out" / "Fully booked" label of the page's own:
  in the show's title ("Band *SOLD OUT*"), beside this performance's date
  with nothing for that performance still on sale (another ticket type, an
  "Add" button, "3 tickets available"), or on a page with no live booking
  button at all; or on the show's card on the venue's own listings page.
  Sentences ("they sold out their last tour"), hidden page templates and a
  label beside another date or time don't count.
Seller data saying tickets are on sale always wins over a label.

Results are kept in ticket-cache.json, so events more than three weeks away
are rechecked every few days and nearer ones daily, within a time limit.
Pages that can't be read (some sites block automated visits) leave the event
as it was. Each sold-out decision records why in the cache ("why").
"""
import asyncio, importlib.util, json, os, re, sys, time
from collections import OrderedDict
from datetime import date
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
INFO_PATHS = re.compile(r'/(?:booking-tickets|booking-info|faqs?|help|contact|about|access|visiting(?:-us)?|terms|privacy|login|account|basket|cart|gift[\w-]*|membership)(?:/|$)', re.I)
# A venue's, promoter's, artist's or tour's page lists many events, even when its address has a number in it
# (seetickets.com/promoter/melting-vinyl/7460, ticketmaster.co.uk/venue/415678, eventbrite.co.uk/o/...).
ROSTER_PATHS = re.compile(r'/(?:venue|venues|location|locations|tour|tours|artist|artists|promoters?|organi[sz]ers?|o)/|/(?:venue|venues|location|tour|artist|promoters?|organi[sz]ers?)/?$', re.I)
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
    if ROSTER_PATHS.search(p.path):
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


def small(el, limit=40):
    """An element with few descendants (a label, a title or a button), not a page section."""
    return len(el.find_all(True, limit=limit)) < limit


CARD_TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'span', 'div', 'p', 'strong', 'li']


def text_index(root):
    """Every short piece of text on a page, read once: [(element, text, title key)]."""
    out = []
    for el in root.find_all(CARD_TAGS):
        if not small(el):
            continue
        t = own_text(el)
        if t and len(t) <= 200:
            out.append((el, t, se.title_key(t)))
    return out


HIDDEN_CLASSES = {'hidden', 'is-hidden', 'd-none', 'hide', 'visually-hidden', 'sr-only', 'screen-reader-text', 'invisible'}


def hidden(el):
    """Hidden on the page (a template the site shows only when it applies)."""
    for x in [el, *el.parents]:
        attrs = getattr(x, 'attrs', None) or {}
        if 'hidden' in attrs:  # (not aria-hidden: that hides from screen readers, not from the page)
            return True
        if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', str(attrs.get('style', '')), re.I):
            return True
        if HIDDEN_CLASSES & set(attrs.get('class', []) or []):
            return True
    return False


def sold_labels(root):
    """Elements in root that are a sold-out label of their own."""
    found = []
    for el in root.find_all(True):
        if not small(el, 15) or hidden(el):
            continue
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


DOORS = re.compile(r'doors?\s*(?:open(?:ing)?)?\s*(?:at|from)?\s*[:\-]?\s*\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?', re.I)
# Signs that tickets can still be bought: "3 tickets available", an "Add" button.
AVAILABLE_TEXT = re.compile(r'\b\d+\s+(?:tickets?|places?|spaces?|seats?)\s+(?:available|left|remaining)\b'
                            r'|^\W*add(?:\s+to\s+(?:basket|cart|bag|order))?\W*$|^\W*(?:select|choose)\s+(?:tickets?|seats?|quantity)\W*$', re.I)


# "On sale 20 Feb 2026 10:00", "Announced 3 March": dates that aren't the show's.
ON_SALE = re.compile(r'\b(?:(?:general\s+|pre-?)?(?:on\s*)?sale|announced|released|published|added|updated)\s*(?:date)?\s*[:\-]?\s*(?:on\s+|from\s+)?(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s*)?\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+\.?(?:\s+\d{4})?(?:,?\s*(?:at\s*)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?', re.I)


CLOCK_24 = re.compile(r'(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])(?!\s*(?:am|pm))', re.I)


def times_in(text):
    """Start times written in text, as HH:MM: '7:30 pm', '19:30' (doors times left out)."""
    text = DOORS.sub(' ', text)
    out = {hhmm(t) for t in se.TIME_RE.findall(text)}
    text = se.TIME_RE.sub(' ', text)
    out |= {f'{int(h):02d}:{m}' for h, m in CLOCK_24.findall(text)}
    return out - {''}


def hhmm(t):
    m = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', t.strip(), re.I)
    if not m:
        return ''
    h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == 'pm' else 0)
    return f'{h:02d}:{int(m.group(2) or 0):02d}'


def when_near(el):
    """(dates, start times) written in the smallest block around el that shows a
    date: a performance row on a page listing several. Empty when el isn't in
    such a row, or the nearest dated block covers several dates."""
    blk = el; near_times = None
    for _ in range(7):
        blk = blk.parent
        if blk is None or blk.name in ('body', 'html', '[document]') or not small(blk, 150):
            break
        text = ON_SALE.sub(' ', own_text(blk))
        if near_times is None and times_in(text):
            near_times = times_in(text)  # the closest row with a time: "21:00  Sold out"
        dates = set()
        for m in se.DATE_RE.finditer(text):
            d = se.parse_dt(m.group(1))
            if d and d.date() >= TODAY:  # a past date is an on-sale or announcement date, not a performance
                dates.add(d.date().isoformat())
        if dates:
            if len(dates) > 1:
                return set(), set()
            return dates, (near_times or set())
    return set(), set()


def for_this_show(dates, times, event):
    """True/False when a row's date says whether it is this event's; None when it doesn't say.
    (Times aren't compared here: listings give doors or stage times inconsistently.)"""
    if not dates:
        return None
    return event['date'] in dates


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
    cands = {}
    for el, u, t in live_ctas(root, page_url):
        if el.name != 'a' or u.rstrip('/') == here:
            continue
        if host_of(u) == host_of(page_url) and not is_ticket_site(u):
            continue  # another page on the same site ("Booking info"), not the seller
        if any(n in host_of(u) for n in NOT_SELLERS) or 'queue-it.net' in host_of(el.get('href') or ''):
            continue  # a listings site, or a queue in front of the venue's own booking (the page is the place to book)
        if u not in cands:
            dates, times = when_near(el)
            cands[u] = (for_this_show(dates, times, event), times)
    if not cands:
        return None
    mine = [u for u, (ok, _) in cands.items() if ok]
    if len(mine) > 1 and len({host_of(u) for u in mine}) == 1:
        # Two performances on the same day with one seller (a 7pm and a 9pm show): go by the time.
        timed = [u for u in mine if event.get('time') and event['time'] in cands[u][1]]
        return timed[0] if len(timed) == 1 else None
    if mine:
        # This date's button(s). Several here are different sellers for the same
        # performance (Hope & Ruin: Fatsoma, DICE, Gigantic): the venue lists its main one first.
        return mine[0]
    if any(ok is False for ok, _ in cands.values()):
        return None  # the buttons are for other dates (or times): this one has none, or it's sold out
    if len(cands) > 1 and len({host_of(u) for u in cands}) == 1:
        return None  # several bookings with one seller and nothing to tell which is this event's
    return next(iter(cands))


def cards_for(root, event, other_keys, index=None):
    """Smallest blocks on a listing page that are this event's card."""
    key = se.title_key(event['title'])
    if len(key) < 3:
        return []
    words = {w for w in key.split() if len(w) >= 3} or set(key.split())
    cards = []
    for el, t, tk in (index if index is not None else text_index(root)):
        if not words & set(tk.split()):
            continue  # shares no word with the title (quick test before the slower comparison)
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


UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'
# Sites that build their pages in the browser: a plain request misses their
# booking buttons or ticket availability. Everything else is fetched with a
# plain request first (much quicker), and with the browser if that fails.
# (Checked against browser and plain copies of 147 real event pages.)
BROWSER_HOSTS = ('brightondome.org', 'dice.fm', 'ents24.com')
# Ticketing sites whose plain pages carry the same availability data as the
# browser's. On other ticketing sites a page that says nothing is retried in
# the browser before giving up.
PLAIN_OK = ('eventbrite.', 'skiddle.', 'tickettailor.', 'wegottickets.', 'songkick.', 'gigantic.')
PAGE_TIMEOUT = 90


class Fetcher:
    def __init__(self, browser=None):
        self.browser = browser; self.ctx = None
        self.mem = OrderedDict(); self.pending = {}
        self.sem = asyncio.Semaphore(10); self.hosts = {}
        self.started = time.monotonic(); self.count = 0; self.fails = 0; self.browser_count = 0

    def out_of_time(self):
        return time.monotonic() - self.started > TIME_BUDGET

    async def get(self, url, browser=False):
        """(html, final url, came from the browser). '' when the page couldn't be read."""
        key = (url, browser)
        if key in self.mem:
            self.mem.move_to_end(key)
            return self.mem[key]
        if key in self.pending:
            return await asyncio.shield(self.pending[key])
        fut = asyncio.get_running_loop().create_future(); self.pending[key] = fut
        result = ('', url, False)
        try:
            if not self.out_of_time():
                hs = self.hosts.setdefault(host_of(url), asyncio.Semaphore(3))
                async with hs:            # at most 3 at a time per site, and
                    async with self.sem:  # 10 overall
                        result = await asyncio.wait_for(self._fetch(url, browser), timeout=PAGE_TIMEOUT)
        except Exception:
            self.fails += 1
        finally:
            if not fut.done():
                fut.set_result(result)
            self.pending.pop(key, None)
            self.mem[key] = result
            while len(self.mem) > 300:
                self.mem.popitem(last=False)
        return result

    async def _fetch(self, url, force_browser):
        html, final, via = '', url, False
        if not force_browser and not any(h in host_of(url) for h in BROWSER_HOSTS):
            try:
                html, final = await asyncio.wait_for(asyncio.to_thread(se.fetch_plain, url), timeout=40)
            except Exception:
                html = ''
            if any(h in host_of(final) for h in BROWSER_HOSTS):
                html = ''  # redirected (link.dice.fm -> dice.fm) to a site that needs the browser
        if len(html) < 5000 or 'Just a moment' in html[:3000]:
            h2, f2 = await self._browser_get(url)
            if len(h2) > len(html):
                html, final, via = h2, f2, True
        self.count += 1
        if len(html) < 3000:
            self.fails += 1; html = ''
        return html, final, via

    async def _browser_get(self, url):
        if self.browser is None:
            return '', url
        if self.ctx is None:
            self.ctx = await self.browser.new_context(user_agent=UA, locale='en-GB')
        page = await self.ctx.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass
            await page.wait_for_timeout(1200)
            self.browser_count += 1
            return await page.content(), page.url
        except Exception:
            return '', url
        finally:
            try:
                await page.close()
            except Exception:
                pass


# ---- Reading pages (these run in worker threads, so one big page being read
# doesn't hold up the others, and each page's parsed copy is dropped as soon
# as it has been read) --------------------------------------------------------

def analyse_listing(html, final, items):
    """For each (event, other titles at its venue): (cards found, card says sold out, card's link)."""
    root = strip_chrome(soup_of(html))
    index = text_index(root)
    out = {}
    for event, other_keys in items:
        cards = cards_for(root, event, other_keys, index)
        if len(cards) != 1:
            out[event['id']] = (len(cards), '', None)
        else:
            labels = sold_labels(cards[0])
            out[event['id']] = (1, ('card label: ' + own_text(labels[0])[:40]) if labels else '', card_link(cards[0], final, event))
    return out


def match_show(dates, times, event, by_time=False):
    """'yes' when a row's date (and, with by_time, its time) is this event's, 'no'
    when it is another performance's, '' when the row doesn't say."""
    if not dates:
        return ''
    if event['date'] not in dates:
        return 'no'
    if by_time and times and event['time'] not in times:
        return 'no'  # the same day's other performance (a 7pm and a 9pm show)
    return 'yes'


def live_controls(root, final):
    """What on the page can still be bought with: booking buttons and links,
    an "Add" button, "3 tickets available"."""
    out = [el for el, u, t in live_ctas(root, final) if u != final or el.name == 'button']
    for el in root.find_all(['button', 'a', 'span', 'div', 'p', 'li', 'label', 'td']):
        if not small(el, 10):
            continue
        t = own_text(el)
        if not t or len(t) > 60 or not AVAILABLE_TEXT.search(t) or UNAVAILABLE_CTA.search(t):
            continue
        if el.has_attr('disabled') or 'disabled' in ' '.join(el.get('class', []) or []).lower() or hidden(el):
            continue
        out.append(el)
    return [el for el in out if not hidden(el)]


def page_label(root, final, event, ld_dates):
    """Why the page says this event is sold out ('' if it doesn't)."""
    if ld_dates and event['date'] not in ld_dates:
        return ''  # the page is about another performance
    labels = sold_labels(root)
    if not labels:
        return ''
    # Times are only compared when the page lists this event's time and another
    # one (a 7pm and a 9pm show): otherwise a different time is just doors vs
    # stage time (our listing says 18:30, the page 7:30 pm).
    page_times = set()
    for el in root.find_all(CARD_TAGS):
        if small(el, 6):
            t = own_text(el)
            if len(t) <= 60:
                page_times |= times_in(t)
    by_time = bool(event.get('time')) and event['time'] in page_times and len(page_times) >= 2
    rows = [(l, match_show(*when_near(l), event, by_time)) for l in labels]
    titled = [l for l, m in rows if m != 'no' and l.name in ('h1', 'h2', 'h3') and SOLD_IN_HEADING.search(own_text(l))]
    if titled:
        return 'in the title: ' + own_text(titled[0])[:60]  # "Band *SOLD OUT*"
    mine = [l for l, m in rows if m == 'yes']
    undated = [l for l, m in rows if m == '']
    controls = [(c, match_show(*when_near(c), event, by_time)) for c in live_controls(root, final)]
    if mine and not [c for c, m in controls if m == 'yes']:
        # Labelled sold out beside this performance's date, and nothing for this
        # performance can still be bought (another ticket type, say).
        return 'label next to this date: ' + own_text(mine[0])[:40]
    if undated and not mine and not [c for c, m in controls if m != 'no']:
        return 'label, no live booking button: ' + own_text(undated[0])[:40]
    return ''


def analyse_page(html, final, event):
    """(schema.org verdict, why the page labels the show sold out, the next link towards the seller)."""
    raw = soup_of(html)
    verdict = ld_verdict(raw, event, final)
    ld_dates = {str(o.get('startDate', ''))[:10] for o in ld_events(raw)} - {''}
    root = strip_chrome(raw)
    label = '' if verdict is not None else page_label(root, final, event, ld_dates)
    nxt = None
    if not (is_ticket_site(final) and verdict is not None):
        nxt = booking_link(root, final, event)
    return verdict, label, nxt


EVIDENCE = Path(os.environ['TICKET_EVIDENCE']) if os.environ.get('TICKET_EVIDENCE') else None


def keep_evidence(event, final, html, why):
    """For checking the checker: save the page behind a sold-out decision (TICKET_EVIDENCE=dir)."""
    if EVIDENCE is None or not html:
        return
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    n = len(list(EVIDENCE.glob(f"{event['id'][:120]}-*.html")))
    (EVIDENCE / f"{event['id'][:120]}-{n}.html").write_text(html)
    with open(EVIDENCE / 'why.jsonl', 'a') as f:
        f.write(json.dumps({'id': event['id'], 'title': event['title'], 'date': event['date'], 'page': final, 'why': why, 'file': f"{event['id'][:120]}-{n}.html"}) + '\n')


async def follow(fx, event, url, steps):
    """Follow the booking button towards the seller: (steps taken, verdict, why).
    The verdict is True/False when the seller's data says, else None; why
    explains a sold-out verdict or label."""
    start = url; sold = None; why = ''
    for _ in range(MAX_HOPS):
        html, final, via = await fx.get(url)
        if not html:
            break
        verdict, label, nxt = await asyncio.to_thread(analyse_page, html, final, event)
        if verdict is None and not via and is_ticket_site(final) and not any(h in host_of(final) for h in PLAIN_OK):
            # A ticketing site's plain page said nothing: its browser page may.
            h2, f2, _ = await fx.get(url, browser=True)
            if h2:
                html, final = h2, f2
                verdict, label, nxt = await asyncio.to_thread(analyse_page, html, final, event)
        if verdict is not None:
            sold = verdict
            if verdict:
                why = f'seller data says sold out ({host_of(final)})'
                keep_evidence(event, final, html, why)
        elif label and not why:
            why = f'{label} ({host_of(final)})'
            keep_evidence(event, final, html, why)
        del html
        if not nxt or nxt in steps or nxt == start:
            break
        url = nxt; steps.append(nxt)
    return steps, sold, why


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

    def venue_of(e):
        return se.canonical_venue(e.get('venue', ''))

    def others_for(e):
        return {se.title_key(x['title']) for x in by_venue.get(venue_of(e), [])} - {se.title_key(e['title'])}

    def is_generic(e):
        """A listings page rather than this show's own: one address for several different shows."""
        titles = url_titles.get(e['ticket_url'], ())
        return generic_url(e['ticket_url']) or any(not se.same_show(a, b) for a in titles for b in titles if a < b)

    def due(e):
        c = cache.get(cache_key(e, e['ticket_url']))
        if not c:
            return True
        age = (TODAY - date.fromisoformat(c['checked'])).days
        near = (date.fromisoformat(e['date']) - TODAY).days <= NEAR_DAYS
        return age >= (1 if near else RECHECK_DAYS)

    todo = sorted([e for e in upcoming if due(e)], key=lambda e: e['date'])
    print(f'{len(upcoming)} upcoming events with a ticket link; {len(todo)} to check this run', flush=True)
    card = {}           # event id -> (link from its card on a listings page, why the card says sold out)
    listing_sold = {}   # event id -> why its card on the venue's own listings says sold out
    results = {}
    fx = Fetcher()
    try:
        async with se.async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            fx = Fetcher(browser)
            try:
                # 1. Listings pages, each read once for all the events on it.
                async def resolve_group(url, evs):
                    pending = list(evs); pages = [url]
                    for e in evs:
                        pages += [u for u in hints.get(venue_of(e), []) if u not in pages]
                    if not urlparse(url).path.strip('/'):
                        pages += [urljoin(url, '/whats-on/'), urljoin(url, '/events/')]  # a homepage shows only some events
                    for lu in pages:
                        if not pending:
                            break
                        html, final, _ = await fx.get(lu)
                        if not html:
                            continue
                        res = await asyncio.to_thread(analyse_listing, html, final, [(e, others_for(e)) for e in pending])
                        still = []
                        for e in pending:
                            n, sold_label, link = res[e['id']]
                            _, old_why = card.get(e['id'], (None, ''))
                            if n == 1:
                                card[e['id']] = (link, old_why or (f'{sold_label} ({host_of(final)})' if sold_label else ''))
                                if sold_label:
                                    keep_evidence(e, final, html, card[e['id']][1])
                            if not (n == 1 and link):
                                still.append(e)
                        pending = still
                        del html

                async def venue_labels(venue, evs):
                    for lu in hints.get(venue, []):
                        html, final, _ = await fx.get(lu)
                        if not html:
                            continue
                        res = await asyncio.to_thread(analyse_listing, html, final, [(e, others_for(e)) for e in evs])
                        for e in evs:
                            n, sold_label, _ = res[e['id']]
                            if n == 1 and sold_label and e['id'] not in listing_sold:
                                listing_sold[e['id']] = f'{sold_label} on the venue listing ({host_of(final)})'
                                keep_evidence(e, final, html, listing_sold[e['id']])
                        del html

                groups = {}
                for e in todo:
                    if is_generic(e):
                        groups.setdefault(e['ticket_url'], []).append(e)
                plain = {}
                for e in todo:
                    if not is_generic(e):
                        plain.setdefault(venue_of(e), []).append(e)
                await asyncio.gather(*(resolve_group(u, evs) for u, evs in groups.items()),
                                     *(venue_labels(v, evs) for v, evs in plain.items()))
                print(f'  listings read: {fx.count} pages, {int(time.monotonic() - fx.started)}s', flush=True)

                # 2. Each event's own page, then on to the seller: a dozen events at a time, soonest first.
                lanes = asyncio.Semaphore(12); done = 0

                async def one(e):
                    nonlocal done
                    async with lanes:
                        steps = []; why = ''; sold = None
                        try:
                            if is_generic(e):
                                link, why = card.get(e['id'], (None, ''))
                                if link:
                                    steps.append(link)
                                    steps, sold, why2 = await follow(fx, e, link, steps)
                                    why = why2 if sold is not None else (why or why2)
                            else:
                                steps, sold, why = await follow(fx, e, e['ticket_url'], steps)
                        except Exception as exc:
                            print(f'  ! {e["id"]}: {exc}', file=sys.stderr); return
                        if sold is None:
                            why = why or listing_sold.get(e['id'], '')
                            sold = True if why else None
                        if sold is False:
                            why = ''  # the seller says tickets are on sale: that wins over any label
                        closest = steps[-1] if steps else None
                        if not (fx.out_of_time() and closest is None and sold is None):
                            results[e['id']] = (closest, sold, why)
                        done += 1
                        if done % 200 == 0:
                            print(f'  {done}/{len(todo)} checked, {fx.count} pages, {int(time.monotonic() - fx.started)}s', flush=True)

                tasks = [asyncio.create_task(one(e)) for e in todo]
                left = max(60, TIME_BUDGET + 240 - (time.monotonic() - fx.started))
                _, late = await asyncio.wait(tasks, timeout=left)
                for t in late:
                    t.cancel()  # anything still going is checked next run
                if late:
                    await asyncio.gather(*late, return_exceptions=True)
                    print(f'  {len(late)} events left for the next run', flush=True)
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
    except Exception as exc:
        # Whatever went wrong, keep what was found so far and leave the rest as it was.
        print(f'Ticket check stopped early: {exc}', file=sys.stderr)
    print(f'Fetched {fx.count} pages ({fx.browser_count} in the browser, {fx.fails} unreadable) in {int(time.monotonic() - fx.started)}s')

    for e in todo:
        if e['id'] in results:
            closest, sold, why = results[e['id']]
            entry = {'url': closest, 'sold': sold, 'checked': TODAY.isoformat()}
            if sold:
                entry['why'] = why
            cache[cache_key(e, e['ticket_url'])] = entry

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
