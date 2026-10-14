import { useMemo } from "react";

type BalanceInvoice = {
  organization: number;
  balance_cents: number;
};

export function useAggregatedBalances(clientId: string, invoices: BalanceInvoice[]) {
  return useMemo(
    () => invoices.reduce(
      (total, invoice) => String(invoice.organization) === clientId
        ? total + invoice.balance_cents
        : total,
      0,
    ),
    [clientId, invoices],
  );
}