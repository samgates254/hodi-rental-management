"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { clientApi } from "@/lib/clientApi";
import { apiErrorMessage, formatCents, getList, humanize } from "@/lib/opsApi";
import "./ops.css";

type TenantRow = { id: number | string; organization: number | string; full_name?: string; first_name: string; last_name: string };
type LeaseRow = { id: number | string; tenant: number | string; reference: string; status: string; unit: number | string };
type ChargeRow = {
  id: string;
  charge_type: string;
  description: string;
  amount_cents: number;
  balance_cents: number;
  due_date: string;
  lifecycle: string;
};
type InvoiceRow = {
  id: number | string;
  organization: number | string;
  tenant: number | string;
  lease: number | string | null;
  period_start: string;
  period_end: string;
  due_date: string;
  status: string;
  total_cents: number;
  paid_cents: number;
  balance_cents: number;
  notes: string;
  charges: ChargeRow[];
};
type RentPaymentRow = {
  id: number | string;
  organization: number | string;
  lease: number | string;
  lease_reference?: string;
  tenant_name?: string;
  unit_name?: string;
  due_date: string;
  amount_minor: number;
  status: string;
  paid_at?: string | null;
  method?: string;
  reference?: string;
};
type AllocationRow = { id: number | string; charge: string; amount_cents: number };
type PostingRow = { id: number | string; account: string; direction: string; amount_cents: number };
type LedgerPayment = {
  id: string;
  organization: number | string;
  tenant: number | string;
  amount_cents: number;
  allocated_cents: number;
  overpayment_cents: number;
  received_date: string;
  method: string;
  status: string;
  reference: string;
  allocations: AllocationRow[];
  postings: PostingRow[];
};
type DelinquencyItem = {
  obligation_id: string;
  status: string;
  balance_cents: number;
  days_past_due: number;
};
type Delinquency = {
  tenant: number;
  as_of: string;
  grace_days: number;
  status: string;
  open_cents: number;
  current_cents: number;
  grace_cents: number;
  delinquent_cents: number;
  items: DelinquencyItem[];
};

const CHARGE_TYPES = [
  "RENT", "BASE_RENT", "WATER", "ELECTRICITY", "SEWER", "GAS", "UTILITY",
  "SERVICE_CHARGE", "GARBAGE", "SECURITY", "MANDATORY_SERVICE", "PENALTY", "LATE_FEE", "FINE",
];

const ALLOCATION_POLICY = { policy_id: "CANONICAL_PRIORITY", policy_version: 2 };

function kesToCents(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  const [whole, fraction = ""] = trimmed.split(".");
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function BillingWorkspace({
  organizationId,
  canWriteLedger,
  canWriteRentLog,
}: {
  organizationId: string;
  canWriteLedger: boolean;
  canWriteRentLog: boolean;
}) {
  const [tab, setTab] = useState<"invoices" | "payments" | "ledger" | "delinquency">("invoices");
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [leases, setLeases] = useState<LeaseRow[]>([]);
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [payments, setPayments] = useState<RentPaymentRow[]>([]);
  const [ledger, setLedger] = useState<LedgerPayment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showInvoice, setShowInvoice] = useState(false);
  const [showRent, setShowRent] = useState(false);
  const [showLedger, setShowLedger] = useState(false);
  const [allocation, setAllocation] = useState<LedgerPayment | null>(null);
  const [delinquency, setDelinquency] = useState<Delinquency | null>(null);
  const [chargeInvoiceId, setChargeInvoiceId] = useState("");

  const load = useCallback(async () => {
    if (!organizationId) return;
    setLoading(true);
    setError("");
    try {
      const [tenantRows, leaseRows, invoiceRows, paymentRows, ledgerRows] = await Promise.all([
        getList<TenantRow>("/api/v1/tenants/"),
        getList<LeaseRow>("/api/v1/leases/"),
        getList<InvoiceRow>("/api/v1/billing/invoices/"),
        getList<RentPaymentRow>("/api/v1/billing/payments/", { organization: organizationId }),
        getList<LedgerPayment>("/api/v1/billing/ledger-payments/"),
      ]);
      const orgTenants = tenantRows.filter(row => String(row.organization) === organizationId);
      const tenantIds = new Set(orgTenants.map(row => String(row.id)));
      setTenants(orgTenants);
      setLeases(leaseRows.filter(row => tenantIds.has(String(row.tenant))));
      setInvoices(invoiceRows.filter(row => String(row.organization) === organizationId));
      setPayments(paymentRows);
      setLedger(ledgerRows.filter(row => String(row.organization) === organizationId));
    } catch (loadError) {
      setError(apiErrorMessage(loadError, "Billing records couldn’t be loaded."));
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    void load();
  }, [load]);

  const tenantName = useMemo(() => {
    const map = new Map<string, string>();
    tenants.forEach(tenant => {
      map.set(String(tenant.id), tenant.full_name || `${tenant.first_name} ${tenant.last_name}`.trim());
    });
    return map;
  }, [tenants]);

  async function createInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const lease = String(form.get("lease") ?? "");
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post("/api/v1/billing/invoices/", {
        tenant: Number(form.get("tenant")),
        lease: lease ? Number(lease) : null,
        period_start: String(form.get("period_start")),
        period_end: String(form.get("period_end")),
        due_date: String(form.get("due_date")),
        notes: String(form.get("notes") ?? ""),
        include_rent: form.get("include_rent") === "on",
      });
      setShowInvoice(false);
      setNotice("Draft invoice created.");
      await load();
    } catch (createError) {
      setError(apiErrorMessage(createError, "The invoice couldn’t be created."));
    } finally {
      setBusy(false);
    }
  }

  async function postInvoice(id: number | string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`/api/v1/billing/invoices/${id}/post/`, {});
      setNotice("Invoice posted.");
      await load();
    } catch (postError) {
      setError(apiErrorMessage(postError, "The invoice couldn’t be posted."));
    } finally {
      setBusy(false);
    }
  }

  async function voidInvoice(id: number | string) {
    if (!window.confirm("Void this posted invoice? Allocated invoices cannot be voided.")) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`/api/v1/billing/invoices/${id}/void/`, {});
      setNotice("Invoice voided.");
      await load();
    } catch (voidError) {
      setError(apiErrorMessage(voidError, "The invoice couldn’t be voided."));
    } finally {
      setBusy(false);
    }
  }

  async function addCharge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const cents = kesToCents(String(form.get("amount") ?? ""));
    if (cents == null) {
      setError("Enter a charge amount in KES with up to two decimals.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post("/api/v1/billing/charges/", {
        invoice: String(form.get("invoice")),
        charge_type: String(form.get("charge_type")),
        amount_cents: cents,
        due_date: String(form.get("due_date")),
        description: String(form.get("description") ?? ""),
      });
      setNotice(`Charge added for ${cents} cents.`);
      await load();
    } catch (chargeError) {
      setError(apiErrorMessage(chargeError, "The charge couldn’t be added."));
    } finally {
      setBusy(false);
    }
  }

  async function recordRent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const cents = kesToCents(String(form.get("amount") ?? ""));
    if (cents == null) {
      setError("Enter the rent amount in KES with up to two decimals.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post("/api/v1/billing/payments/", {
        lease: Number(form.get("lease")),
        due_date: String(form.get("due_date")),
        amount_minor: cents,
        status: String(form.get("status") ?? "PENDING"),
        method: String(form.get("method") ?? ""),
        reference: String(form.get("reference") ?? ""),
      });
      setShowRent(false);
      setNotice(`Rent payment recorded for ${cents} cents.`);
      await load();
    } catch (rentError) {
      setError(apiErrorMessage(rentError, "The rent payment couldn’t be recorded."));
    } finally {
      setBusy(false);
    }
  }

  async function recordLedger(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const cents = kesToCents(String(form.get("amount") ?? ""));
    if (cents == null) {
      setError("Enter the ledger amount in KES with up to two decimals.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await clientApi.post<LedgerPayment>("/api/v1/billing/ledger-payments/", {
        tenant: Number(form.get("tenant")),
        amount_cents: cents,
        received_date: String(form.get("received_date")),
        method: String(form.get("method")),
        reference: String(form.get("reference") ?? ""),
      });
      setShowLedger(false);
      setAllocation(response.data);
      setNotice(`Ledger payment recorded for ${response.data.amount_cents} cents. Allocate it to apply the server result.`);
      await load();
    } catch (ledgerError) {
      setError(apiErrorMessage(ledgerError, "The ledger payment couldn’t be recorded."));
    } finally {
      setBusy(false);
    }
  }

  async function allocate(paymentId: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await clientApi.post<LedgerPayment>(
        `/api/v1/billing/ledger-payments/${paymentId}/allocate/`,
        ALLOCATION_POLICY,
      );
      setAllocation(response.data);
      setNotice("Allocation finished. Figures below are the server result.");
      await load();
    } catch (allocateError) {
      setError(apiErrorMessage(allocateError, "The payment couldn’t be allocated."));
    } finally {
      setBusy(false);
    }
  }

  async function assess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setDelinquency(null);
    try {
      const response = await clientApi.get<Delinquency>("/api/v1/billing/delinquency/", {
        params: {
          tenant: String(form.get("tenant")),
          as_of: String(form.get("as_of")),
          grace_days: String(form.get("grace_days") ?? "0"),
        },
      });
      setDelinquency(response.data);
    } catch (assessError) {
      setError(apiErrorMessage(assessError, "Delinquency couldn’t be assessed."));
    } finally {
      setBusy(false);
    }
  }

  const draftInvoices = invoices.filter(invoice => invoice.status === "DRAFT");

  return (
    <section className="ops-panel" id="billing">
      <div className="ops-heading">
        <div>
          <span className="ops-kicker">BILLING</span>
          <h2>Invoices, rent log, and ledger</h2>
          <p>Rent payments stay on the rent log. Ledger allocation is a separate accounting step and uses the server’s result.</p>
        </div>
        <button type="button" className="ops-button" onClick={() => void load()} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
      </div>
      <div className="ops-tabs" role="tablist">
        {([
          ["invoices", "Invoices"],
          ["payments", "Rent payments"],
          ["ledger", "Ledger"],
          ["delinquency", "Delinquency"],
        ] as const).map(([id, label]) => (
          <button key={id} type="button" className={tab === id ? "is-active" : ""} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>
      {error && <p className="ops-alert" role="alert">{error}</p>}
      {notice && <p className="ops-success" role="status">{notice}</p>}
      {loading && <p className="ops-status">Loading billing records…</p>}

      {tab === "invoices" && (
        <>
          {canWriteLedger && (
            <div className="ops-actions">
              <button type="button" className="ops-button ops-button--primary" onClick={() => setShowInvoice(open => !open)}>
                {showInvoice ? "Cancel invoice" : "New invoice"}
              </button>
            </div>
          )}
          {showInvoice && canWriteLedger && (
            <form className="ops-form" onSubmit={event => void createInvoice(event)}>
              <div className="ops-grid">
                <label>Tenant
                  <select name="tenant" required defaultValue="">
                    <option value="" disabled>Select a tenant</option>
                    {tenants.map(tenant => <option key={tenant.id} value={tenant.id}>{tenantName.get(String(tenant.id))}</option>)}
                  </select>
                </label>
                <label>Lease
                  <select name="lease" defaultValue="">
                    <option value="">No lease</option>
                    {leases.map(lease => <option key={lease.id} value={lease.id}>{lease.reference} · {humanize(lease.status)}</option>)}
                  </select>
                </label>
                <label>Period start<input name="period_start" type="date" required defaultValue={today()} /></label>
                <label>Period end<input name="period_end" type="date" required defaultValue={today()} /></label>
                <label>Due date<input name="due_date" type="date" required defaultValue={today()} /></label>
              </div>
              <label className="ops-field"><span><input name="include_rent" type="checkbox" defaultChecked /> Include rent from the lease</span></label>
              <label>Notes<input name="notes" maxLength={300} /></label>
              <button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Create draft"}</button>
            </form>
          )}
          {canWriteLedger && draftInvoices.length > 0 && (
            <form className="ops-form" onSubmit={event => void addCharge(event)}>
              <strong>Add a charge to a draft</strong>
              <div className="ops-grid">
                <label>Invoice
                  <select name="invoice" required value={chargeInvoiceId} onChange={event => setChargeInvoiceId(event.target.value)}>
                    <option value="" disabled>Select a draft</option>
                    {draftInvoices.map(invoice => <option key={invoice.id} value={invoice.id}>#{invoice.id} · {tenantName.get(String(invoice.tenant)) ?? "Tenant"}</option>)}
                  </select>
                </label>
                <label>Type
                  <select name="charge_type" defaultValue="RENT">
                    {CHARGE_TYPES.map(type => <option key={type} value={type}>{humanize(type)}</option>)}
                  </select>
                </label>
                <label>Amount (KES)<input name="amount" inputMode="decimal" required placeholder="548.39" /></label>
                <label>Due date<input name="due_date" type="date" required defaultValue={today()} /></label>
              </div>
              <label>Description<input name="description" /></label>
              <button className="ops-button" disabled={busy || !chargeInvoiceId}>Add charge</button>
            </form>
          )}
          {!loading && invoices.length === 0 && <div className="ops-empty"><strong>No invoices</strong><p>Draft, post, and void invoices for this organization.</p></div>}
          {invoices.length > 0 && (
            <div className="ops-table-wrap">
              <table className="ops-table">
                <thead><tr><th>Invoice</th><th>Tenant</th><th>Period</th><th>Due</th><th>Invoice total</th><th>Amount paid</th><th>Balance due</th><th>Status</th><th></th></tr></thead>
                <tbody>
                  {invoices.map(invoice => (
                    <tr key={invoice.id}>
                      <td>#{invoice.id}<div className="ops-note">{invoice.charges?.length ?? 0} charges</div></td>
                      <td>{tenantName.get(String(invoice.tenant)) ?? `Tenant ${invoice.tenant}`}</td>
                      <td>{invoice.period_start} – {invoice.period_end}</td>
                      <td>{invoice.due_date}</td>
                      <td>{formatCents(invoice.total_cents)}</td>
                      <td>{formatCents(invoice.paid_cents)}</td>
                      <td>{formatCents(invoice.balance_cents)}</td>
                      <td><span className={`ops-pill ${invoice.balance_cents > 0 && invoice.status === "POSTED" ? "is-hot" : "is-good"}`}>{humanize(invoice.status)}</span></td>
                      <td>
                        {canWriteLedger && invoice.status === "DRAFT" && <button type="button" className="ops-button" disabled={busy} onClick={() => void postInvoice(invoice.id)}>Post</button>}
                        {canWriteLedger && invoice.status === "POSTED" && <button type="button" className="ops-button" disabled={busy} onClick={() => void voidInvoice(invoice.id)}>Void</button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "payments" && (
        <>
          <p className="ops-note">This list is the rent-payment record (`amount_minor`, PENDING / PAID / OVERDUE). It is not the ledger.</p>
          {canWriteRentLog && (
            <button type="button" className="ops-button ops-button--primary" onClick={() => setShowRent(open => !open)}>
              {showRent ? "Cancel" : "Record rent payment"}
            </button>
          )}
          {showRent && canWriteRentLog && (
            <form className="ops-form" onSubmit={event => void recordRent(event)}>
              <div className="ops-grid">
                <label>Lease
                  <select name="lease" required defaultValue="">
                    <option value="" disabled>Select a lease</option>
                    {leases.map(lease => <option key={lease.id} value={lease.id}>{lease.reference}</option>)}
                  </select>
                </label>
                <label>Amount (KES)<input name="amount" inputMode="decimal" required /></label>
                <label>Due date<input name="due_date" type="date" required defaultValue={today()} /></label>
                <label>Status
                  <select name="status" defaultValue="PENDING">
                    <option value="PENDING">Pending</option>
                    <option value="PAID">Paid</option>
                    <option value="OVERDUE">Overdue</option>
                  </select>
                </label>
                <label>Method<input name="method" placeholder="CASH" /></label>
                <label>Reference<input name="reference" /></label>
              </div>
              <button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Save rent payment"}</button>
            </form>
          )}
          {!loading && payments.length === 0 && <div className="ops-empty"><strong>No rent payments</strong><p>Recorded rent payments for this organization will appear here.</p></div>}
          {payments.length > 0 && (
            <div className="ops-table-wrap">
              <table className="ops-table">
                <thead><tr><th>Resident</th><th>Unit</th><th>Lease</th><th>Amount</th><th>Due</th><th>Status</th><th>Reference</th></tr></thead>
                <tbody>
                  {payments.map(payment => (
                    <tr key={payment.id}>
                      <td>{payment.tenant_name ?? "Resident"}</td>
                      <td>{payment.unit_name ?? "—"}</td>
                      <td>{payment.lease_reference ?? payment.lease}</td>
                      <td>{formatCents(payment.amount_minor)}</td>
                      <td>{payment.due_date}</td>
                      <td>{humanize(payment.status)}</td>
                      <td>{payment.reference || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "ledger" && (
        <>
          <p className="ops-note">Ledger payments are allocated by the server with policy CANONICAL_PRIORITY version 2. Do not treat a local sum as the balance.</p>
          {canWriteLedger && (
            <button type="button" className="ops-button ops-button--primary" onClick={() => setShowLedger(open => !open)}>
              {showLedger ? "Cancel" : "Record ledger payment"}
            </button>
          )}
          {showLedger && canWriteLedger && (
            <form className="ops-form" onSubmit={event => void recordLedger(event)}>
              <div className="ops-grid">
                <label>Tenant
                  <select name="tenant" required defaultValue="">
                    <option value="" disabled>Select a tenant</option>
                    {tenants.map(tenant => <option key={tenant.id} value={tenant.id}>{tenantName.get(String(tenant.id))}</option>)}
                  </select>
                </label>
                <label>Amount (KES)<input name="amount" inputMode="decimal" required placeholder="800.00" /></label>
                <label>Received<input name="received_date" type="date" required defaultValue={today()} /></label>
                <label>Method
                  <select name="method" defaultValue="CASH">
                    <option value="CASH">Cash</option>
                    <option value="BANK_TRANSFER">Bank transfer</option>
                    <option value="MPESA">M-Pesa reference only</option>
                    <option value="OTHER">Other</option>
                  </select>
                </label>
                <label>Reference<input name="reference" /></label>
              </div>
              <p className="ops-note">M-Pesa here only stores a method label. It does not start a checkout.</p>
              <button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Save ledger payment"}</button>
            </form>
          )}
          {allocation && (
            <div className="ops-detail" role="status">
              <strong>Latest allocation result</strong>
              <dl className="ops-meta">
                <div><dt>Payment</dt><dd>{allocation.amount_cents} cents</dd></div>
                <div><dt>Applied</dt><dd>{allocation.allocated_cents} cents</dd></div>
                <div><dt>Remainder</dt><dd>{allocation.overpayment_cents} cents</dd></div>
                <div><dt>Status</dt><dd>{humanize(allocation.status)}</dd></div>
              </dl>
              <p className="ops-note">
                Applied {formatCents(allocation.allocated_cents)}. Remainder {formatCents(allocation.overpayment_cents)}.
              </p>
              {allocation.allocations?.length > 0 && (
                <ul>
                  {allocation.allocations.map(row => (
                    <li key={row.id}>Charge {row.charge}: {row.amount_cents} cents</li>
                  ))}
                </ul>
              )}
              {allocation.postings?.length > 0 && (
                <ul>
                  {allocation.postings.map(row => (
                    <li key={row.id}>{row.direction} {row.account}: {row.amount_cents} cents</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {!loading && ledger.length === 0 && <div className="ops-empty"><strong>No ledger payments</strong><p>Record a payment, then allocate it against posted charges.</p></div>}
          {ledger.length > 0 && (
            <div className="ops-table-wrap">
              <table className="ops-table">
                <thead><tr><th>Received</th><th>Tenant</th><th>Amount</th><th>Applied</th><th>Remainder</th><th>Status</th><th></th></tr></thead>
                <tbody>
                  {ledger.map(payment => (
                    <tr key={payment.id}>
                      <td>{payment.received_date}</td>
                      <td>{tenantName.get(String(payment.tenant)) ?? `Tenant ${payment.tenant}`}</td>
                      <td>{formatCents(payment.amount_cents)}</td>
                      <td>{formatCents(payment.allocated_cents)}</td>
                      <td>{formatCents(payment.overpayment_cents)}</td>
                      <td>{humanize(payment.status)} · {humanize(payment.method)}</td>
                      <td>
                        {canWriteLedger && payment.status !== "ALLOCATED" && payment.status !== "VOIDED" && (
                          <button type="button" className="ops-button" disabled={busy} onClick={() => void allocate(payment.id)}>Allocate</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "delinquency" && (
        <>
          <form className="ops-form" onSubmit={event => void assess(event)}>
            <div className="ops-grid">
              <label>Tenant
                <select name="tenant" required defaultValue="">
                  <option value="" disabled>Select a tenant</option>
                  {tenants.map(tenant => <option key={tenant.id} value={tenant.id}>{tenantName.get(String(tenant.id))}</option>)}
                </select>
              </label>
              <label>As of<input name="as_of" type="date" required defaultValue={today()} /></label>
              <label>Grace days<input name="grace_days" type="number" min={0} defaultValue={0} required /></label>
            </div>
            <button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Checking…" : "Assess delinquency"}</button>
          </form>
          {!delinquency && !busy && <div className="ops-empty"><strong>No assessment yet</strong><p>Choose a tenant and date. Amounts come back from the delinquency API.</p></div>}
          {delinquency && (
            <div className="ops-detail">
              <dl className="ops-meta">
                <div><dt>Status</dt><dd>{humanize(delinquency.status)}</dd></div>
                <div><dt>Open</dt><dd>{formatCents(delinquency.open_cents)}</dd></div>
                <div><dt>Current</dt><dd>{formatCents(delinquency.current_cents)}</dd></div>
                <div><dt>In grace</dt><dd>{formatCents(delinquency.grace_cents)}</dd></div>
                <div><dt>Delinquent</dt><dd>{formatCents(delinquency.delinquent_cents)}</dd></div>
                <div><dt>As of</dt><dd>{delinquency.as_of} · grace {delinquency.grace_days} days</dd></div>
              </dl>
              {delinquency.items?.length > 0 && (
                <div className="ops-table-wrap">
                  <table className="ops-table">
                    <thead><tr><th>Obligation</th><th>Status</th><th>Balance</th><th>Days past due</th></tr></thead>
                    <tbody>
                      {delinquency.items.map(item => (
                        <tr key={item.obligation_id}>
                          <td>{item.obligation_id}</td>
                          <td>{humanize(item.status)}</td>
                          <td>{formatCents(item.balance_cents)}</td>
                          <td>{item.days_past_due}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
      <p className="ops-note">Online M-Pesa checkout is not available. Recording a method does not collect money.</p>
    </section>
  );
}
