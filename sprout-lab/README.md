# SPROUT Lab

Confidential local mock for composing portfolios from the tokenised equities available on Glider.

```bash
cd sprout-lab
python3 seed.py     # rebuild sprout.db from ./data (resets saved mock portfolios)
python3 server.py   # http://127.0.0.1:8765
```

- `/` is the C-suite landing page. Sections in order:
  1. Hero
  2. How it works
  3. Model cards
  4. **What you get**: interactive flow from deposit → Schroders core / personal sleeve / cash → tokens, with live prices
  5. **Scale**: animated network of wallets with publish, daily-run and add-partner controls
  6. Digital investors
  7. Distribution
  8. The unlock
  9. Live proof wallet
  10. **Can we build it?**: what's proven on Glider vs what's needed
  11. FAQ
- The earlier single-model view, "Schroders Quality 7":
  - **Investor view:** a $10,000 mock position funded at closing prices about a month ago, live prices, current vs target allocation, and daily automatic rebalancing (with a demo fast-forward).
  - **Schroders view:** illustrative distribution across channels, fee income, and publishing a model update to every wallet.
  - **The unlock:** a comparison of a fund today with the same model on SPROUT.
- `/console` is the earlier three-client console.
- `/api/glider/live` is a read-only snapshot from Glider production, cached 60 s: connection status, our strategy and portfolio counts, public strategies, and Bitwise Mag7X wallets and AUM. It never returns the key or the account email. The key is read from `../.env.local`.
- `/api/prices?symbols=MSFT,NVDA` serves live quotes from Yahoo Finance (cached 30 s). These are prices of the underlying shares.
- `/onboarding` is the earlier first-time investor flow. `/lab` is the internal builder over the full asset catalogue.
- The manager name is the `MANAGER` constant at the top of the script in `static/index.html`.
- Python 3 standard library only. Binds to 127.0.0.1, so it isn't reachable from other machines.
- `data/` holds read-only snapshots from the Glider production API (1 Oct 2026): asset metadata, per-asset validation results and public strategies. It contains no API key.
- Mock portfolios are saved to `sprout.db` only. Nothing is created on Glider.
- Optional: put `GLIDER_API_KEY=...` in `../.env.local` to enable **Check with Glider**. It calls only the dry-run `POST /v2/strategies/validate`.

Rules enforced, matching the live API:
- 1–50 assets.
- Weights above 0 with at most 2 decimals, summing to exactly 100.
- One chain per strategy. No blocklisted assets (NEE on BNB).
- Interval schedules only, because cron is not enabled for the tenant.
- Slippage and price impact 0–1000 bps. Minimum trade at least $1.
