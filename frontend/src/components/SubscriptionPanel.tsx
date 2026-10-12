"use client";

import { useCallback, useEffect, useState } from "react";
import { ClientApiError, clientApi } from "@/lib/clientApi";

type Plan = {
  code: string;
  name: string;
  description: string;
  price_minor: number | null;
  currency: string;
  interval: string;
  unit_limit: number | null;
  is_custom_pricing: boolean;
  entitlements: Record<string, boolean>;
};
type SubscriptionInvoice = {
  id: string;
  invoice_number: string;
  plan_name: string;
  amount_minor: number;
  currency: string;
  period_start: string;
  period_end: string;
  due_date: string;
  status: string;
  payment_reference: string | null;
  payment_review_status: string | null;
};
type Subscription = {
  organization: number;
  plan: Plan;
  pending_plan: Plan | null;
  status: string;
  current_period_start: string | null;
  current_period_end: string | null;
  effective_unit_limit: number | null;
  unit_count: number;
  remaining_units: number | null;
  effective_entitlements: Record<string, boolean>;
  invoices: SubscriptionInvoice[];
};

const money = (minor: number, currency: string) => new Intl.NumberFormat("en-KE", {
  style: "currency", currency, maximumFractionDigits: 0,
}).format(minor / 100);

export default function SubscriptionPanel({ organizationId, canManage }: { organizationId: string; canManage: boolean }) {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [reference, setReference] = useState("");
  const [selectedPlan, setSelectedPlan] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!organizationId) return;
    setError("");
    try {
      const [current, catalogue] = await Promise.all([
        clientApi.get<Subscription>("/api/v1/subscriptions/organization/", { params: { organization: organizationId } }),
        clientApi.get<Plan[]>("/api/v1/subscriptions/plans/"),
      ]);
      setSubscription(current.data);
      setPlans(catalogue.data);
      const requestedPlan = new URLSearchParams(window.location.search).get("plan");
      const requestedPlanIsAvailable = requestedPlan && catalogue.data.some(plan => plan.code === requestedPlan && plan.code !== "free" && !plan.is_custom_pricing);
      setSelectedPlan(current.data.pending_plan?.code ?? (requestedPlanIsAvailable ? requestedPlan : ""));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Subscription details could not be loaded.");
    }
  }, [organizationId]);

  useEffect(() => { void load(); }, [load]);

  async function changePlan() {
    if (!selectedPlan) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await clientApi.post<SubscriptionInvoice>("/api/v1/subscriptions/organization/", {
        organization: organizationId, plan: selectedPlan,
      });
      setNotice(`Invoice ${result.data.invoice_number} issued. Report its payment reference after you pay; Hodi will verify it before activating the plan.`);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The plan request could not be created.");
    } finally { setBusy(false); }
  }

  async function reportPayment(invoiceId: string) {
    if (!reference.trim()) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/subscriptions/invoices/${invoiceId}/report-payment/`, { reference: reference.trim() });
      setNotice("Payment reference submitted for administrator verification. Your plan will update after it is verified.");
      setReference("");
      await load();
    } catch (cause) {
      setError(cause instanceof ClientApiError ? cause.message : cause instanceof Error ? cause.message : "Payment reference could not be submitted.");
    } finally { setBusy(false); }
  }

  return (
    <section id="subscription" className="landlord-section" aria-labelledby="subscription-title">
      <div className="landlord-section-heading">
        <div><span className="landlord-eyebrow">HODI SOFTWARE PLAN</span><h2 id="subscription-title">Subscription</h2></div>
      </div>
      {error && <p className="landlord-alert" role="alert">{error}</p>}
      {notice && <p className="landlord-alert landlord-subscription-notice" role="status">{notice}</p>}
      {!subscription ? <div className="landlord-empty-state" aria-live="polite">Loading subscription…</div> : (
        <div className="landlord-subscription-grid">
          <article className="landlord-subscription-card">
            <div className="landlord-subscription-card-heading"><div><span className="landlord-eyebrow">CURRENT PLAN</span><h3>{subscription.plan.name}</h3></div><span className={`landlord-subscription-status status-${subscription.status.toLowerCase()}`}>{subscription.status.replaceAll("_", " ")}</span></div>
            <p>{subscription.plan.is_custom_pricing ? "Negotiated pricing" : `${money(subscription.plan.price_minor ?? 0, subscription.plan.currency)} / month`}</p>
            <p className="landlord-form-note">{subscription.current_period_end ? `Current period ends ${subscription.current_period_end}.` : "No paid billing period is active."}</p>
            <div className="landlord-subscription-usage"><span>Rentable units</span><strong>{subscription.unit_count} / {subscription.effective_unit_limit ?? "Negotiated"}</strong></div>
            {subscription.remaining_units !== null && <p className="landlord-form-note">{subscription.remaining_units} unit{subscription.remaining_units === 1 ? "" : "s"} remaining on this plan.</p>}
            {subscription.pending_plan && <p className="landlord-subscription-pending">Plan change to {subscription.pending_plan.name} is awaiting verified payment.</p>}
            <ul className="landlord-subscription-features">{Object.entries(subscription.effective_entitlements).filter(([, enabled]) => enabled).map(([key]) => <li key={key}>{key.replaceAll("_", " ")}</li>)}</ul>
          </article>
          <article className="landlord-subscription-card">
            <span className="landlord-eyebrow">AVAILABLE PLANS</span><h3>Choose a plan</h3>
            <p className="landlord-form-note">Plan changes take effect only after Hodi verifies payment. Prices shown are draft launch proposals. Contact Hodi for payment instructions; this application does not initiate or verify a payment provider transaction.</p>
            {canManage ? <div className="landlord-subscription-upgrade">
              <label htmlFor="subscription-plan">Plan</label>
              <select id="subscription-plan" value={selectedPlan} onChange={event => setSelectedPlan(event.target.value)}>
                <option value="">Select a plan</option>
                {plans.filter(plan => plan.code !== "free" && (
                  plan.code !== subscription.plan.code || subscription.status !== "ACTIVE" ||
                  !subscription.current_period_end || subscription.current_period_end <= new Date().toISOString().slice(0, 10)
                )).map(plan => <option key={plan.code} value={plan.code}>{plan.name} · {plan.is_custom_pricing ? "Contact Hodi" : `${money(plan.price_minor ?? 0, plan.currency)} / month`}</option>)}
              </select>
              {selectedPlan === "enterprise" ? <p className="landlord-form-note">Enterprise includes negotiated pricing and unit limits. Contact Hodi to configure it.</p> : <button className="landlord-button landlord-button--primary" type="button" disabled={!selectedPlan || busy || Boolean(subscription.pending_plan)} onClick={() => void changePlan()}>{busy ? "Working…" : "Request plan and issue invoice"}</button>}
            </div> : <p className="landlord-form-note">Only organization owners and property managers can request a plan change.</p>}
          </article>
          <article className="landlord-subscription-card landlord-subscription-invoices">
            <span className="landlord-eyebrow">HODI BILLING</span><h3>Subscription invoices</h3>
            {subscription.invoices.length ? <div className="landlord-subscription-invoice-list">{subscription.invoices.map(invoice => <div className="landlord-subscription-invoice" key={invoice.id}>
              <div><strong>{invoice.invoice_number}</strong><span>{invoice.plan_name} · {invoice.period_start} to {invoice.period_end} · due {invoice.due_date}</span><b>{money(invoice.amount_minor, invoice.currency)} · {invoice.status.replaceAll("_", " ")}</b>{invoice.payment_reference && <span>Reported reference: {invoice.payment_reference}</span>}</div>
              {invoice.payment_review_status === "PENDING_REVIEW" && <span className="text-text-secondary">Payment report awaiting Hodi verification.</span>}
              {invoice.payment_review_status === "REJECTED" && <span className="text-error">Reported reference was not verified. Submit a new reference after checking payment details.</span>}
              {canManage && invoice.status !== "PAID" && invoice.status !== "VOID" && invoice.payment_review_status !== "PENDING_REVIEW" && <form onSubmit={event => { event.preventDefault(); void reportPayment(invoice.id); }}><label className="sr-only" htmlFor={`reference-${invoice.id}`}>Payment reference</label><input id={`reference-${invoice.id}`} value={reference} onChange={event => setReference(event.target.value)} placeholder="Payment reference" maxLength={100} required /><button className="landlord-button" disabled={busy}>Submit for verification</button></form>}
            </div>)}</div> : <p className="landlord-form-note">No subscription invoices have been issued.</p>}
          </article>
        </div>
      )}
    </section>
  );
}
