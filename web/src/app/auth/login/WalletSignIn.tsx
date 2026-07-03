"use client";

import "@rainbow-me/rainbowkit/styles.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  WagmiProvider,
  useAccount,
  useSignMessage,
  useSwitchChain,
} from "wagmi";
import { base } from "wagmi/chains";
import {
  RainbowKitProvider,
  darkTheme,
  ConnectButton,
} from "@rainbow-me/rainbowkit";
import { useEffect, useRef, useState } from "react";
import { config } from "@/lib/wallet/wagmi";

const queryClient = new QueryClient();

// Once a wallet connects (via RainbowKit's multi-wallet modal), run SIWE against
// the grid-chat backend: fetch the server-built nonce message, sign it, verify.
// Verify sets the session cookie, then we land in the app. Same backend the old
// button used — only the connect/sign UX changed.
function WalletAuth({ nextUrl }: { nextUrl?: string | null }) {
  const { isConnected, address, chainId } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const { switchChainAsync } = useSwitchChain();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const attempted = useRef(false);

  useEffect(() => {
    if (!isConnected || !address || attempted.current) return;
    attempted.current = true;

    (async () => {
      setBusy(true);
      setError(null);
      try {
        // SIWE is chain-agnostic, but wagmi throws a ChainMismatchError if the
        // wallet's current chain isn't the one the connection expects. Best-effort
        // nudge the wallet to Base; if the user declines we still sign on their
        // current chain (mainnet is in the supported list), so login never hard-
        // fails on chain. This mirrors the gallery's auto-switch-to-Base.
        if (chainId && chainId !== base.id) {
          try {
            await switchChainAsync({ chainId: base.id });
          } catch {
            // user declined / wallet can't switch — proceed to sign anyway
          }
        }

        const nonceRes = await fetch("/api/auth/wallet/nonce", {
          method: "POST",
        });
        if (!nonceRes.ok) throw new Error("Could not start wallet login.");
        const { message } = await nonceRes.json();

        const signature = await signMessageAsync({ message });

        const verifyRes = await fetch("/api/auth/wallet/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, signature, address }),
        });
        if (!verifyRes.ok) {
          const detail = await verifyRes
            .json()
            .then((d) => d?.detail)
            .catch(() => null);
          throw new Error(detail || "Wallet verification failed.");
        }

        window.location.href = nextUrl || "/app";
      } catch (e: any) {
        attempted.current = false; // allow another attempt
        const rejected =
          e?.code === 4001 ||
          (typeof e?.message === "string" &&
            e.message.toLowerCase().includes("reject"));
        setError(
          rejected
            ? "Signature request was rejected."
            : e?.message || "Wallet login failed."
        );
      } finally {
        setBusy(false);
      }
    })();
  }, [isConnected, address, chainId, signMessageAsync, switchChainAsync, nextUrl]);

  return (
    <div className="flex flex-col items-center gap-2 w-full">
      <ConnectButton
        showBalance={false}
        chainStatus="none"
        accountStatus="address"
      />
      {busy && <p className="text-sm text-text-03">Signing you in…</p>}
      {error && (
        <p className="text-sm text-center text-red-500" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export default function WalletSignIn({
  nextUrl,
}: {
  nextUrl?: string | null;
}) {
  return (
    // reconnectOnMount=false: the login page must ALWAYS start disconnected so
    // the RainbowKit "Connect Wallet" button + multi-wallet chooser is shown.
    // With the default (true), wagmi silently restores the last-used injected
    // wallet (MetaMask) on load, WalletAuth's effect then auto-fires SIWE, and
    // the user gets a bare MetaMask signature popup — never the wallet picker.
    <WagmiProvider config={config} reconnectOnMount={false}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider
          modalSize="compact"
          theme={darkTheme({
            accentColor: "#f8991d", // AIPG orange
            accentColorForeground: "white",
            borderRadius: "medium",
            fontStack: "system",
          })}
        >
          <WalletAuth nextUrl={nextUrl} />
        </RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
