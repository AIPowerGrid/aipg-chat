"use client";

import { getDefaultConfig } from "@rainbow-me/rainbowkit";
import { base, mainnet } from "wagmi/chains";
import { cookieStorage, createStorage } from "wagmi";

// Public WalletConnect client id (shared across AIPG properties; not a secret —
// it ships in the client bundle). Overridable via env.
const projectId =
  process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID ||
  "c5c31afe428becb9a80167e07ebb235e";

// Same wallet stack as the AIPG gallery: RainbowKit's multi-wallet modal
// (injected + WalletConnect + Coinbase). Base is the primary chain; mainnet is
// listed too so a wallet that connects on Ethereum mainnet doesn't trip wagmi's
// ChainMismatchError during the (chain-agnostic) SIWE signature — WalletSignIn
// best-effort switches to Base but login works from either chain. SIWE is handled
// separately against the grid-chat backend (/api/auth/wallet/nonce|verify).
export const config = getDefaultConfig({
  appName: "AI Power Grid",
  projectId,
  chains: [base, mainnet],
  ssr: true,
  storage: createStorage({ storage: cookieStorage }),
});
