#!/usr/bin/env python3
"""Validate the separate festival dataset before publishing."""
import json,re,sys
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/"festivals.json"
if not DATA.exists(): raise SystemExit("festivals.json is missing")
try: data=json.loads(DATA.read_text())
except Exception as exc: raise SystemExit(f"invalid festivals.json: {exc}")
festivals=data.get("festivals")
if not isinstance(festivals,list): raise SystemExit("festivals must be an array")
try: start=date.fromisoformat(data["range_start"]); end=date.fromisoformat(data["range_end"])
except Exception: raise SystemExit("invalid festival date range")
if end!=date(start.year+1,12,31): raise SystemExit("festival range must end on 31 December of the following calendar year")
ids=set(); keys=set(); errors=[]
for i,f in enumerate(festivals):
    for k in ("id","title","date","date_end","location","category","ticket_url"):
        if not f.get(k): errors.append(f"{i}: missing {k}")
    try: d=date.fromisoformat(str(f.get("date")))
    except Exception: errors.append(f"{i}: invalid date"); continue
    try: de=date.fromisoformat(str(f.get("date_end"))); assert d<=de<=end
    except Exception: errors.append(f"{f.get('id')}: invalid date_end or outside range")
    if not str(f.get("id","")).startswith("festival:"): errors.append(f"{i}: id is not festival-scoped")
    if f.get("id") in ids: errors.append(f"duplicate id {f.get('id')}")
    ids.add(f.get("id"))
    key=(re.sub(r"[^a-z0-9]+"," ",str(f.get("title")).lower()).strip(),d.isoformat())
    if key in keys: errors.append(f"duplicate title/date {f.get('title')} {d}")
    keys.add(key)
    if f.get("category") not in {"Music","Arts & Culture","Food & Drink","Family","Wellness","Comedy","Film","Sport & Outdoor","Other"}: errors.append(f"{f.get('id')}: invalid category")
if errors:
    print("\n".join(errors[:50]),file=sys.stderr); raise SystemExit(1)
print(f"Validated {len(festivals)} festivals from {start} to {end}.")
