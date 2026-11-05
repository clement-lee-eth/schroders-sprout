# Glider platform boundaries for SPROUT

Assessment date: 8 October 2026.

**Sources:**
- Glider OpenAPI 3.1 spec (41 operations) and the full developer docs.
- Live calls with the SPROUT production key (tenant "Schroders Test", all 10 scopes). Only reads and dry-run validation were used. Nothing was created.

**Legend:** ✅ verified live · 📄 documented, not yet exercised · ⚠️ limit or gap · ❌ not supported

## 1. Portfolios (strategies)

| Capability | Status | Detail |
|---|---|---|
| Custom Schroders portfolios | ✅ | Global Income (11 holdings), Quality 7 (7) and Future Leaders (9) all pass `POST /v2/strategies/validate`. |
| Assets available | ✅ | 177 of 178 tested assets are accepted: 143 Ondo stocks and ETFs on BNB Chain, 8 Coinbase stocks on Base, plus stablecoins and crypto. NextEra (NEE) is blocklisted. |
| Size and weights | ✅ | 1 to 50 assets per portfolio. Weights are percentages with up to two decimals and must sum to exactly 100. |
| One chain per portfolio | ⚠️ | Glider rejects mixed chains ("Allocation must use a single chain"). Ondo (BNB) and Coinbase (Base) need separate portfolios. |
| Model updates | 📄 | `POST /v2/strategies/{id}/versions`. Every enrolled portfolio moves to the new target at its next run. |
| Delete a strategy or portfolio | ❌ | There is no delete endpoint. Test records stay in the account permanently. |
| Different holdings for one investor's portfolio | ❌ | A portfolio mirrors its strategy exactly. Personalisation means separate strategies, for example 3 risk levels × 5 themes = 15. All 30 variants validated (15 × 2 model versions). |
| Strategies per account | ⚠️ | No documented limit. Confirm with Glider before creating one strategy per investor. |

## 2. Rebalancing

| Capability | Status | Detail |
|---|---|---|
| Automatic schedule | 📄 | Hourly, daily, weekly or monthly. Runs without anyone acting. |
| Market-hours scheduling (cron) | ⚠️ | Rejected for our account: "Cron strategy schedules are not enabled for this tenant". Ask Glider to enable it. |
| On-demand rebalance | 📄 | `POST /v2/portfolios/{id}/rebalance` returns `202` with an operation ID. A cooldown applies between manual triggers. |
| Tracking an operation | 📄 | States: `accepted → running → completed / failed / cancelled` (also `retrying`, `awaiting_user`). |
| Guardrails | ✅ | Slippage and price impact 0–1000 bps each. Minimum trade at least $1 (we use $5). Smaller trades are skipped, so portfolios under about $100 rebalance imprecisely. |
| Ondo market hours | ⚠️ | Ondo redemptions need an open US session. Requests outside it are accepted, then can fail with "market closed". |

## 3. Investors (enrolment, wallets, funding)

| Capability | Status | Detail |
|---|---|---|
| Two-stage enrolment | 📄 | `POST /v2/enroll/signature` returns a message for the investor to sign; `POST /v2/enroll` submits the signature and returns a portfolio and smart accounts. |
| Privy wallets | 📄 | Glider publishes a Privy tutorial: email login, an embedded wallet, then `personal_sign` on the stage-1 message. The API key stays on our backend. |
| Several portfolios per investor | 📄 | One portfolio per strategy per wallet. Enrolling the same wallet in the same strategy twice fails (`API_202`). |
| Funding | 📄 | A plain onchain transfer to the investor's smart account. There is no deposit endpoint. |
| Withdrawal | 📄 | Needs a fresh investor signature, valid 10 minutes. Same chain only, up to 10 assets, in kind or swapped to USDC/USDT. |
| Custody | 📄 | Glider never holds funds. Its session key can trade but cannot withdraw. |

## 4. Eligibility and risk assessment

| Capability | Status | Detail |
|---|---|---|
| KYC and eligibility | ❌ (by Glider) | Not provided. Glider's API terms make the distributing app responsible for blocking restricted jurisdictions. SPROUT must build this. |
| Risk profiling and suitability | ❌ (by Glider) | Not provided. SPROUT owns the questionnaire, scoring and the record of each decision. |
| Rules we used | ⚠️ | Ondo's published eligibility. US and Canada are prohibited. UK, EEA, Switzerland, Hong Kong, Singapore, Malaysia and Brazil are professional or qualified investors only. Coinbase stocks are Reg S, non-US, and reportedly not available in the UK. Needs Schroders compliance sign-off. |

## 5. Distribution and data

| Capability | Status | Detail |
|---|---|---|
| Partners offering Schroders portfolios | 📄 | Public strategies (`isPublic: true`) can be enrolled into by any Glider account using the strategy ID. Each partner needs its own Glider integration. |
| Schroders seeing partners' investors | ❌ | Not through the standard API. Strategy records carry no AUM or investor count. Ask Glider about the opt-in Campaigns endpoint or agreed reporting. |
| Platform data | ✅ | Live discovery data: 31 public strategies; Bitwise Mag7X with about 2,000 wallets and $1.0m. |
| Rate limit | ✅ | 1,000 requests per window (resets about every 60 s). |

## 6. Economics

| Item | Status | Detail |
|---|---|---|
| Glider trading fee | 📄 | Taken automatically inside each portfolio: 0.30% of traded volume in Bitwise's ATPs. Glider pays network fees. |
| Distributor fee | ✅ | `swapBps` 30–300 per account or strategy. Currently unset (Glider default). |
| Schroders model fee (0.15%) | ⚠️ | Not available in the API. Needs a licensing agreement with Glider, as Bitwise has. The published fee split (`glider.fi/api-pricing`) currently returns 404. |

## 7. Environments

| Item | Status | Detail |
|---|---|---|
| Production | ✅ | `api.glider.fi/v2`. This is mainnet, so funding means real money. |
| Staging | ⚠️ | `staging-api.glider.fi/v2` exists, but our key doesn't work there. Request a key from `developers@glider.fi`. |

## What the /go prototype does today

| Step | Real or simulated |
|---|---|
| Privy email login | Simulated (no Privy app ID yet). Real code paths are shown under the hood. |
| Wallet key and signature | **Real.** Generated and signed in the browser with ethers, standing in for Privy's embedded wallet. |
| Eligibility and risk profile | Real logic, illustrative rules |
| The three Schroders portfolios | **Validated live** on Glider each time an investor reaches the amount screen |
| Token quantities and values | **Live share prices** (underlying US shares) |
| Enrolment, funding, rebalancing | Simulated using Glider's documented requests and responses |

**To make the simulated steps real:**
1. Create the three strategies. This needs production-write approval and creates permanent records.
2. Add a Privy app ID.
3. Enrol a test wallet.
4. Fund two wallets with $100–300 each, after compliance sign-off.
5. Watch a real daily run.
