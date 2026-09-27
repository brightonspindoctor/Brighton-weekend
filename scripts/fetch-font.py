"""Download Plus Jakarta Sans (latin, variable 400-800) into fonts/ so the app
serves the font itself and visitors' browsers never contact Google.
Run by .github/workflows/fetch-font.yml; safe to run again."""
import re
import sys
import urllib.request
from pathlib import Path

CSS_URL = "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400..800&display=swap"
OUT = Path(__file__).resolve().parents[1] / "fonts" / "plus-jakarta-sans-latin.woff2"
# A modern browser user agent makes Google return woff2 files.
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def latin_url(css):
    # Google splits the font by character set; each block starts with a comment such as /* latin */.
    for label, block in re.findall(r"/\*\s*([a-z-]+)\s*\*/\s*(@font-face\s*\{[^}]*\})", css):
        if label == "latin":
            m = re.search(r"url\((https://[^)]+\.woff2)\)", block)
            if m:
                return m.group(1)
    return None

def main():
    css = get(CSS_URL).decode("utf-8")
    url = latin_url(css)
    if not url:
        sys.exit("Could not find the latin woff2 file in Google's font CSS")
    data = get(url)
    if data[:4] != b"wOF2" or len(data) < 10_000:
        sys.exit(f"Downloaded file is not a valid woff2 font ({len(data)} bytes)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"Saved {OUT.relative_to(OUT.parents[1])} ({len(data):,} bytes)")

if __name__ == "__main__":
    main()
