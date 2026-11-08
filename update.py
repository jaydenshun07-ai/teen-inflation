#!/usr/bin/env python3
"""Refresh the CPI data inside index.html from SingStat's Table Builder API.

Run:   python update.py                  (fetch live data)
       python update.py --from-file x.json   (use a saved API response, for testing)

It only changes index.html if every safety check passes. Otherwise it stops
with a message and leaves the page exactly as it was.
"""
import json, os, re, sys, urllib.error, urllib.request, urllib.parse
from datetime import date

TABLE = "M213751"  # CPI, 2024 as base year, monthly
BASE = os.environ.get("SINGSTAT_BASE", "https://tablebuilder.singstat.gov.sg/api/table/tabledata/") + TABLE
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

AGENTS = ["SingStat Python package/2.0.1 https://pypi.org/project/singstat",
          "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"]
META = BASE.replace("/tabledata/", "/metadata/")
PAGE = 3000  # the API returns at most 3000 data points per request

def get(url, params, soft=False):
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    last = ""
    for ua in AGENTS:
        req = urllib.request.Request(full, headers={"Accept": "application/json", "User-Agent": ua})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "replace").replace("\n", " ")
            last = f"HTTP {e.code} | body starts: {body}"
        except Exception as e:
            last = repr(e)
        print("Attempt failed:", last, "| agent:", ua[:30], "| params:", list(params))
    if soft:
        return None
    sys.exit("STOP: SingStat refused or failed every attempt. Last response: " + last + ". Page not changed.")

def fetch():
    meta = get(META, {})
    recs = ((meta.get("Data") or {}).get("records") or {}).get("row") or []
    want = {norm(s): s for s in SERIES}
    cand = {}
    for r in recs:
        k = norm(r.get("rowText", ""))
        if k in want:
            cand.setdefault(want[k], []).append(str(r["seriesNo"]))
    missing = [s for s in SERIES if s not in cand]
    if missing:
        sys.exit(f"STOP: these series are not in the table list: {missing}. "
                 f"First names seen: {[norm(r.get('rowText','')) for r in recs][:40]}. Page not changed.")
    ids = {}
    for s, c in cand.items():
        ids[s] = min(c, key=lambda x: (len(x.split(".")), x))
        if len(c) > 1:
            print(f"Note: '{s}' appears {len(c)} times {c}; using {ids[s]}")
    print("Series numbers:", ids)
    merged, offset = {}, 0
    for _ in range(12):
        js = get(BASE, {"seriesNoOrRowNo": ",".join(ids.values()), "limit": PAGE, "offset": offset}, soft=offset > 0)
        if js is None:
            break
        n = 0
        for r in (js.get("Data") or {}).get("row") or []:
            m = merged.setdefault(r["seriesNo"], {"rowText": r["rowText"], "columns": []})
            cols = r.get("columns") or []
            m["columns"] += cols
            n += len(cols)
        if n < PAGE:
            break
        offset += PAGE
    return {"Data": {"row": list(merged.values())}}

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
