"""SPROUT Lab: local mock of what can be built on Glider. Standard library only.

Run:  python3 seed.py && python3 server.py   ->  http://127.0.0.1:8765
Mock portfolios are saved to the local sprout.db only; nothing is created on Glider.
If GLIDER_API_KEY is set (env or ../.env.local), "Check with Glider" runs the
read-only dry run POST /v2/strategies/validate. No other Glider endpoint is called.
"""
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "sprout.db"
PORT = int(os.environ.get("PORT", "8765"))
GLIDER = "https://api.glider.fi/v2"
FREQUENCIES = ("hourly", "daily", "weekly", "monthly")
WEIGHT_RE = re.compile(r"^\d+(\.\d{1,2})?$")


def load_key():
    if os.environ.get("GLIDER_API_KEY"):
        return os.environ["GLIDER_API_KEY"].strip()
    env = ROOT.parent / ".env.local"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GLIDER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return None


PRICE_TTL = 300  # daily closes; the live price comes from live_quotes()
LIVE_TTL = 8
_quote_cache = {}
_price_cache = {}
_price_lock = threading.Lock()
SYMBOL_RE = re.compile(r"^[A-Z.\-]{1,10}$")


def fetch_price(symbol):
    """Live quote and one month of daily closes for a US-listed share (Yahoo Finance chart API)."""
    with _price_lock:
        hit = _price_cache.get(symbol)
        if hit and time.time() - hit[0] < PRICE_TTL:
            return hit[1]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1mo&interval=1d"
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0 (sprout-lab)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.load(r)["chart"]["result"][0]
        meta, q = res["meta"], res["indicators"]["quote"][0]
        closes = [{"t": t, "c": round(c, 4)} for t, c in zip(res.get("timestamp") or [], q.get("close") or []) if c is not None]
        period = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
        out = {
            "symbol": symbol, "price": meta.get("regularMarketPrice"),
            "prevClose": meta.get("chartPreviousClose") if len(closes) < 2 else closes[-2]["c"],
            "time": meta.get("regularMarketTime"), "currency": meta.get("currency"),
            "marketOpen": bool(period) and period.get("start", 0) <= time.time() <= period.get("end", 0),
            "closes": closes, "source": "Yahoo Finance",
        }
    except Exception as e:  # keep the last good quote if the feed hiccups
        with _price_lock:
            hit = _price_cache.get(symbol)
        return hit[1] if hit else {"symbol": symbol, "error": str(e)[:120]}
    with _price_lock:
        _price_cache[symbol] = (time.time(), out)
    return out


def _session(meta, now):
    """Which US session is trading now: pre, regular, post, overnight (24/5 onchain) or weekend."""
    period = meta.get("currentTradingPeriod") or {}
    for k in ("pre", "regular", "post"):
        w = period.get(k) or {}
        if w.get("start", 0) <= now < w.get("end", 0):
            return k
    et = time.gmtime(now + (period.get("regular") or {}).get("gmtoffset", -14400))
    if et.tm_wday == 5 or (et.tm_wday == 4 and et.tm_hour >= 20) or (et.tm_wday == 6 and et.tm_hour < 20):
        return "weekend"
    return "overnight"


def _spark(chunk):
    """Latest trade including pre-market and after-hours, for up to 20 symbols in one call."""
    url = "https://query1.finance.yahoo.com/v7/finance/spark?" + urllib.parse.urlencode(
        {"symbols": ",".join(chunk), "range": "1d", "interval": "1m", "includePrePost": "true"})
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0 (sprout-lab)"})
    out, now = {}, time.time()
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            res = json.load(r)["spark"]["result"]
    except Exception:
        return out
    for item in res:
        try:
            x = item["response"][0]
            meta, ts, cl = x["meta"], x.get("timestamp") or [], x["indicators"]["quote"][0]["close"]
            last = [(t, c) for t, c in zip(ts, cl) if c is not None]
            t, c = last[-1] if last else (meta.get("regularMarketTime"), meta.get("regularMarketPrice"))
            out[item["symbol"]] = {"price": round(c, 4), "t": t, "session": _session(meta, now),
                                   "regularPrice": meta.get("regularMarketPrice"), "prevClose": meta.get("chartPreviousClose")}
        except Exception:
            continue
    return out


def live_quotes(symbols):
    now = time.time()
    with _price_lock:
        stale = [s for s in symbols if now - _quote_cache.get(s, (0, None))[0] > LIVE_TTL]
    if stale:
        chunks = [stale[i:i + 20] for i in range(0, len(stale), 20)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for got in pool.map(_spark, chunks):
                with _price_lock:
                    for k, v in got.items():
                        _quote_cache[k] = (now, v)
    with _price_lock:
        return {s: _quote_cache[s][1] for s in symbols if s in _quote_cache}


def prices(symbols):
    symbols = [s for s in dict.fromkeys(symbols) if SYMBOL_RE.match(s)][:80]
    with ThreadPoolExecutor(max_workers=12) as pool:
        out = {p["symbol"]: p for p in pool.map(fetch_price, symbols)}
    for sym, q in live_quotes(symbols).items():
        p = out.get(sym)
        if not p or not p.get("price"):
            continue
        p.update({"price": q["price"], "liveAt": q["t"], "session": q["session"], "regularPrice": q["regularPrice"]})
        if q.get("prevClose"):
            p["prevClose"] = q["prevClose"]
        p["marketOpen"] = q["session"] == "regular"
    return out


_live_cache = {"t": 0, "data": None}


def glider_get(path, key):
    req = urllib.request.Request(f"{GLIDER}{path}", headers={"x-api-key": key, "user-agent": "sprout-lab/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def glider_live():
    """Read-only snapshot of real Glider data for the landing page. Never returns the key or tenant email."""
    if _live_cache["data"] and time.time() - _live_cache["t"] < 60:
        return _live_cache["data"]
    key = load_key()
    out = {"connected": False, "asOf": time.time()}
    if not key:
        out["message"] = "No GLIDER_API_KEY configured."
        return out
    try:
        who = glider_get("/whoami", key)["data"]
        mine = glider_get("/strategies", key)["data"]["strategies"]
        ports = glider_get("/portfolios", key)["data"]["portfolios"]
        top = glider_get("/discovery/strategies?collection=top_performing&sort=tvl.desc&limit=50", key)["data"]
        cur = glider_get("/discovery/strategies?collection=curated&limit=50", key)["data"]
        public = {s["strategyId"]: s for s in (top if isinstance(top, list) else top.get("strategies", []))}
        public.update({s["strategyId"]: s for s in (cur if isinstance(cur, list) else cur.get("strategies", []))})
        rows = []
        for s in public.values():
            m = s.get("metrics") or {}
            rows.append({"name": s["name"], "tvlUsd": float(m["tvlUsd"]) if m.get("tvlUsd") else None,
                         "portfolios": m.get("portfolioCount"), "assets": len(s["allocation"]["assets"])})
        rows.sort(key=lambda r: r["tvlUsd"] or 0, reverse=True)
        out.update({
            "connected": True, "scopes": len(who.get("scopes", [])),
            "ourStrategies": len(mine), "ourPublic": sum(1 for s in mine if s.get("isPublic")),
            "ourPortfolios": len(ports),
            "publicStrategies": len(rows),
            "publicTvlUsd": sum(r["tvlUsd"] or 0 for r in rows),
            "publicPortfolios": sum(r["portfolios"] or 0 for r in rows),
            "bitwise": next((r for r in rows if "bitwise" in r["name"].lower()), None),
            "top": rows[:5],
        })
    except Exception as e:
        out["message"] = f"Glider unavailable: {str(e)[:100]}"
    _live_cache.update(t=time.time(), data=out)
    return out


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def rows(sql, args=()):
    with db() as con:
        return [dict(r) for r in con.execute(sql, args)]


def check(body):
    """Apply the strategy rules Glider enforces (from the OpenAPI spec and live validate tests)."""
    errors = []
    raw_name, alloc = body.get("name"), body.get("allocation") or []
    if not isinstance(raw_name, (str, type(None))) or not isinstance(alloc, list) or not all(isinstance(a, dict) for a in alloc):
        return ["Name must be text and allocation a list of assets."], None, None
    name = (raw_name or "").strip()
    if not 1 <= len(name) <= 256:
        errors.append("Name must be 1–256 characters.")
    if not 1 <= len(alloc) <= 50:
        errors.append("A strategy holds between 1 and 50 assets.")
    ids = [str(a.get("caip_id")) for a in alloc]
    if len(set(ids)) != len(ids):
        errors.append("Each asset can appear only once.")
    total = Decimal(0)
    for a in alloc:
        w = str(a.get("weight", "")).strip()
        try:
            ok = bool(WEIGHT_RE.match(w)) and Decimal(w) > 0
        except InvalidOperation:
            ok = False
        if not ok:
            errors.append(f"Weight for {a.get('symbol', a.get('caip_id'))} must be above 0 with at most 2 decimals.")
        else:
            total += Decimal(w)
    if alloc and total != 100:
        errors.append(f"Weights must sum to exactly 100 (currently {total}).")
    known = {r["caip_id"]: r for r in rows(
        f"SELECT caip_id, chain_id, symbol, usable FROM assets WHERE caip_id IN ({','.join('?' * len(ids)) or 'NULL'})", ids)}
    chains = {known[i]["chain_id"] for i in ids if i in known}
    if len(chains) > 1:
        errors.append("Allocation must use a single chain. Glider rejects mixed-chain strategies.")
    for i in ids:
        if i not in known:
            errors.append(f"Unknown asset {i}.")
        elif not known[i]["usable"]:
            errors.append(f"{known[i]['symbol']} is blocklisted by Glider and cannot be used.")
    freq = body.get("frequency", "daily")
    if freq not in FREQUENCIES:
        errors.append("Schedule must be hourly, daily, weekly or monthly. Cron schedules are not enabled for our tenant.")
    for k, lo, hi in (("slippage_bps", 0, 1000), ("price_impact_bps", 0, 1000)):
        v = body.get(k)
        if not isinstance(v, int) or not lo <= v <= hi:
            errors.append(f"{k.replace('_', ' ')} must be a whole number from {lo} to {hi}.")
    try:
        if Decimal(str(body.get("threshold_usd", "5"))) < 1:
            errors.append("Minimum trade size must be at least $1.00.")
    except InvalidOperation:
        errors.append("Minimum trade size must be a number.")
    payload = {
        "name": name,
        "description": (body.get("description") or None),
        "allocation": {"assets": [{"assetId": a.get("caip_id"), "weight": str(a.get("weight"))} for a in alloc]},
        "schedule": {"type": "interval", "frequency": freq},
        "preferences": {"swap": {"slippageBps": body.get("slippage_bps"), "priceImpactBps": body.get("price_impact_bps"),
                                 "thresholdUsd": str(body.get("threshold_usd", "5.00"))}},
        "isPublic": False,
    }
    return errors, payload, (chains.pop() if len(chains) == 1 else None)


def glider_validate(payload):
    key = load_key()
    if not key:
        return 503, {"available": False, "message": "No GLIDER_API_KEY set. Add it to .env.local to enable the live dry run."}
    req = urllib.request.Request(
        f"{GLIDER}/strategies/validate", data=json.dumps(payload).encode(), method="POST",
        headers={"x-api-key": key, "content-type": "application/json", "user-agent": "sprout-lab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200, {"available": True, "glider": json.load(r)}
    except urllib.error.HTTPError as e:
        try:
            return 200, {"available": True, "glider": json.load(e)}
        except Exception:
            return 502, {"available": True, "message": f"Glider returned HTTP {e.code}."}
    except urllib.error.URLError as e:
        return 502, {"available": True, "message": f"Could not reach Glider: {e.reason}"}


class Handler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser left (reload or navigation) before the answer arrived; nothing to send it to

    def send_json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        # Only a JSON object counts: anything else (bad length, invalid UTF-8, an array) is a 400, not a dropped connection.
        try:
            n = int(self.headers.get("content-length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, UnicodeDecodeError):
            return None
        return body if isinstance(body, dict) else None

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/api/config":
            cfg = {"privyAppId": None, "strategies": {}}
            env = ROOT.parent / ".env.local"
            if env.exists():
                for line in env.read_text().splitlines():
                    if line.startswith("PRIVY_APP_ID="):
                        cfg["privyAppId"] = line.split("=", 1)[1].strip().strip('"') or None
            created = ROOT / "data" / "created_strategies.json"
            if created.exists():
                cfg["strategies"] = json.loads(created.read_text())
            return self.send_json(200, cfg)
        if path == "/api/validation":
            f = ROOT / "data" / "goal_strategy_validation.json"
            if not f.exists():
                return self.send_json(404, {"error": "run scripts/validate_goal_strategies.py"})
            d = json.loads(f.read_text())
            return self.send_json(200, {"passed": d["passed"], "total": d["total"], "checkedAt": int(f.stat().st_mtime)})
        if path.startswith("/brand/"):  # official brand files dropped into static/brand/ (e.g. the Schroders logo)
            name = path[len("/brand/"):]
            f = ROOT / "static" / "brand" / name
            if "/" in name or ".." in name or not f.is_file():
                return self.send_json(404, {"error": "not found"})
            ext = f.suffix.lower()
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("content-type", {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext, "application/octet-stream"))
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path in ("/manifest.webmanifest", "/icon.svg", "/sim.css", "/nav.js", "/live.js", "/favicon.ico"):
            if path == "/favicon.ico":  # browsers ask for this by default; serve the same SVG icon
                path = "/icon.svg"
            f = ROOT / "static" / path.lstrip("/")
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "application/manifest+json" if path.endswith("webmanifest") else "text/css" if path.endswith(".css") else "application/javascript" if path.endswith(".js") else "image/svg+xml")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/glider/live":
            return self.send_json(200, glider_live())
        if path == "/api/prices":
            syms = urllib.parse.parse_qs(query).get("symbols", [""])[0].upper().split(",")
            return self.send_json(200, {"asOf": time.time(), "prices": prices(syms)})
        if path in ("/index.html", "/go", "/onboarding"):  # superseded entry points: the landing page lives at /
            self.send_response(302); self.send_header("location", "/"); self.end_headers(); return
        pages = {"/": "index.html", "/lab": "lab.html", "/onboarding": "onboarding.html", "/console": "console.html", "/go": "go.html", "/app": "app.html", "/brief": "index.html"}
        if path in pages:
            data = (ROOT / "static" / pages[path]).read_bytes()
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/meta":
            self.send_json(200, {
                "chains": rows("SELECT * FROM chains ORDER BY CASE chain_id WHEN 56 THEN 0 WHEN 8453 THEN 1 WHEN 1 THEN 2 ELSE 3 END"),
                "frequencies": FREQUENCIES,
                "gliderCheck": bool(load_key()),
            })
        elif path == "/api/assets":
            self.send_json(200, rows("SELECT * FROM assets ORDER BY chain_id, asset_type, symbol"))
        elif path == "/api/strategies":
            out = rows("SELECT * FROM strategies ORDER BY tvl_usd DESC")
            alloc = rows("SELECT * FROM strategy_assets")
            for s in out:
                s["allocation"] = [a for a in alloc if a["strategy_id"] == s["strategy_id"]]
            self.send_json(200, out)
        elif path == "/api/portfolios":
            out = rows("SELECT * FROM portfolios ORDER BY id DESC")
            alloc = rows("SELECT pa.*, a.symbol FROM portfolio_assets pa JOIN assets a USING (caip_id)")
            for p in out:
                p["allocation"] = [a for a in alloc if a["portfolio_id"] == p["id"]]
            self.send_json(200, out)
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        # A JSON content type forces a CORS preflight, so other websites can't post here from the user's browser.
        if (self.headers.get("content-type") or "").split(";")[0].strip().lower() != "application/json":
            return self.send_json(415, {"error": "Send JSON with content-type application/json."})
        body = self.read_json()
        if body is None:
            return self.send_json(400, {"error": "Request body must be JSON."})
        if self.path == "/api/check":
            errors, payload, chain = check(body)
            return self.send_json(200, {"valid": not errors, "errors": errors, "payload": payload, "chain_id": chain})
        if self.path == "/api/glider-validate":
            errors, payload, _ = check(body)
            if errors:
                return self.send_json(200, {"available": True, "glider": None, "message": "Fix the local rule errors first."})
            code, res = glider_validate(payload)
            return self.send_json(code, res)
        if self.path == "/api/portfolios":
            errors, payload, chain = check(body)
            if errors:
                return self.send_json(400, {"errors": errors})
            with db() as con:
                cur = con.execute(
                    "INSERT INTO portfolios (name, chain_id, frequency, slippage_bps, price_impact_bps, threshold_usd) VALUES (?,?,?,?,?,?)",
                    (payload["name"], chain, payload["schedule"]["frequency"], body["slippage_bps"], body["price_impact_bps"],
                     payload["preferences"]["swap"]["thresholdUsd"]))
                con.executemany("INSERT INTO portfolio_assets VALUES (?,?,?)",
                                [(cur.lastrowid, a["caip_id"], str(a["weight"])) for a in body["allocation"]])
            return self.send_json(201, {"id": cur.lastrowid})
        self.send_json(404, {"error": "Not found"})

    def do_DELETE(self):
        m = re.fullmatch(r"/api/portfolios/(\d+)", self.path)
        if not m:
            return self.send_json(404, {"error": "Not found"})
        with db() as con:
            con.execute("DELETE FROM portfolios WHERE id = ?", (int(m.group(1)),))
        self.send_json(200, {"deleted": int(m.group(1))})


if __name__ == "__main__":
    if not DB.exists():
        raise SystemExit("sprout.db not found. Run: python3 seed.py")
    print(f"SPROUT Lab on http://127.0.0.1:{PORT}  (Glider dry-run check: {'on' if load_key() else 'off'})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
