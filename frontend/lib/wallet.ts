"use client";

import { useCallback, useEffect, useState } from "react";
import { readWallet } from "./api";
import { addDays } from "./datetime";
import { WalletBalances, WalletStatus } from "./types";

export type WalletLoad = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: WalletStatus };

export const formatMoney = (cents: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);

/** "123.45" for prefilling dollar inputs. */
export const centsToInput = (cents: number) => (cents / 100).toFixed(2);

/** First forecast day for saved balances: the as-of day for wallet saves, the next day for older check-ins. */
export function forecastStartFor(balances: WalletBalances): string {
  return balances.source === "wallet" ? balances.effective_date : addDays(balances.effective_date, 1);
}

export function describeAge(days: number | null): string {
  if (days === null) return "";
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  return `${days} days ago`;
}

/** Loads the signed-in student's latest wallet balances, history, and warning amounts. */
export function useWallet(): [WalletLoad, () => Promise<void>] {
  const [wallet, setWallet] = useState<WalletLoad>({ status: "loading" });
  const reload = useCallback(async () => {
    try {
      setWallet({ status: "ready", data: await readWallet() });
    } catch (error) {
      setWallet({ status: "error", message: error instanceof Error ? error.message : "Unable to load your wallet balances." });
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return [wallet, reload];
}
