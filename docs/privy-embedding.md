# Embedding Privy in SPROUT

## What Privy offers

- **Pre-built login modal:** React only (`@privy-io/react-auth`). You call `login()` and Privy shows its own modal with email, Google, Apple and wallet sign-in.
- **Headless SDK:** `useLoginWithEmail` in React, or `@privy-io/js-sdk-core` without React. It handles the logic, but you build the screens yourself.
- **Embedded wallet:** created automatically at login with `embeddedWallets.ethereum.createOnLogin: 'users-without-wallets'`. There is no seed phrase. The user recovers access through their login.
- **Silent signing:** `showWalletUIs: false` hides Privy's confirmation pop-ups. The approval happens in SPROUT's own interface, with one tap on "Approve autopilot".

## How `/go` uses it

| Situation | What the app does |
|---|---|
| No Privy App ID (today) | A Privy-style modal: email → code → "Setting up your secure wallet" → done. The code fills itself in, so the C-suite demo flows without anyone checking an inbox. A real wallet key is generated in the browser and used to sign. |
| `PRIVY_APP_ID` set in `.env.local` | The app loads Privy's real React modal at runtime, from esm.sh, as a small "island" inside the plain HTML page. "Get started" opens Privy's own modal. The embedded wallet signs the autopilot approval silently. |

Settings used for the real modal:

```js
loginMethods: ["email", "google", "apple"],
appearance: { theme: "light", accentColor: "#12824f", landingHeader: "Sign in to SPROUT", walletChainType: "ethereum-only" },
embeddedWallets: { ethereum: { createOnLogin: "users-without-wallets" }, showWalletUIs: false }
```

## Switching on real Privy (about 10 minutes)

1. Create an app at dashboard.privy.io and copy its **App ID**.
2. In the dashboard:
   - Turn on the **Email**, **Google** and **Apple** login methods.
   - Add `http://127.0.0.1:8765` and `http://localhost:8765` as **allowed origins**.
   - Upload the SPROUT logo if you want it in the modal.
3. Add the ID to `.env.local` at the project root:
   ```
   PRIVY_APP_ID=your-app-id
   ```
4. Restart the server. `/api/config` will now return the ID, and the app will use Privy's real modal.

The real-Privy path hasn't been tested yet, because it needs an App ID. Expect one round of tuning: the esm.sh import, and config key names, which vary between Privy SDK versions.

## For production, beyond the demo

- **Build SPROUT as a React or Next.js app** with Privy installed from npm, rather than loading it from a CDN at runtime.
- **Verify Privy's access token on the backend** before calling Glider. Keep the Glider API key server-side only.
- **Wallet type:** Privy's embedded wallet is a standard (ECDSA) wallet, so Glider enrolment uses `accountType: "ECDSA"` and supports several chains in one enrolment. Privy *smart* wallets would need `ERC1271`, which allows only one chain per enrolment.
- **Funding:** Privy's on-ramp (card or bank → USDT/USDC) can fund the investor's Glider smart account directly. That's worth evaluating for first-time investors.
