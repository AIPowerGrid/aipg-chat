"use client";

import { useState } from "react";
import { Button } from "@opal/components";

// SIWE wallet login via the injected provider (MetaMask / any window.ethereum).
// No web3 library needed: request account -> sign the server's nonce message
// with personal_sign -> POST to the backend wallet router, which sets the
// session cookie. Backend: backend/onyx/auth/wallet.py (ENABLE_WALLET_LOGIN).
export default function WalletSignInButton({
  nextUrl,
}: {
  nextUrl?: string | null;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect() {
    setError(null);
    const eth =
      typeof window !== "undefined" ? (window as any).ethereum : null;
    if (!eth) {
      setError(
        "No Ethereum wallet found. Install MetaMask (or another wallet) and try again."
      );
      return;
    }
    setBusy(true);
    try {
      const accounts: string[] = await eth.request({
        method: "eth_requestAccounts",
      });
      const address = accounts?.[0];
      if (!address) throw new Error("No wallet account selected.");

      const nonceRes = await fetch("/api/auth/wallet/nonce", {
        method: "POST",
      });
      if (!nonceRes.ok) throw new Error("Could not start wallet login.");
      const { message } = await nonceRes.json();

      const signature: string = await eth.request({
        method: "personal_sign",
        params: [message, address],
      });

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
      // User rejecting the signature throws code 4001 — show a friendly note.
      setError(
        e?.code === 4001
          ? "Signature request was rejected."
          : e?.message || "Wallet login failed."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 w-full">
      <Button onClick={connect} disabled={busy}>
        {busy ? "Connecting…" : "Connect Wallet"}
      </Button>
      {error && (
        <p className="text-sm text-center text-red-500" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
