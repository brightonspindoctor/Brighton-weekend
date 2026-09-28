#!/usr/bin/env python3
"""Regression checks for high-value events known to be publicly listed."""
import json, sys
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/"events.json").read_text())
expected=json.loads((ROOT/"required-events.json").read_text()).get("events",[])
start=date.fromisoformat(data["range_start"]); end=date.fromisoformat(data["range_end"])
events=data.get("events",[]); missing=[]
for wanted in expected:
    d=date.fromisoformat(wanted["date"])
    if d < start or d > end: continue
    needle=wanted["title_contains"].lower()
    matches=[e for e in events if e.get("date")==wanted["date"] and e.get("venue")==wanted["venue"] and needle in str(e.get("title","")).lower()]
    if not matches: missing.append(f"{wanted['title_contains']} | {wanted['date']} | {wanted['venue']}")
if missing:
    print("ERROR: critical upcoming events were not discovered:",file=sys.stderr)
    print("\n".join(" - "+x for x in missing),file=sys.stderr)
    raise SystemExit(1)
print(f"Validated {len(expected)} critical event regression checks.")
