"use client";

import { useEffect, useState, type FormEvent } from "react";
import { clientApi, getStoredAuthToken, setStoredAuthToken, type AuthResponse } from "@/lib/clientApi";
import ThemeToggle from "@/components/theme/ThemeToggle";

type RevenueSummary = {
  active_subscriptions: number;
  paid_organizations: number;
  free_organizations: number;
  organizations_by_plan: Array<{ plan__code: string; plan__name: string; status: string; organizations: number }>;
  subscription_invoices_issued: number;
  verified_payments: number;
  collected_minor: number;
  net_collected_minor: number;
  reversed_minor: number;
  outstanding_minor: number;
  overdue_invoices: number;
  cancelled_or_expired: number;
  pending_payment_reports: number;
  verified_plan_upgrades: number;
  verified_plan_downgrades: number;
  recent_activity: Array<{ action: string; organization: string | null; actor: string | null; created_at: string }>;
};
type PaymentReport = {
  id: number;
  invoice_number: string;
  organization_name: string;
  amount_minor: number;
  currency: string;
  reference: string;
  reported_by_name: string;
};
type EnterpriseOrganization = { organization: number; organization_name: string; current_plan: string; status: string };

const kes = (minor: number) => new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", maximumFractionDigits: 0 }).format(minor / 100);

export default function RevenueDashboardPage() {
  const [summary, setSummary] = useState<RevenueSummary | null>(null);
  const [reports, setReports] = useState<PaymentReport[]>([]);
  const [organizations, setOrganizations] = useState<EnterpriseOrganization[]>([]);
  const [enterpriseOrg, setEnterpriseOrg] = useState("");
  const [enterpriseAmount, setEnterpriseAmount] = useState("");
  const [enterpriseLimit, setEnterpriseLimit] = useState("");
  const [enterpriseReason, setEnterpriseReason] = useState("");
  const [reviewReason, setReviewReason] = useState<Record<number, string>>({});
  const [reviewError, setReviewError] = useState("");
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isAuthorized, setIsAuthorized] = useState(false);

  useEffect(() => {
    if (!getStoredAuthToken()) return;
    void Promise.all([
      clientApi.get<RevenueSummary>("/api/v1/subscriptions/admin/revenue/"),
      clientApi.get<PaymentReport[]>("/api/v1/subscriptions/admin/payment-reports/"),
      clientApi.get<EnterpriseOrganization[]>("/api/v1/subscriptions/admin/enterprise-invoices/"),
    ]).then(([revenue, pending, orgs]) => { setSummary(revenue.data); setReports(pending.data); setOrganizations(orgs.data); setIsAuthorized(true); }).catch(cause => {
      setError(cause instanceof Error && "status" in cause && (cause as { status: number }).status === 403
        ? "This dashboard is restricted to authorized Hodi administrators."
        : cause instanceof Error && "status" in cause && (cause as { status: number }).status === 401
          ? "Your session has expired. Sign in again with an authorized Hodi administrator account."
          : cause instanceof Error ? cause.message : "Revenue data could not be loaded.");
    });
  }, []);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try {
      const response = await clientApi.post<AuthResponse>("/api/v1/accounts/login/", { username, password }, { skipAuth: true });
      if (!response.data.is_staff || !response.data.token) {
        setStoredAuthToken(null);
        setError("This account is not authorized for Hodi administration.");
        return;
      }
      setStoredAuthToken(response.data.token);
      window.location.reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Administrator sign in failed."); }
  }

  async function reviewReport(id: number, action: "confirm" | "reject") {
    const reason = reviewReason[id]?.trim() ?? "";
    if (reason.length < 8) { setReviewError("Enter a verification reason of at least 8 characters."); return; }
    setReviewError("");
    try {
      await clientApi.post(`/api/v1/subscriptions/admin/payment-reports/${id}/${action}/`, { reason });
      setReports(current => current.filter(report => report.id !== id));
      setReviewReason(current => { const next = { ...current }; delete next[id]; return next; });
    } catch (cause) { setReviewError(cause instanceof Error ? cause.message : "Payment report review failed."); }
  }

  async function issueEnterpriseInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setReviewError("");
    try {
      await clientApi.post("/api/v1/subscriptions/admin/enterprise-invoices/", {
        organization: Number(enterpriseOrg), amount_minor: Number(enterpriseAmount) * 100,
        unit_limit: Number(enterpriseLimit), reason: enterpriseReason,
      });
      setEnterpriseAmount(""); setEnterpriseLimit(""); setEnterpriseReason("");
      setReviewError("Enterprise invoice issued with the negotiated terms.");
    } catch (cause) { setReviewError(cause instanceof Error ? cause.message : "Enterprise invoice could not be issued."); }
  }

  const metrics = summary ? [
    ["Paid subscriptions", String(summary.active_subscriptions)],
    ["Paid organizations", String(summary.paid_organizations)],
    ["Free organizations", String(summary.free_organizations)],
    ["Verified payments", String(summary.verified_payments)],
    ["Gross verified payments", kes(summary.collected_minor)],
    ["Net collected after reversals", kes(summary.net_collected_minor)],
    ["Reversed payments", kes(summary.reversed_minor)],
    ["Outstanding invoices", kes(summary.outstanding_minor)],
    ["Overdue invoices", String(summary.overdue_invoices)],
    ["Payment reports to review", String(summary.pending_payment_reports)],
    ["Cancelled or expired", String(summary.cancelled_or_expired)],
    ["Subscription invoices issued", String(summary.subscription_invoices_issued)],
    ["Verified upgrades / downgrades", `${summary.verified_plan_upgrades} / ${summary.verified_plan_downgrades}`],
  ] : [];

  return <main className="min-h-screen bg-bg px-5 py-8 text-text sm:px-8">
    <div className="mx-auto max-w-6xl">
      <header className="flex items-center justify-between gap-4 border-b border-border pb-5"><div><p className="text-xs font-bold tracking-[0.16em] text-brand">INTERNAL · HODI</p><h1 className="mt-2 text-3xl font-semibold">Subscription revenue</h1></div><ThemeToggle /></header>
      {error && <div className="mt-6 rounded-xl border border-border bg-surface p-5" role="alert"><p>{error}</p></div>}
      {!isAuthorized && <form className="mt-6 grid max-w-md gap-3 rounded-xl border border-border bg-surface p-5" onSubmit={event => void signIn(event)}><h2 className="text-lg font-semibold">Hodi administrator sign in</h2><label className="grid gap-1 text-sm">Username<input className="min-h-10 rounded-lg border border-border bg-surface px-3 text-text" autoComplete="username" required value={username} onChange={event => setUsername(event.target.value)} /></label><label className="grid gap-1 text-sm">Password<input className="min-h-10 rounded-lg border border-border bg-surface px-3 text-text" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label><button className="rounded-lg bg-brand px-4 py-2 font-semibold text-brand-contrast">Sign in</button><p className="text-xs text-text-secondary">Access is restricted by the server to Hodi administrator accounts.</p></form>}
      {!summary && !error && <p className="py-8 text-text-secondary" aria-live="polite">Loading verified subscription records…</p>}
      {summary && <>
        <section className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Subscription financial summary">{metrics.map(([label, value]) => <article className="rounded-xl border border-border bg-surface p-5 shadow-soft" key={label}><p className="text-sm text-text-secondary">{label}</p><strong className="mt-2 block text-2xl">{value}</strong></article>)}</section>
        <section className="mt-8 rounded-xl border border-border bg-surface p-5"><h2 className="text-xl font-semibold">Organizations by plan and status</h2><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[420px] text-left text-sm"><thead className="text-text-secondary"><tr><th className="py-2">Plan</th><th>Status</th><th>Organizations</th></tr></thead><tbody>{summary.organizations_by_plan.map(row => <tr className="border-t border-border" key={`${row.plan__code}-${row.status}`}><td className="py-3">{row.plan__name}</td><td>{row.status.replaceAll("_", " ")}</td><td>{row.organizations}</td></tr>)}</tbody></table></div></section>
        <section className="mt-8 rounded-xl border border-border bg-surface p-5"><h2 className="text-xl font-semibold">Recent subscription activity</h2>{summary.recent_activity.length ? <ol className="mt-4 divide-y divide-border">{summary.recent_activity.map((row, index) => <li className="grid gap-1 py-3 sm:grid-cols-[1fr_auto]" key={`${row.action}-${row.created_at}-${index}`}><span>{row.action.replaceAll(".", " · ").replaceAll("_", " ")} · {row.organization ?? "Organization removed"}</span><time className="text-sm text-text-secondary">{new Date(row.created_at).toLocaleString()}</time></li>)}</ol> : <p className="mt-3 text-text-secondary">No subscription activity recorded.</p>}</section>
        <section className="mt-8 rounded-xl border border-border bg-surface p-5"><h2 className="text-xl font-semibold">Payment reports awaiting verification</h2><p className="mt-2 text-sm text-text-secondary">Verify each reference against an authoritative provider or bank record before confirming it. A customer report alone is not payment proof.</p>{reviewError && <p className="mt-3 text-error" role="alert">{reviewError}</p>}{reports.length ? <div className="mt-4 divide-y divide-border">{reports.map(report => <article className="grid gap-3 py-4" key={report.id}><div><strong>{report.organization_name} · {report.invoice_number}</strong><p className="text-sm text-text-secondary">{kes(report.amount_minor)} · reference {report.reference} · reported by {report.reported_by_name}</p></div><label className="grid gap-1 text-sm text-text-secondary">Verification or rejection reason<textarea className="min-h-20 rounded-lg border border-border bg-surface px-3 py-2 text-text" value={reviewReason[report.id] ?? ""} onChange={event => setReviewReason(current => ({ ...current, [report.id]: event.target.value }))} maxLength={1000} /></label><div className="flex flex-wrap gap-2"><button className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-contrast" onClick={() => void reviewReport(report.id, "confirm")}>Confirm verified payment</button><button className="rounded-lg border border-border px-4 py-2 text-sm font-semibold" onClick={() => void reviewReport(report.id, "reject")}>Reject report</button></div></article>)}</div> : <p className="mt-4 text-text-secondary">No reported payments need review.</p>}</section>
        <section className="mt-8 rounded-xl border border-border bg-surface p-5"><h2 className="text-xl font-semibold">Configure negotiated Enterprise terms</h2><p className="mt-2 text-sm text-text-secondary">Set approved monthly pricing and the unit limit. The subscription remains pending until payment is independently verified.</p><form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={event => void issueEnterpriseInvoice(event)}><label className="grid gap-1 text-sm">Organization<select className="min-h-10 rounded-lg border border-border bg-surface px-3" required value={enterpriseOrg} onChange={event => setEnterpriseOrg(event.target.value)}><option value="">Choose an organization</option>{organizations.map(org => <option key={org.organization} value={org.organization}>{org.organization_name} · {org.current_plan}</option>)}</select></label><label className="grid gap-1 text-sm">Monthly price (whole KES)<input className="min-h-10 rounded-lg border border-border bg-surface px-3" type="number" min="1" max="90071992547409" step="1" required value={enterpriseAmount} onChange={event => setEnterpriseAmount(event.target.value)} /></label><label className="grid gap-1 text-sm">Included rentable units<input className="min-h-10 rounded-lg border border-border bg-surface px-3" type="number" min="1" step="1" required value={enterpriseLimit} onChange={event => setEnterpriseLimit(event.target.value)} /></label><label className="grid gap-1 text-sm sm:col-span-2">Approved terms and reason<textarea className="min-h-20 rounded-lg border border-border bg-surface px-3 py-2" minLength={8} maxLength={1000} required value={enterpriseReason} onChange={event => setEnterpriseReason(event.target.value)} /></label><button className="w-fit rounded-lg bg-brand px-4 py-2 font-semibold text-brand-contrast">Issue Enterprise invoice</button></form></section>
      </>}
    </div>
  </main>;
}
