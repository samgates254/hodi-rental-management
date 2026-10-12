"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { clientApi, getStoredAuthToken } from "@/lib/clientApi";

type Plan = {
  code: string;
  name: string;
  description: string;
  price_minor: number | null;
  setup_fee_minor: number;
  currency: string;
  interval: string;
  unit_limit: number | null;
  is_custom_pricing: boolean;
  entitlements: Record<string, boolean>;
};

const order = ["free", "starter", "growth", "professional", "enterprise"];
const features = [
  { key: "billing", name: "Rent and billing records", detail: "Create rent invoices and keep payment records with each tenancy." },
  { key: "maintenance", name: "Maintenance workflows", detail: "Record maintenance requests and track their operational status." },
  { key: "reporting", name: "Portfolio reporting", detail: "Review the reporting workflows available in HODI." },
  { key: "staff_management", name: "Team management", detail: "Manage organization membership using the existing role permissions." },
] as const;
const formatMoney = (minor: number, currency: string) => new Intl.NumberFormat("en-KE", {
  style: "currency", currency, maximumFractionDigits: 0,
}).format(minor / 100);

export default function PricingExperience() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadPlans = useCallback(async () => {
    setLoading(true);
    setError("");
    setPlans([]);
    try {
      const result = await clientApi.get<Plan[]>("/api/v1/subscriptions/plans/");
      const available = result.data.filter((plan) => plan.code && typeof plan.setup_fee_minor === "number");
      available.sort((a, b) => (order.indexOf(a.code) < 0 ? 99 : order.indexOf(a.code)) - (order.indexOf(b.code) < 0 ? 99 : order.indexOf(b.code)));
      setPlans(available);
      setSelected((current) => available.some((plan) => plan.code === current) ? current : available.find((plan) => plan.code === "growth")?.code ?? available[0]?.code ?? "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Plans could not be loaded. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadPlans(); }, [loadPlans]);

  const chosenPlan = useMemo(() => plans.find((plan) => plan.code === selected), [plans, selected]);

  function choosePlan(plan: Plan) {
    if (plan.code === "enterprise") {
      window.location.assign("/contact");
      return;
    }
    if (plan.code === "free") {
      window.location.assign(getStoredAuthToken() ? "/landlords" : "/signup?type=landlord&plan=free");
      return;
    }
    window.location.assign(getStoredAuthToken()
      ? `/landlords?plan=${encodeURIComponent(plan.code)}#subscription`
      : `/signup?type=landlord&plan=${encodeURIComponent(plan.code)}`);
  }

  return (
    <>
      <section className="relative isolate overflow-hidden bg-[#f3f5f2] dark:bg-bg">
        <Container className="grid min-h-[480px] items-center gap-9 py-12 sm:py-16 lg:grid-cols-[0.9fr_1.1fr] lg:py-20">
          <div className="relative z-10">
            <p className="text-sm font-semibold tracking-wide text-teal">Plans for property operators</p>
            <h1 className="mt-4 max-w-xl text-balance text-4xl font-semibold leading-[1.04] tracking-[-0.045em] text-charcoal sm:text-5xl lg:text-[3.6rem]">
              More clarity in every part of your portfolio.
            </h1>
            <p className="mt-5 max-w-lg text-base leading-7 text-text-secondary sm:text-lg">
              Keep property records, rent activity, tenant information and maintenance work connected in one operating space.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Button href="#plans" size="lg">Explore plans</Button>
              <Button href="/platform" variant="secondary" size="lg">Explore HODI</Button>
            </div>
            <p className="mt-5 max-w-md text-sm leading-6 text-text-secondary">Monthly plans in KES. Paid subscriptions activate only after an authorized HODI administrator verifies payment.</p>
          </div>
          <div className="relative min-h-[300px] overflow-hidden rounded-sm bg-[#18352e] sm:min-h-[390px] lg:translate-x-5">
            <Image src="/images/hodi/apartment-building.jpg" alt="Residential apartment building in soft daylight" fill priority sizes="(max-width: 1024px) 100vw, 55vw" className="object-cover object-center" />
            <div className="absolute inset-0 bg-gradient-to-r from-[#10271f]/40 via-transparent to-transparent" aria-hidden="true" />
            <div className="absolute bottom-0 left-0 max-w-sm p-5 text-white sm:p-7">
              <span className="text-xs font-semibold uppercase tracking-[0.15em] text-white/80">One connected operation</span>
              <p className="mt-2 text-2xl font-medium leading-tight sm:text-3xl">The buildings, people and work behind a well-run portfolio.</p>
            </div>
          </div>
        </Container>
        <div className="absolute -bottom-20 left-0 -z-10 h-44 w-full bg-surface" aria-hidden="true" />
      </section>

      <section id="plans" className="scroll-mt-24 bg-surface pb-16 pt-12 sm:pb-20 sm:pt-16">
        <Container>
          <div className="grid gap-8 lg:grid-cols-[0.72fr_1.28fr] lg:items-end">
            <div>
              <p className="text-sm font-semibold text-teal">Plans and pricing</p>
              <h2 className="mt-2 max-w-md text-3xl font-semibold leading-tight tracking-[-0.035em] text-charcoal sm:text-4xl">Choose capacity that fits today.</h2>
            </div>
            <p className="max-w-2xl text-sm leading-6 text-text-secondary sm:text-base">All amounts and entitlements below come from HODI’s active plan catalogue. Unit capacity is the primary difference between plans; available tools are shown in the comparison below.</p>
          </div>

          {loading && <div className="mt-9 border-y border-border py-8 text-sm text-text-secondary" aria-live="polite">Loading current plans…</div>}
          {!loading && error && <div className="mt-9 flex flex-col items-start gap-3 border-y border-border py-6 sm:flex-row sm:items-center sm:justify-between" role="alert"><div><h3 className="font-semibold text-charcoal">Pricing is temporarily unavailable</h3><p className="mt-1 text-sm text-text-secondary">{error}</p></div><button type="button" onClick={() => void loadPlans()} className="rounded-md bg-brand px-4 py-2.5 text-sm font-semibold text-brand-contrast">Try again</button></div>}
          {!loading && !error && plans.length === 0 && <p className="mt-9 border-y border-border py-8 text-sm text-text-secondary">No plans are currently available. Contact HODI for assistance.</p>}

          {!loading && !error && plans.length > 0 && <>
            <div className="mt-8 overflow-hidden border-y border-border" role="group" aria-label="Available HODI subscription plans">
              <div className="hidden grid-cols-[1.1fr_0.8fr_1fr_1fr_1.1fr] gap-4 border-b border-border bg-bg px-4 py-3 text-xs font-semibold uppercase tracking-wide text-text-secondary md:grid">
                <span>Plan</span><span>Capacity</span><span>Monthly</span><span>One-time setup</span><span>First invoice*</span>
              </div>
              {plans.map((plan) => {
                const active = selected === plan.code;
                const monthly = plan.price_minor ?? 0;
                const firstTotal = monthly + plan.setup_fee_minor;
                const highlight = plan.code === "growth";
                return <button key={plan.code} type="button" aria-pressed={active} aria-label={`Select ${plan.name} plan`} onClick={() => setSelected(plan.code)} className={`group grid w-full gap-2 border-b border-border px-4 py-4 text-left transition-colors last:border-b-0 focus-visible:relative focus-visible:z-10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal md:grid-cols-[1.1fr_0.8fr_1fr_1fr_1.1fr] md:items-center md:gap-4 md:py-5 ${active ? "bg-soft-teal/55" : "bg-surface hover:bg-bg"}`}>
                  <span className="flex items-center gap-3"><span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border ${active ? "border-teal" : "border-border"}`}>{active && <span className="h-2.5 w-2.5 rounded-full bg-teal" />}</span><span><span className="flex items-center gap-2 font-semibold text-charcoal">{plan.name}{highlight && <span className="rounded-sm bg-brand px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-brand-contrast">Balanced capacity</span>}</span><span className="mt-1 block text-xs leading-5 text-text-secondary">{plan.description || "Property operations for your organization."}</span></span></span>
                  <span className="pl-8 text-sm text-charcoal md:pl-0"><span className="mr-2 text-xs text-text-secondary md:hidden">Units</span>{plan.is_custom_pricing ? "Negotiated" : plan.unit_limit ? `Up to ${plan.unit_limit}` : "No fixed limit"}</span>
                  <span className="pl-8 text-sm text-charcoal md:pl-0"><span className="mr-2 text-xs text-text-secondary md:hidden">Monthly</span>{plan.is_custom_pricing ? "Custom" : `${formatMoney(monthly, plan.currency)} / month`}</span>
                  <span className="pl-8 text-sm text-charcoal md:pl-0"><span className="mr-2 text-xs text-text-secondary md:hidden">One-time setup</span>{plan.is_custom_pricing ? "Agreed with HODI" : formatMoney(plan.setup_fee_minor, plan.currency)}</span>
                  <span className="pl-8 font-semibold text-charcoal md:pl-0"><span className="mr-2 text-xs font-normal text-text-secondary md:hidden">First invoice*</span>{plan.is_custom_pricing ? "Custom" : formatMoney(firstTotal, plan.currency)}</span>
                </button>;
              })}
            </div>

            {chosenPlan && <div className="mt-6 grid gap-6 border-l-2 border-teal pl-5 sm:grid-cols-[1fr_auto] sm:items-center sm:pl-6">
              <div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-teal">Selected: {chosenPlan.name}</p><p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">{chosenPlan.code === "enterprise" ? "Discuss negotiated monthly pricing, setup and unit capacity with HODI." : chosenPlan.code === "free" ? "Create a landlord account and begin with the available Free plan." : `For a new organization, the first invoice is ${formatMoney((chosenPlan.price_minor ?? 0) + chosenPlan.setup_fee_minor, chosenPlan.currency)}: ${formatMoney(chosenPlan.setup_fee_minor, chosenPlan.currency)} one-time setup plus ${formatMoney(chosenPlan.price_minor ?? 0, chosenPlan.currency)} for the first month. Later monthly invoices do not repeat the setup fee.`}</p></div>
              <button type="button" onClick={() => choosePlan(chosenPlan)} className="inline-flex min-h-11 items-center justify-center rounded-md bg-brand px-5 py-3 text-sm font-semibold text-brand-contrast transition hover:bg-[var(--hodi-brand-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--hodi-focus)]">{chosenPlan.code === "enterprise" ? "Contact HODI" : chosenPlan.code === "free" ? "Start for free" : "Continue with this plan"}</button>
            </div>}
            <p className="mt-5 text-xs leading-5 text-text-secondary">*First invoice for a new organization, before any applicable adjustments. Existing subscriptions are not retroactively charged setup fees. HODI does not collect payment automatically.</p>
          </>}
        </Container>
      </section>

      <section className="bg-[#f3f5f2] py-14 dark:bg-bg sm:py-20">
        <Container>
          <div className="max-w-xl"><p className="text-sm font-semibold text-teal">Included tools</p><h2 className="mt-2 text-3xl font-semibold tracking-[-0.035em] text-charcoal sm:text-4xl">A shared set of operating tools.</h2><p className="mt-3 text-sm leading-6 text-text-secondary">Plan capacity varies. The current catalogue controls which supported tools are included.</p></div>
          {plans.length > 0 && <div className="mt-8 overflow-x-auto border-y border-border bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal" tabIndex={0} aria-label="Scrollable plan comparison">
            <table className="w-full min-w-[700px] border-collapse text-left text-sm">
              <thead><tr className="border-b border-border bg-surface"><th scope="col" className="px-4 py-4 font-semibold text-charcoal">Capability</th>{plans.map(plan => <th key={plan.code} scope="col" className={`px-4 py-4 font-semibold text-charcoal ${plan.code === "growth" ? "bg-soft-teal/45" : ""}`}>{plan.name}</th>)}</tr></thead>
              <tbody>
                <tr className="border-b border-border"><th scope="row" className="px-4 py-4 font-medium text-charcoal">Rentable unit limit</th>{plans.map(plan => <td key={plan.code} className={`px-4 py-4 text-text-secondary ${plan.code === "growth" ? "bg-soft-teal/45" : ""}`}>{plan.is_custom_pricing ? "Negotiated" : plan.unit_limit ? `Up to ${plan.unit_limit}` : "No fixed limit"}</td>)}</tr>
                {features.map(feature => <tr key={feature.key} className="border-b border-border last:border-0"><th scope="row" className="px-4 py-4 font-medium text-charcoal">{feature.name}<span className="mt-1 block max-w-sm text-xs font-normal leading-5 text-text-secondary">{feature.detail}</span></th>{plans.map(plan => <td key={plan.code} className={`px-4 py-4 ${plan.code === "growth" ? "bg-soft-teal/45" : ""}`}><span className={plan.entitlements[feature.key] ? "font-medium text-teal" : "text-text-secondary"}>{plan.entitlements[feature.key] ? "Included" : "Not included"}</span></td>)}</tr>)}
              </tbody>
            </table>
          </div>}
          <p className="mt-4 text-xs text-text-secondary">Team permissions are governed by organization roles. The plan limit counts active rentable units through Building → Property → Organization; tenants, staff, buildings and properties are not units.</p>
        </Container>
      </section>

      <section className="bg-surface py-14 sm:py-20">
        <Container className="grid items-center gap-9 lg:grid-cols-[0.84fr_1.16fr] lg:gap-16">
          <div className="relative aspect-[5/4] overflow-hidden bg-[#d9e2dc]"><Image src="/images/hodi/property-exterior.jpg" alt="A residential property exterior" fill sizes="(max-width: 1024px) 100vw, 40vw" className="object-cover" /></div>
          <div><p className="text-sm font-semibold text-teal">Clear capacity, lasting access</p><h2 className="mt-2 max-w-lg text-3xl font-semibold leading-tight tracking-[-0.035em] text-charcoal sm:text-4xl">What happens when you reach your unit limit?</h2><p className="mt-4 text-sm leading-6 text-text-secondary sm:text-base">HODI prevents adding more billable units until your plan or negotiated allowance changes. Your existing properties, tenancy details, invoices and financial records remain available.</p><p className="mt-3 text-sm leading-6 text-text-secondary sm:text-base">Inactive units do not count toward the plan limit. Buildings, tenants and team members are not counted as rentable units.</p><a href="/platform" className="mt-5 inline-flex font-semibold text-teal underline decoration-teal/40 underline-offset-4 hover:decoration-teal">See how the platform is structured</a></div>
        </Container>
      </section>

      <section className="border-y border-border bg-[#f3f5f2] py-14 dark:bg-bg sm:py-20">
        <Container>
          <div className="max-w-xl"><p className="text-sm font-semibold text-teal">A practical start</p><h2 className="mt-2 text-3xl font-semibold tracking-[-0.035em] text-charcoal sm:text-4xl">Set up your portfolio at your pace.</h2></div>
          <ol className="mt-8 grid gap-7 sm:grid-cols-2 lg:grid-cols-4">
            {[["01", "Create an account", "Set up your landlord organization in HODI."], ["02", "Add property and units", "Build your portfolio using the property structure."], ["03", "Invite your team", "Add the people who need organization access."], ["04", "Run your workflows", "Keep rent records and maintenance work together; review plan capacity as you grow."]].map(([number, title, body]) => <li key={number} className="border-t border-teal pt-4"><span className="font-mono text-xs font-semibold text-teal">{number}</span><h3 className="mt-3 font-semibold text-charcoal">{title}</h3><p className="mt-2 text-sm leading-6 text-text-secondary">{body}</p></li>)}
          </ol>
        </Container>
      </section>

      <section className="bg-surface py-14 sm:py-20">
        <Container className="max-w-4xl">
          <p className="text-sm font-semibold text-teal">Plan and billing questions</p><h2 className="mt-2 text-3xl font-semibold tracking-[-0.035em] text-charcoal sm:text-4xl">The important details, plainly answered.</h2>
          <div className="mt-7 divide-y divide-border border-y border-border">
            {[["What is a unit?", "One rentable Unit under a Building and Property connected to your organization. Inactive units are excluded. HODI does not count buildings, tenants or staff as units."], ["Can I start with Free?", "Yes. Select Free to create a landlord account. HODI assigns the available Free plan to the organization; it does not create a paid subscription invoice."], ["What happens at the unit limit?", "You can continue to access existing records. HODI prevents adding more billable units until the allowance changes."], ["How does a paid plan become active?", "Request a plan in the landlord subscription area. HODI issues a subscription invoice separately from rent. After paying through the instructions supplied by HODI, submit the reference for authorized staff to verify."], ["Is the setup fee recurring?", "No. When configured, it is shown as a separate one-time line on the first paid invoice. It is not included on ordinary later monthly invoices. Existing subscriptions are grandfathered from newly configured setup fees."], ["Does reporting a payment activate my plan?", "No. A payment reference remains pending until an authorized HODI administrator independently verifies it. HODI does not automatically collect subscription payments."], ["Can I upgrade later?", "Owners and property managers can request a plan change from the subscription area. A paid plan remains pending until the invoice payment is verified."], ["How can I discuss Enterprise?", "Contact HODI to discuss custom pricing and a negotiated unit limit. Sending a contact request does not create an Enterprise agreement."]].map(([question, answer]) => <details key={question} className="group py-5"><summary className="flex cursor-pointer list-none items-center justify-between gap-5 font-semibold text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal"><span>{question}</span><span className="text-xl font-normal text-teal transition-transform group-open:rotate-45" aria-hidden="true">+</span></summary><p className="mt-3 max-w-3xl text-sm leading-6 text-text-secondary">{answer}</p></details>)}
          </div>
          <div className="mt-9 flex flex-col gap-4 border-l-2 border-teal bg-bg px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7"><div><h3 className="font-semibold text-charcoal">Ready to manage with more clarity?</h3><p className="mt-1 text-sm text-text-secondary">Start with a plan that fits the portfolio you have today.</p></div><div className="flex flex-wrap gap-3"><Button href="/signup?type=landlord">Create an account</Button><Button href="/contact" variant="secondary">Contact HODI</Button></div></div>
        </Container>
      </section>
    </>
  );
}
