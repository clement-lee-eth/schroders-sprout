"""Dry-run every SPROUT goal strategy on Glider (validate only; nothing is created).

A goal strategy = purpose (Growth / Income / Sustainable) x risk level (1-5) x optional
themes add-on (levels 3-5 only, up to 2 themes), for model versions v1 and v2.
The allocation maths mirrors personal() in static/app.html. Run with the server up:
    python3 sprout-lab/scripts/validate_goal_strategies.py
Writes data/goal_strategy_validation.json.
"""
import itertools, json, math, os, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8765"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "goal_strategy_validation.json")

MODELS = {
    "quality": {1: {"MSFT": 18, "NVDA": 16, "AAPL": 14, "GOOGL": 14, "TSM": 14, "AMZN": 12, "LLY": 12},
                2: {"MSFT": 18, "NVDA": 16, "AAPL": 14, "GOOGL": 14, "TSM": 14, "AVGO": 12, "LLY": 12}},
    "income": {1: {"KO": 12, "PEP": 10, "MCD": 10, "WMT": 10, "COST": 8, "V": 8, "ABBV": 10, "MRK": 8, "SO": 8, "GLD": 6, "USDT": 10},
               2: {"KO": 12, "PEP": 10, "MCD": 10, "WMT": 10, "COST": 8, "V": 8, "ABBV": 10, "ABT": 8, "SO": 8, "GLD": 6, "USDT": 10}},
    "sustain": {1: {"MSFT": 14, "ASML": 12, "ETN": 12, "ISRG": 10, "NVO": 10, "V": 10, "COST": 10, "PWR": 8, "ABT": 8, "ENPH": 6},
                2: {"MSFT": 14, "ASML": 12, "ETN": 12, "ISRG": 10, "NVO": 10, "V": 10, "COST": 10, "PWR": 8, "ABT": 8, "GEV": 6}},
}
THEMES = {"ai": ["AVGO", "AMD", "MU", "ANET"], "health": ["NVO", "ISRG", "VRTX", "REGN"],
          "energy": ["CEG", "GEV", "ETN", "VST"], "brands": ["COST", "WMT", "KO", "PEP"]}
LEVELS = {1: (20, 10, 0), 2: (12, 6, 0), 3: (7, 0, 18), 4: (4, 0, 24), 5: (2, 0, 29)}  # cash, gold, theme sleeve


def personal(pid, ver, level, themes):
    base = MODELS[pid][ver]
    eq = {t: w for t, w in base.items() if t not in ("USDT", "GLD")}
    cash, gold, sleeve = LEVELS[level]
    sleeve = sleeve if themes else 0
    core_share = 100 - cash - gold - sleeve
    tot = sum(eq.values())
    w = {t: core_share * v / tot for t, v in eq.items()}
    items = [t for k in themes for t in THEMES[k]]
    for t in items:
        w[t] = w.get(t, 0) + sleeve / len(items)
    if gold:
        w["GLD"] = gold
    if cash:
        w["USDT"] = cash
    out = {t: math.floor(v * 100) / 100 for t, v in w.items()}
    k = max(out, key=out.get)
    out[k] = round(out[k] + 100 - sum(out.values()), 2)
    return out


def main():
    assets = json.load(urllib.request.urlopen(BASE + "/api/assets"))
    caip = {a["symbol"]: a["caip_id"] for a in assets if a["chain_id"] == 56}
    combos = []
    for pid in MODELS:
        for ver in (1, 2):
            for level in range(1, 6):
                opts = [()] + ([(k,) for k in THEMES] + list(itertools.combinations(THEMES, 2)) if level >= 3 else [])
                for th in opts:
                    combos.append((pid, ver, level, th))

    def run(c):
        pid, ver, level, th = c
        alloc = personal(pid, ver, level, list(th))
        missing = [t for t in alloc if t not in caip]
        if missing:
            return c, False, "no BNB token for " + ",".join(missing)
        body = {"name": f"SPROUT {pid} v{ver} L{level} {'+'.join(th) or 'core'}", "frequency": "daily",
                "slippage_bps": 100, "price_impact_bps": 100, "threshold_usd": "5.00",
                "allocation": [{"caip_id": caip[t], "weight": f"{w:.2f}", "symbol": t} for t, w in alloc.items()]}
        req = urllib.request.Request(BASE + "/api/glider-validate", data=json.dumps(body).encode(), headers={"content-type": "application/json"})
        try:
            j = json.load(urllib.request.urlopen(req, timeout=60))
            ok = bool(j.get("glider", {}).get("success"))
            return c, ok, "" if ok else json.dumps(j.get("glider") or j)[:200]
        except Exception as e:  # noqa: BLE001
            return c, False, str(e)[:200]

    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(run, combos))
    passed = sum(1 for _, ok, _ in res if ok)
    print(f"{passed}/{len(res)} goal strategies accepted by Glider")
    for c, ok, why in res:
        if not ok:
            print("FAIL", c, why)
    json.dump({"passed": passed, "total": len(res),
               "results": [{"pid": c[0], "version": c[1], "level": c[2], "themes": list(c[3]), "ok": ok, "error": why} for c, ok, why in res]},
              open(OUT, "w"), indent=1)


if __name__ == "__main__":
    main()
