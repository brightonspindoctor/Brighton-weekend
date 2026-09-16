#!/usr/bin/env python3
"""Remove event classes that should not be published in Brighton Weekend."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'events.json'

DOME_VENUES = {
    'brighton dome',
    'dome - concert hall',
    'dome - corn exchange',
    'dome - studio theatre',
}
PATTERNS_RECURRING = (
    'foundations',
    'fnky frdy',
    'fnky friday',
    'bottomless brunch',
)

data = json.loads(OUT.read_text())
events = data.get('events', [])
kept = []
removed_dome = 0
removed_patterns = 0

for event in events:
    venue = (event.get('venue') or '').strip().lower()
    title = (event.get('title') or '').strip().lower()

    if venue in DOME_VENUES:
        removed_dome += 1
        continue

    if venue == 'patterns' and any(marker in title for marker in PATTERNS_RECURRING):
        removed_patterns += 1
        continue

    kept.append(event)

data['events'] = kept
data['venues'] = sorted({e.get('venue') for e in kept if e.get('venue')})
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
print(f'Removed {removed_dome} Brighton Dome events and {removed_patterns} recurring Patterns events; kept {len(kept)} events.')
