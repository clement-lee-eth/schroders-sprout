"""Build sprout.db from data snapshotted from the Glider production API on 1 Oct 2026.

Sources (in ./data):
  asset_info.json        POST /v2/assets/allocation-breakdown  (names, symbols, sectors)
  validate_results.json  POST /v2/strategies/validate per asset (usable vs blocklisted)
  discovery_all.json     GET  /v2/discovery/strategies          (public strategies)
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DB = ROOT / "sprout.db"

CHAINS = {
    56: ("BNB Chain", "eip155:56"),
    8453: ("Base", "eip155:8453"),
    1: ("Ethereum", "eip155:1"),
    42161: ("Arbitrum", "eip155:42161"),
}

# Settlement / cash assets checked individually with /v2/strategies/validate.
STABLES = {
    "eip155:56/erc20:0x55d398326f99059ff775485246999027b3197955": ("USDT", "Tether USD"),
    "eip155:56/erc20:0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": ("USDC", "USD Coin"),
    "eip155:8453/erc20:0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": ("USDC", "USD Coin"),
    "eip155:1/erc20:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", "USD Coin"),
}
ETFS = {"GLD", "SLV", "PPLT", "IBIT"}
RWA = {"USDY", "PAXG", "XAUT"}

SCHEMA = """
CREATE TABLE chains (chain_id INTEGER PRIMARY KEY, name TEXT, caip2 TEXT);
CREATE TABLE assets (
  caip_id TEXT PRIMARY KEY, chain_id INTEGER REFERENCES chains, symbol TEXT, token_symbol TEXT,
  name TEXT, issuer TEXT, asset_type TEXT, sector TEXT, usable INTEGER, note TEXT);
CREATE TABLE strategies (
  strategy_id TEXT PRIMARY KEY, name TEXT, description TEXT, chain_id INTEGER,
  tvl_usd REAL, portfolio_count INTEGER, source TEXT);
CREATE TABLE strategy_assets (strategy_id TEXT REFERENCES strategies, caip_id TEXT, weight TEXT);
CREATE TABLE portfolios (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, chain_id INTEGER, frequency TEXT,
  slippage_bps INTEGER, price_impact_bps INTEGER, threshold_usd TEXT,
  created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE portfolio_assets (portfolio_id INTEGER REFERENCES portfolios ON DELETE CASCADE, caip_id TEXT, weight TEXT);
"""


def chain_of(caip):
    return int(caip.split("/")[0].split(":")[1])


def classify(caip, symbol, info):
    chain = chain_of(caip)
    if caip in STABLES:
        return "Stablecoin", "Circle / Tether"
    if symbol in RWA:
        return "Tokenised RWA", "Ondo" if symbol == "USDY" else ("Paxos" if symbol == "PAXG" else "Tether")
    if chain == 56:
        return ("ETF / trust" if symbol in ETFS else "Equity"), "Ondo"
    if caip.startswith("eip155:8453/erc20:0xb200"):
        return "Equity", "Coinbase"
    if info.get("cryptoCategory") or not info.get("sector"):
        return "Crypto", "Native / protocol"
    return "Equity", "Other"


def main():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO chains VALUES (?,?,?)", [(k, v[0], v[1]) for k, v in CHAINS.items()])

    info = json.loads((DATA / "asset_info.json").read_text())
    valid = json.loads((DATA / "validate_results.json").read_text())

    rows = []
    for caip, sym_status in valid.items():
        status = sym_status[1]
        meta = info.get(caip, {})
        if caip in STABLES:
            symbol, name = STABLES[caip]
        else:
            symbol, name = meta.get("symbol"), meta.get("name")
        if not symbol or symbol == "?":
            continue  # unresolved by Glider; leave out of the mock
        atype, issuer = classify(caip, symbol, meta)
        token = symbol + ("on" if issuer == "Ondo" and atype != "Tokenised RWA" else "c" if issuer == "Coinbase" else "")
        sector = meta.get("sector") or meta.get("cryptoCategory") or ("Cash" if atype == "Stablecoin" else "")
        usable = 1 if status == "OK" else 0
        note = "" if usable else "Blocklisted by Glider (validate, 1 Oct 2026)"
        rows.append((caip, chain_of(caip), symbol, token, name, issuer, atype, sector, usable, note))
    con.executemany("INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

    for s in json.loads((DATA / "discovery_all.json").read_text()):
        assets = s["allocation"]["assets"]
        m = s.get("metrics") or {}
        con.execute(
            "INSERT INTO strategies VALUES (?,?,?,?,?,?,?)",
            (s["strategyId"], s["name"], s.get("description"), chain_of(assets[0]["assetId"]),
             float(m["tvlUsd"]) if m.get("tvlUsd") else None, m.get("portfolioCount"), "Glider public strategy"),
        )
        con.executemany("INSERT INTO strategy_assets VALUES (?,?,?)",
                        [(s["strategyId"], a["assetId"], a["weight"]) for a in assets])
    con.commit()
    n_assets = con.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    n_eq = con.execute("SELECT COUNT(*) FROM assets WHERE asset_type IN ('Equity','ETF / trust')").fetchone()[0]
    n_str = con.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]
    print(f"sprout.db built: {n_assets} assets ({n_eq} equities/ETFs), {n_str} public strategies")


if __name__ == "__main__":
    main()
