# SPROUT Lab

The local server behind the SPROUT prototype. For what SPROUT is and how to demo it, see the [main README](../README.md).

## Run

```bash
python3 server.py     # http://127.0.0.1:8765
python3 seed.py       # optional: rebuild sprout.db from data/ (deletes saved mock portfolios)
```

It needs only the Python 3 standard library. The server binds to `127.0.0.1`, so other machines can't reach it. Set `PORT` to use a different port.

## Pages

| Address | File | Purpose |
|---|---|---|
| `/` | `static/index.html` | Website |
| `/app` | `static/app.html` | Investor app |
| `/console` | `static/console.html` | Admin console. Add `?tour=1` to start the guided tour. |
| `/lab` | `static/lab.html` | Portfolio builder over the full asset catalogue |

`/go` and `/onboarding` are earlier versions that now redirect to `/`. Their files, `static/go.html` and `static/onboarding.html`, are no longer served.

## API

| Route | What it does |
|---|---|
| `GET /api/prices?symbols=MSFT,NVDA` | Live quotes for the underlying shares from Yahoo Finance, cached for 30 seconds |
| `GET /api/glider/live` | Read-only Glider snapshot, cached for 60 seconds. Never returns the key or the account email. |
| `GET /api/validation` | Summary of the saved goal strategy validation results |
| `GET /api/config` | Optional Privy app ID and any recorded strategy IDs |
| `GET /api/meta` | Chains, rebalance frequencies, and whether the Glider check is on |
| `GET /api/assets`, `GET /api/strategies` | Asset catalogue and public strategies from `sprout.db` |
| `POST /api/check` | Runs the local rules below on a portfolio |
| `POST /api/glider-validate` | Runs the local rules, then the Glider dry run `POST /v2/strategies/validate` |
| `GET` and `POST /api/portfolios`, `DELETE /api/portfolios/<id>` | List, save and delete mock portfolios in `sprout.db` |

POST routes accept only `application/json`. Mock portfolios stay in `sprout.db`, and the server never creates anything on Glider.

## Glider key

Put `GLIDER_API_KEY=...` in `.env.local` in the top folder of the repo to turn on the Glider snapshot and dry run. The file is ignored by git, so never force-add it.

## Portfolio rules

These match what the live Glider API accepted when tested:

- A portfolio holds 1 to 50 assets.
- Weights are above 0, have at most 2 decimals, and sum to exactly 100.
- All assets are on one chain, and none are blocklisted (NEE on BNB Chain).
- Schedules are interval-based, because cron isn't enabled for the account.
- Slippage and price impact are 0 to 1000 bps, and the minimum trade is at least $1.

## Files

- `data/` holds snapshots from the Glider production API and validation results. It contains no API key.
- `scripts/validate_goal_strategies.py` re-runs the dry run for every goal strategy. It needs the server running.
- `scripts/create_strategies.py` creates real strategies on Glider production, and Glider has no delete endpoint. Don't run it without approval. Its list of strategies predates the current range.
