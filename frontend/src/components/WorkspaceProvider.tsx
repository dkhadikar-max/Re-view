"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import type { Property } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

type WorkspaceValue = {
  property: Property | null;
  propertyName: string | null;
  /** ISO 4217 workspace currency from the hotel country */
  currency: string;
  money: (amount: number, currencyOverride?: string) => string;
};

const WorkspaceContext = createContext<WorkspaceValue>({
  property: null,
  propertyName: null,
  currency: "EUR",
  money: (amount, currencyOverride) =>
    formatCurrency(amount, currencyOverride || "EUR"),
});

export function WorkspaceProvider({
  property,
  children,
}: {
  property: Property | null;
  children: ReactNode;
}) {
  const currency = (property?.currency || "EUR").toUpperCase();
  const propertyName = property?.name || null;

  const money = useCallback(
    (amount: number, currencyOverride?: string) =>
      formatCurrency(amount, (currencyOverride || currency).toUpperCase()),
    [currency]
  );

  const value = useMemo(
    () => ({ property, propertyName, currency, money }),
    [property, propertyName, currency, money]
  );

  return (
    <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  return useContext(WorkspaceContext);
}

/** Format amounts in the onboarded hotel currency. */
export function useMoney() {
  return useWorkspace().money;
}

export function useWorkspaceCurrency() {
  return useWorkspace().currency;
}
