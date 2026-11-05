"""Create the three Schroders portfolios as private strategies on Glider production.

Usage:
    python3 sprout-lab/scripts/create_strategies.py            # dry run: validate only, creates nothing
    python3 sprout-lab/scripts/create_strategies.py --create   # validate, then create (permanent; no delete endpoint)

Reads GLIDER_API_KEY from .env.local at the project root. Writes the created strategy IDs to
sprout-lab/data/created_strategies.json, which the /go app reads to show real IDs.
Skips any portfolio that already exists in the account under the same name.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "sprout-lab"
API = "https://api.glider.fi/v2"
USDT_BNB = "eip155:56/erc20:0x55d398326f99059ff775485246999027b3197955"

PORTFOLIOS = [
    ("Schroders Global Income", "Cautious. Dividend leaders, gold and a cash buffer. SPROUT pilot, private.",
     {"KO": 12, "PEP": 10, "MCD": 10, "WMT": 10, "COST": 8, "V": 8, "ABBV": 10, "MRK": 8, "SO": 8, "GLD": 6, "USDT": 10}),
    ("Schroders Quality 7", "Balanced. Seven global leaders weighted by conviction. SPROUT pilot, private.",
     {"MSFT": 18, "NVDA": 16, "AAPL": 14, "GOOGL": 14, "TSM": 14, "AMZN": 12, "LLY": 12}),
    ("Schroders Future Leaders", "Adventurous. AI, chips, cybersecurity and power. SPROUT pilot, private.",
     {"NVDA": 16, "AVGO": 14, "TSM": 12, "ASML": 10, "AMD": 10, "PLTR": 10, "CRWD": 10, "ISRG": 9, "CEG": 9}),
]


def key():
    for line in (ROOT / ".env.local").read_text().splitlines():
        if line.startswith("GLIDER_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("GLIDER_API_KEY not found in .env.local")


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"x-api-key": KEY, "content-type": "application/json", "user-agent": "sprout-lab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


KEY = key()
create = "--create" in sys.argv
info = json.loads((LAB / "data" / "asset_info.json").read_text())
ids = {v["symbol"]: k for k, v in info.items() if k.startswith("eip155:56/") and v.get("symbol")}
ids["USDT"] = USDT_BNB
existing = {s["name"]: s for s in call("GET", "/strategies")["data"]["strategies"]}
out = {}

for name, desc, weights in PORTFOLIOS:
    if name in existing:
        print(f"= {name}: already exists ({existing[name]['strategyId']})")
        out[name] = existing[name]["strategyId"]
        continue
    body = {"name": name, "description": desc,
            "allocation": {"assets": [{"assetId": ids[t], "weight": str(w)} for t, w in weights.items()]},
            "schedule": {"type": "interval", "frequency": "daily"},
            "preferences": {"swap": {"slippageBps": 100, "priceImpactBps": 100, "thresholdUsd": "5.00"}},
            "isPublic": False}
    v = call("POST", "/strategies/validate", body)
    if not v.get("success"):
        print(f"✗ {name}: rejected by validation: {v.get('error')}")
        continue
    if not create:
        print(f"✓ {name}: valid (dry run, not created)")
        continue
    r = call("POST", "/strategies", body)
    if r.get("success"):
        sid = r["data"]["strategyId"]
        out[name] = sid
        print(f"+ {name}: created {sid}")
    else:
        print(f"✗ {name}: create failed: {r.get('error')}")

if out:
    (LAB / "data" / "created_strategies.json").write_text(json.dumps(out, indent=2))
    print("Saved IDs to sprout-lab/data/created_strategies.json")
if not create:
    print("\nDry run only. Re-run with --create to create the strategies (permanent).")
