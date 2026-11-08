#!/usr/bin/env python3
"""Refresh the CPI data inside index.html from SingStat's Table Builder API.

Run:   python update.py                  (fetch live data)
       python update.py --from-file x.json   (use a saved API response, for testing)

It only changes index.html if every safety check passes. Otherwise it stops
with a message and leaves the page exactly as it was.
"""
import json, re, sys, urllib.request, urllib.parse
from datetime import date

TABLE = "M213751"  # CPI, 2024 as base year, monthly
BASE = "https://tablebuilder.singstat.gov.sg/api/table/tabledata/" + TABLE
START_YEAR = 2019
SERIES = ["All Items", "Food", "Restaurants, Cafes & Pubs", "Clothing & Footwear",
          "Transport", "Bus & Train Fares", "Information & Communication",
          "Recreation, Sport & Culture", "Education",
          "Private Tuition & Other Educational Courses"]
MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
TOLERANCE = 0.5  # max allowed change to an already-published month (index points)

def norm(s):
    return re.sub(r"\s+", " ", s.replace("&", "and")).strip().lower()

def month_key(label):
    y, m = label.split()
    return int(y), MON.index(m)

def fetch():
    today = date.today()
    labels = [f"{y} {MON[m]}" for y in range(START_YEAR, today.year + 1) for m in range(12)]
    url = BASE + "?" + urllib.parse.urlencode({"timeFilter": ",".join(labels), "limit": 2000})
    req = urllib.request.Request(url, headers={"User-Agent": "teen-inflation-calculator"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

def extract(js):
    rows = (js.get("Data") or {}).get("row")
    if not rows:
        sys.exit("STOP: the API response has no data rows. Page not changed.")
    found = {s: [] for s in SERIES}
    want = {norm(s): s for s in SERIES}
    for row in rows:
        key = norm(row.get("rowText", ""))
        if key in want:
            found[want[key]].append(row)
    for s, hits in found.items():
        if len(hits) != 1:
            names = [norm(r.get("rowText", "")) for r in rows][:60]
            sys.exit(f"STOP: expected exactly one row named '{s}', found {len(hits)}. "
                     f"First row names seen: {names}. Page not changed.")
    out = {}
    for s, (row,) in found.items():
        out[s] = {c["key"]: float(c["value"]) for c in row.get("columns", [])
                  if c.get("value") not in (None, "", "na", "-")}
    return out

def main():
    js = json.load(open(sys.argv[2])) if len(sys.argv) > 2 and sys.argv[1] == "--from-file" else fetch()
    new = extract(js)
    months = sorted(set.intersection(*[set(v) for v in new.values()]), key=month_key)
    months = [m for m in months if month_key(m)[0] >= START_YEAR]
    if not months:
        sys.exit("STOP: no months common to all series. Page not changed.")
    # months must be consecutive
    idx = [month_key(m)[0] * 12 + month_key(m)[1] for m in months]
    if any(b - a != 1 for a, b in zip(idx, idx[1:])):
        sys.exit("STOP: the months returned have gaps. Page not changed.")
    data = {"m": months, "s": {s: [new[s][m] for m in months] for s in SERIES}}

    html = open("index.html", encoding="utf-8").read()
    mt = re.search(r"/\*DATA\*/(.*?)/\*END\*/", html, re.S)
    if not mt:
        sys.exit("STOP: data markers not found in index.html.")
    old = json.loads(mt.group(1))
    if month_key(months[-1]) < month_key(old["m"][-1]):
        sys.exit(f"STOP: API latest month {months[-1]} is older than the page's {old['m'][-1]}.")
    for i, m in enumerate(old["m"]):
        if m in months:
            j = months.index(m)
            for s in SERIES:
                if abs(old["s"][s][i] - data["s"][s][j]) > TOLERANCE:
                    sys.exit(f"STOP: {s} for {m} changed from {old['s'][s][i]} to "
                             f"{data['s'][s][j]}. Check for a rebase or a parsing problem. Page not changed.")
    new_json = json.dumps(data, separators=(",", ":"))
    if new_json == mt.group(1):
        print("No change: page already has data to", months[-1]); return
    html = html[:mt.start(1)] + new_json + html[mt.end(1):]
    open("index.html", "w", encoding="utf-8").write(html)
    added = [m for m in months if m not in old["m"]]
    print("Updated. Latest month:", months[-1], "| new months:", added or "none (revisions only)")

if __name__ == "__main__":
    main()
