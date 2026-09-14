#!/usr/bin/env python3
"""Refresh Brighton Weekend event data from the configured venue websites.

The scraper deliberately prefers structured Event JSON-LD and falls back to
visible event-card text. It never invents a start time. A refresh is rejected
if too few sources succeed or too few events are found, so a broken venue page
cannot wipe a good events.json.
"""
import asyncio, json, re, sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / "event-sources.json").read_text())
OUT = ROOT / "events.json"
TZ = ZoneInfo("Europe/London")
NOW = datetime.now(TZ)
RANGE_START = NOW.date()
RANGE_END = (NOW + timedelta(days=280)).date()

MONTHS = r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
DATE_RE = re.compile(rf"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\.?\s*(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s*(?:\d{{4}})?|(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?)\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", re.I)

CATEGORY_WORDS = {
    "Comedy": ["comedy", "comedian", "stand-up", "stand up", "laughs"],
    "Club": ["club", "dj", "dnb", "drum & bass", "rave", "techno", "house night", "party"],
    "Theatre": ["theatre", "theater", "play", "musical", "west end"],
    "Dance": ["dance", "ballet", "contemporary dance"],
    "Family": ["family", "kids", "children", "storytelling", "baby"],
    "Talk": ["talk", "in conversation", "lecture", "spoken word", "author"],
    "Sport": ["football", "boxing", "wrestling", "sport", "racecourse"],
    "Music": ["gig", "live", "band", "concert", "tour", "festival", "dj set", "orchestra", "singer"],
}


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def category_for(title, text, source_type=""):
    hay = clean(f"{title} {text} {source_type}").lower()
    for cat, words in CATEGORY_WORDS.items():
        if any(w in hay for w in words):
            return cat
    return "Other"


def parse_dt(value, default_year=None):
    if not value:
        return None
    s = clean(str(value))
    try:
        dt = dateparser.parse(s, dayfirst=True, fuzzy=True, default=datetime(default_year or NOW.year, 1, 1))
        if not dt:
            return None
        return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
    except Exception:
        return None


def normalise_event(raw, venue, page_url, source_type=""):
    title = clean(raw.get("name") or raw.get("title"))
    if not title:
        return None
    start_raw = raw.get("startDate") or raw.get("start_date") or raw.get("date")
    start = parse_dt(start_raw)
    if not start:
        return None
    end = parse_dt(raw.get("endDate") or raw.get("end_date"))
    if start.date() < RANGE_START or start.date() > RANGE_END:
        return None
    # Reject obvious cancellation/postponement text rather than publishing stale listings.
    blob = clean(" ".join(str(raw.get(k, "")) for k in ("name", "description", "status"))).lower()
    if any(x in blob for x in ("cancelled", "canceled", "postponed", "event cancelled")):
        return None
    url = raw.get("url") or raw.get("offers", {}).get("url") if isinstance(raw.get("offers"), dict) else raw.get("url")
    url = urljoin(page_url, url or page_url)
    ident = re.sub(r"[^a-z0-9]+", "-", f"{start.date()}-{venue}-{title}".lower()).strip("-")[:180]
    item = {
        "id": ident,
        "title": title,
        "date": start.date().isoformat(),
        "venue": venue,
        "time": start.strftime("%H:%M") if start_raw and re.search(r"T|\d{1,2}:\d{2}|am|pm", str(start_raw), re.I) else "",
        "finish_time": end.strftime("%H:%M") if end else "",
        "category": category_for(title, raw.get("description", ""), source_type),
        "ticket_url": url,
    }
    return item


def jsonld_events(html, venue, page_url):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tag in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        try:
            data = json.loads(tag.string or tag.get_text())
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, list):
                stack.extend(obj); continue
            if not isinstance(obj, dict):
                continue
            if "@graph" in obj and isinstance(obj["@graph"], list):
                stack.extend(obj["@graph"])
            typ = obj.get("@type", "")
            types = typ if isinstance(typ, list) else [typ]
            if any(str(t).lower() == "event" for t in types):
                e = normalise_event(obj, venue, page_url, " ".join(map(str, types)))
                if e: out.append(e)
    return out


def dom_events(html, venue, page_url):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    # Event cards are deliberately parsed as whole blocks: this works across the
    # WordPress, Squarespace, Wix and custom venue pages used by the app.
    candidates = soup.find_all(["article", "li", "div"], limit=12000)
    for node in candidates:
        text = clean(node.get_text(" ", strip=True))
        if len(text) < 12 or len(text) > 900:
            continue
        dm = DATE_RE.search(text)
        if not dm:
            continue
        dt = parse_dt(dm.group(1))
        if not dt or not (RANGE_START <= dt.date() <= RANGE_END):
            continue
        links = node.find_all("a", href=True)
        if not links:
            continue
        # Prefer the first reasonably-sized link text, otherwise use a heading.
        title = ""
        href = page_url
        for a in links:
            t = clean(a.get_text(" ", strip=True))
            if 3 <= len(t) <= 180 and t.lower() not in {"more info", "more info & tickets", "buy tickets", "book tickets", "find out more", "event details"}:
                title, href = t, urljoin(page_url, a["href"])
                break
        if not title:
            h = node.find(["h1", "h2", "h3", "h4"])
            title = clean(h.get_text(" ", strip=True)) if h else ""
        if not title or title.lower() in {"what's on", "events", "upcoming events"}:
            continue
        tm = TIME_RE.search(text)
        end_tm = None
        times = TIME_RE.findall(text)
        if len(times) > 1:
            end_tm = times[-1]
        raw = {"name": title, "startDate": f"{dt.date().isoformat()}T{tm.group(1) if tm else '00:00'}", "url": href, "description": text}
        if end_tm: raw["endDate"] = f"{dt.date().isoformat()}T{end_tm}"
        e = normalise_event(raw, venue, page_url, "")
        if e:
            # If the page has no time, don't pretend midnight is a real time.
            if not tm: e["time"] = ""
            out.append(e)
    return out


async def scrape_source(browser, source):
    page = await browser.new_page()
    page.set_default_timeout(25000)
    try:
        await page.goto(source["url"], wait_until="domcontentloaded", timeout=30000)
        try: await page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeoutError: pass
        # Give JS event calendars a short chance to render.
        await page.wait_for_timeout(1500)
        html = await page.content()
        events = jsonld_events(html, source["venue"], page.url)
        if not events:
            events = dom_events(html, source["venue"], page.url)
        return events, page.url, None
    except Exception as exc:
        return [], source["url"], str(exc)
    finally:
        await page.close()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = await asyncio.gather(*(scrape_source(browser, s) for s in SOURCES))
        await browser.close()

    all_events, successful = [], 0
    failures = []
    for source, (events, final_url, err) in zip(SOURCES, results):
        if err:
            failures.append(f"{source['venue']}: {err}")
            continue
        successful += 1
        all_events.extend(events)
        print(f"{source['venue']}: {len(events)} events ({final_url})")

    # Deduplicate by venue/date/title, preferring an event with a real time and URL.
    dedup = {}
    for e in all_events:
        key = (e["venue"].lower(), e["date"], re.sub(r"[^a-z0-9]+", " ", e["title"].lower()).strip())
        old = dedup.get(key)
        if old is None or (not old.get("time") and e.get("time")):
            dedup[key] = e
    events = sorted(dedup.values(), key=lambda x: (x["date"], x["time"] or "99:99", x["venue"], x["title"]))

    print(f"Successful sources: {successful}/{len(SOURCES)}; events: {len(events)}")
    if failures:
        print("Source failures:", file=sys.stderr)
        for f in failures: print(f" - {f}", file=sys.stderr)

    # Safety rails: never replace the live data with a partial/empty scrape.
    if successful < max(12, int(len(SOURCES) * 0.70)):
        raise SystemExit("Too many venue sources failed; refusing to replace events.json")
    if len(events) < 80:
        raise SystemExit("Too few events scraped; refusing to replace events.json")

    venues = sorted({e["venue"] for e in events})
    payload = {
        "updated": NOW.date().isoformat(),
        "range_start": RANGE_START.isoformat(),
        "range_end": RANGE_END.isoformat(),
        "venues": venues,
        "events": events,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {OUT} with {len(events)} events across {len(venues)} venues")


if __name__ == "__main__":
    asyncio.run(main())
