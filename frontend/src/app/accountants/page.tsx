"use client";

import { useCallback, useEffect, useState } from "react";
import { clientApi, ClientApiError, fetchMe, logout, type MeResponse } from "@/lib/clientApi";
import { formatMinor } from "@/lib/money";
import { Logo } from "@/components/layout/Logo";
import ThemeToggle from "@/components/theme/ThemeToggle";
import { useAggregatedBalances } from "@/hooks/useAggregatedBalances";

type Invite = {
  id: number;
  organization_id: number;
  organization_name: string;
  email: string;
  status: string;
  expires_at: string;
  can_accept: boolean;
};

type Payment = {
  id: number;
  organization: number;
  amount_cents: number;
  allocated_cents: number;
  received_date: string;
  method: string;
  status: string;
  reference: string;
};

type Invoice = {
  id: number;
  organization: number;
  period_start: string;
  period_end: string;
  due_date: string;
  status: string;
  currency: string;
  total_cents: number;
  paid_cents: number;
  balance_cents: number;
};

function sum(rows: Invoice[], key: "total_cents" | "paid_cents" | "balance_cents") {
  return rows.reduce((total, row) => total + row[key], 0);
}

export default function AccountantWorkspace() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [org, setOrg] = useState("");
  const [clientSearch, setClientSearch] = useState("");
  const [clientPickerOpen, setClientPickerOpen] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [profile, invitationResponse] = await Promise.all([
        fetchMe(),
        clientApi.get<Invite[]>("/api/v1/organizations/accountant-invitations/"),
      ]);
      setMe(profile);
      setInvites(invitationResponse.data);
      const permitted = profile.memberships.filter((membership) => membership.role === "ACCOUNTANT" && membership.is_active);
      const selected = permitted.find((membership) => String(membership.organization) === org) || permitted[0];
      if (selected) {
        setOrg(String(selected.organization));
        const [invoiceResponse, ledgerResponse] = await Promise.all([
          clientApi.get<Invoice[]>("/api/v1/billing/invoices/", { params: { organization: selected.organization } }),
          clientApi.get<Payment[]>("/api/v1/billing/ledger-payments/", { params: { organization: selected.organization } }),
        ]);
        setInvoices(invoiceResponse.data.filter((invoice) => String(invoice.organization) === String(selected.organization)));
        setPayments(ledgerResponse.data.filter((payment) => String(payment.organization) === String(selected.organization)));
      } else {
        setInvoices([]);
        setPayments([]);
      }
      setError("");
    } catch (loadError) {
      if (loadError instanceof ClientApiError && (loadError.status === 401 || loadError.status === 403)) {
        window.location.replace("/signin");
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Could not load accountant records.");
    } finally {
      setLoading(false);
    }
  }, [org]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function action(id: number, name: string) {
    setError("");
    try {
      await clientApi.post(`/api/v1/organizations/accountant-invitations/${id}/${name}/`, {});
      await refresh();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Invitation action failed.");
    }
  }

  async function signOut() {
    try {
      await logout();
    } catch {
      // The shared logout helper clears the local session even if the API is unavailable.
    }
    window.location.assign("/signin");
  }

  const clients = me?.memberships.filter((membership) => membership.role === "ACCOUNTANT" && membership.is_active) || [];
  const pending = invites.filter((invite) => invite.status === "PENDING" && invite.can_accept);
  const currency = invoices[0]?.currency || "KES";
  const selectedClient = clients.find((membership) => String(membership.organization) === org);
  const matchingClients = clients.filter((membership) =>
    membership.organization_name.toLocaleLowerCase().includes(clientSearch.trim().toLocaleLowerCase()),
  );
  const totalBalanceCents = useAggregatedBalances(org, invoices);

  return (
    <main className="hodi-record">
      <div className="hodi-record-wrap">
        <header className="hodi-record-topbar">
          <Logo size={34} />
          {clients.length > 0 && (
            <nav className="hodi-record-nav" aria-label="Accountant workspace sections">
              <a href="#overview">Overview</a>
              <a href="#invoices">Invoices</a>
              <a href="#payments">Payments</a>
            </nav>
          )}
          <div className="hodi-record-header-actions">
            <ThemeToggle />
            <button type="button" className="secondary" onClick={() => void refresh()} disabled={loading}>
              {loading ? "Refreshing…" : "Refresh"}
            </button>
            <button type="button" className="secondary" onClick={() => void signOut()}>Sign out</button>
          </div>
        </header>
        <p className="hodi-record-kicker">Hodi finance</p>
        <h1>Accountant workspace</h1>
        <p className="hodi-record-lead">
          Client access is granted by an organisation owner and can be revoked at any time. Figures below are recorded invoices and payments only.
        </p>
        {selectedClient && <p className="hodi-record-note" aria-live="polite">Total balance: <strong>{formatMinor(totalBalanceCents, currency)}</strong></p>}
        {error && <p className="hodi-record-alert" role="alert">{error}</p>}
        {loading && <p className="hodi-record-note" role="status">Loading client access…</p>}

        {pending.map((invite) => (
          <article className="hodi-record-invite" key={invite.id}>
            <h2>Invitation to {invite.organization_name}</h2>
            <p className="hodi-record-note">Expires {new Date(invite.expires_at).toLocaleDateString("en-KE")}</p>
            <div className="hodi-record-actions">
              <button type="button" onClick={() => void action(invite.id, "accept")}>Accept</button>
              <button type="button" className="secondary" onClick={() => void action(invite.id, "decline")}>Decline</button>
            </div>
          </article>
        ))}

        {clients.length > 0 && (
          <>
            <div className="relative max-w-xl">
              <label className="block text-sm font-medium" htmlFor="accountant-client-search">Client organisation</label>
              <input
                id="accountant-client-search"
                role="combobox"
                aria-autocomplete="list"
                aria-expanded={clientPickerOpen}
                aria-controls="accountant-client-options"
                aria-activedescendant={undefined}
                autoComplete="off"
                className="mt-1 min-h-11 w-full rounded border border-border bg-surface px-3 text-base"
                placeholder={selectedClient?.organization_name ?? "Search client organisations"}
                value={clientSearch}
                onFocus={() => setClientPickerOpen(true)}
                onChange={(event) => { setClientSearch(event.target.value); setClientPickerOpen(true); }}
                onKeyDown={(event) => {
                  if (event.key === "Escape") setClientPickerOpen(false);
                  if (event.key === "Enter" && matchingClients[0]) {
                    event.preventDefault();
                    setInvoices([]);
                    setPayments([]);
                    setOrg(String(matchingClients[0].organization));
                    setClientSearch("");
                    setClientPickerOpen(false);
                  }
                }}
              />
              {clientPickerOpen && matchingClients.length > 0 && (
                <ul id="accountant-client-options" role="listbox" className="absolute z-20 mt-1 max-h-60 w-full overflow-y-auto rounded border border-border bg-surface p-1 shadow-lg">
                  {matchingClients.map((membership) => (
                    <li key={membership.organization} role="option" aria-selected={String(membership.organization) === org}>
                      <button
                        type="button"
                        className="min-h-11 w-full rounded px-3 text-left text-sm hover:bg-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal"
                        onClick={() => {
                          setInvoices([]);
                          setPayments([]);
                          setOrg(String(membership.organization));
                          setClientSearch("");
                          setClientPickerOpen(false);
                        }}
                      >
                        {membership.organization_name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {clientPickerOpen && matchingClients.length === 0 && <p className="hodi-record-note" role="status">No matching organisations.</p>}
            </div>
            <section id="overview" className="hodi-record-stats" aria-label="Invoice totals" aria-busy={loading}>
              <article className="hodi-record-stat"><span>Invoices</span><strong>{invoices.length}</strong></article>
              <article className="hodi-record-stat"><span>Invoiced</span><strong>{formatMinor(sum(invoices, "total_cents"), currency)}</strong></article>
              <article className="hodi-record-stat"><span>Paid</span><strong>{formatMinor(sum(invoices, "paid_cents"), currency)}</strong></article>
              <article className="hodi-record-stat"><span>Outstanding</span><strong>{formatMinor(sum(invoices, "balance_cents"), currency)}</strong></article>
            </section>

            <h2 id="invoices">Invoice report</h2>
            <div className="hodi-record-table-wrap">
              <table className="hodi-record-invoice-table">
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Period</th>
                    <th>Status</th>
                    <th>Total</th>
                    <th>Paid</th>
                    <th>Outstanding</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>{invoice.id}</td>
                      <td>{invoice.period_start}–{invoice.period_end}</td>
                      <td>{invoice.status}</td>
                      <td>{formatMinor(invoice.total_cents, invoice.currency)}</td>
                      <td>{formatMinor(invoice.paid_cents, invoice.currency)}</td>
                      <td>{formatMinor(invoice.balance_cents, invoice.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!invoices.length && <p className="hodi-record-note">No invoices are recorded for this client.</p>}

            <h2 id="payments">Recorded rent transactions</h2>
            <div className="hodi-record-table-wrap">
              <table className="hodi-record-payment-table">
                <thead>
                  <tr>
                    <th>Payment</th>
                    <th>Received</th>
                    <th>Method</th>
                    <th>Status</th>
                    <th>Amount</th>
                    <th>Allocated</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((payment) => (
                    <tr key={payment.id}>
                      <td>{payment.id}<p className="hodi-record-note">{payment.reference || "No reference"}</p></td>
                      <td>{payment.received_date}</td>
                      <td>{payment.method}</td>
                      <td>{payment.status}</td>
                      <td>{payment.amount_cents == null ? "Amount unavailable" : formatMinor(payment.amount_cents)}</td>
                      <td>{formatMinor(payment.allocated_cents)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!payments.length && <p className="hodi-record-note">No recorded payments are available for this client.</p>}
          </>
        )}

        {!loading && !error && clients.length === 0 && !pending.length && (
          <p className="hodi-record-note">No active client access or pending invitations are linked to this account.</p>
        )}
      </div>
    </main>
  );
}
