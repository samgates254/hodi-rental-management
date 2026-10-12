"use client";

import Image from "next/image";
import { useCallback, useEffect, useState } from "react";
import { clientApi, getStoredAuthToken } from "@/lib/clientApi";
import { Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";

type Plan = {
  code: string;
  name: string;
  description: string;
  price_minor: number | null;
  currency: string;
  interval: string;
  unit_limit: number | null;
  entitlements: Record<string, boolean>;
  is_custom_pricing: boolean;
};

const featureRows = [
  { key: "billing", label: "Rent invoicing and payment records", detail: "Keep tenant charges and recorded payments together." },
  { key: "maintenance", label: "Maintenance workflows", detail: "Track requests and their operational progress." },
  { key: "reporting", label: "Portfolio reporting", detail: "Review property and rent operations in the landlord workspace." },
  { key: "staff_management", label: "Team management", detail: "Invite and manage organization staff where supported." },
] as const;

const audience: Record<string, string> = {
  free: "For landlords getting their records in order.",
  starter: "For a growing set of homes and tenants.",
  growth: "For established portfolios that need more unit capacity.",
  professional: "For larger portfolios working within a higher unit allowance.",
  enterprise: "For organizations that need negotiated terms and capacity.",
};

const planOrder = ["free", "starter", "growth", "professional", "enterprise"];

const money = (minor: number, currency: string) => new Intl.NumberFormat("en-KE", {
  style: "currency", currency, maximumFractionDigits: 0,
}).format(minor / 100);

function planHref(plan: Plan) {
  if (plan.code === "enterprise") return "/contact";
  if (plan.code === "free") return "/signup?type=landlord";
  return `/signup?type=landlord&plan=${encodeURIComponent(plan.code)}`;
}

export default function PricingExperience() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadPlans = useCallback(async () => {
    setLoading(true);
    setError("");
    setPlans([]);
    try {
      const response = await clientApi.get<Plan[]>("/api/v1/subscriptions/plans/");
      setPlans([...response.data].sort((left, right) => {
        const leftIndex = planOrder.indexOf(left.code);
        const rightIndex = planOrder.indexOf(right.code);
        return (leftIndex < 0 ? planOrder.length : leftIndex) - (rightIndex < 0 ? planOrder.length : rightIndex) || left.name.localeCompare(right.name);
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Plans could not be loaded. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadPlans(); }, [loadPlans]);

  function selectPlan(plan: Plan) {
    if (plan.code === "enterprise") {
      window.location.assign("/contact");
      return;
    }
    if (plan.code === "free") {
      window.location.assign(getStoredAuthToken() ? "/landlords" : "/signup?type=landlord");
      return;
    }
    const destination = getStoredAuthToken()
      ? `/landlords?plan=${encodeURIComponent(plan.code)}#subscription`
      : planHref(plan);
    window.location.assign(destination);
  }

  return (
    <>
      <section className="relative overflow-hidden border-b border-border bg-bg">
        <Container className="grid items-center gap-10 py-12 sm:py-16 lg:grid-cols-[0.92fr_1.08fr] lg:gap-16 lg:py-20">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal">Plans for property operators</p>
            <h1 className="mt-5 max-w-2xl font-display text-4xl font-semibold leading-[1.08] tracking-[-0.03em] text-charcoal text-balance sm:text-5xl lg:text-[3.65rem]">
              Property management that grows with you.
            </h1>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-text-secondary sm:text-lg">
              Bring properties, rentable units, tenant records, rent activity and maintenance work into one connected place. Start with the portfolio you have; choose more room as it grows.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button href="#plans" size="lg">Compare plans</Button>
              <Button href="/contact" variant="secondary" size="lg">Talk to Hodi</Button>
            </div>
            <p className="mt-5 text-sm text-text-secondary">Monthly plans in KES. Paid plans become active after Hodi verifies payment.</p>
          </div>
          <div className="relative min-h-[300px] overflow-hidden rounded-xl border border-border bg-surface shadow-soft sm:min-h-[390px]">
            <Image
              src="/images/hodi/apartment-building.jpg"
              alt="Contemporary multi-unit residential building"
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 54vw"
              className="object-cover object-center"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-[#09131c]/65 via-[#09131c]/5 to-transparent" aria-hidden="true" />
            <div className="absolute inset-x-0 bottom-0 p-5 text-white sm:p-7">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/75">One operating picture</p>
              <p className="mt-2 max-w-sm font-display text-2xl font-medium leading-tight sm:text-3xl">The property, the people, and the work around it.</p>
            </div>
          </div>
        </Container>
      </section>

      <section id="plans" className="scroll-mt-24 bg-surface py-14 sm:py-20">
        <Container>
          <div className="mx-auto max-w-2xl text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal">Straightforward monthly plans</p>
            <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-charcoal sm:text-4xl">Choose the right room for your portfolio</h2>
            <p className="mt-4 text-base leading-relaxed text-text-secondary">Every plan includes the core Hodi property operations. The plan sets your included rentable-unit capacity.</p>
          </div>

          {loading && <div className="mt-10 rounded-xl border border-border bg-bg p-8 text-center text-text-secondary" aria-live="polite">Loading current plans…</div>}
          {!loading && error && <div className="mx-auto mt-10 max-w-xl rounded-xl border border-[color:color-mix(in_srgb,var(--hodi-error)_30%,transparent)] bg-[var(--hodi-error-soft)] p-6 text-center" role="alert"><p className="font-semibold text-charcoal">Pricing is temporarily unavailable</p><p className="mt-2 text-sm text-text-secondary">{error}</p><button type="button" onClick={() => void loadPlans()} className="mt-4 rounded-md bg-brand px-4 py-2 text-sm font-semibold text-brand-contrast">Try again</button></div>}
          {!loading && !error && plans.length === 0 && <p className="mt-10 text-center text-text-secondary">There are no plans available at this time. Please contact Hodi for assistance.</p>}

          {!loading && !error && plans.length > 0 && <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {plans.map(plan => (
              <article key={plan.code} className={`flex min-w-0 flex-col border bg-bg p-5 sm:p-6 ${plan.code === "growth" ? "border-teal/60 shadow-soft" : "border-border"}`}>
                <div className="flex min-h-7 items-center justify-between gap-2">
                  <h3 className="font-display text-xl font-semibold text-charcoal">{plan.name}</h3>
                  {plan.is_custom_pricing && <span className="text-[0.65rem] font-semibold uppercase tracking-wider text-teal">Tailored</span>}
                </div>
                <p className="mt-3 min-h-10 text-sm leading-relaxed text-text-secondary">{audience[plan.code] ?? plan.description}</p>
                <p className="mt-5 min-h-[3.25rem] text-charcoal">
                  {plan.is_custom_pricing ? <span className="text-2xl font-semibold">Custom</span> : <><span className="text-2xl font-semibold tracking-tight">{money(plan.price_minor ?? 0, plan.currency)}</span><span className="ml-1 text-xs text-text-secondary">/ month</span></>}
                </p>
                <div className="mt-4 border-y border-border py-3">
                  <p className="text-xs uppercase tracking-wide text-text-secondary">Rentable units</p>
                  <p className="mt-1 text-sm font-semibold text-charcoal">{plan.unit_limit ? `Up to ${plan.unit_limit}` : "Negotiated limit"}</p>
                </div>
                <ul className="mt-4 flex-1 space-y-2.5 text-sm text-text-secondary">
                  {featureRows.filter(row => plan.entitlements[row.key]).map(row => <li className="flex gap-2" key={row.key}><span className="text-teal" aria-hidden="true">✓</span><span>{row.label}</span></li>)}
                  {featureRows.every(row => !plan.entitlements[row.key]) && <li>Contact Hodi to discuss included capabilities.</li>}
                </ul>
                <button type="button" data-plan-code={plan.code} onClick={() => selectPlan(plan)} className={`mt-6 inline-flex min-h-11 w-full items-center justify-center rounded-md px-4 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--hodi-focus)] ${plan.code === "growth" ? "bg-brand text-brand-contrast hover:bg-[var(--hodi-brand-hover)]" : "border border-border bg-surface text-charcoal hover:border-teal hover:text-teal"}`}>
                  {plan.code === "enterprise" ? "Contact us" : plan.code === "free" ? "Start for free" : "Choose this plan"}
                </button>
              </article>
            ))}
          </div>}
          <p className="mt-5 text-center text-xs leading-relaxed text-text-secondary">Prices are the current proposed monthly catalogue amounts and are confirmed by Hodi when a subscription invoice is issued.</p>
        </Container>
      </section>

      <section className="border-y border-border bg-bg py-14 sm:py-20">
        <Container>
          <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
            <div className="max-w-xl"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal">Included capabilities</p><h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-charcoal sm:text-4xl">The core tools stay connected</h2></div>
            <p className="max-w-md text-sm leading-relaxed text-text-secondary">Current active plans include the enabled capabilities shown below. Capacity changes by plan; features only appear when enabled in Hodi’s plan catalogue.</p>
          </div>
          {plans.length > 0 && <div className="mt-8 overflow-x-auto rounded-lg border border-border bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal" tabIndex={0} aria-label="Scrollable plan feature comparison">
            <table className="w-full min-w-[760px] border-collapse text-left text-sm">
              <thead><tr className="border-b border-border bg-bg"><th scope="col" className="w-[30%] px-4 py-4 font-semibold text-charcoal sm:px-5">Capability</th>{plans.map(plan => <th key={plan.code} scope="col" className="px-3 py-4 font-semibold text-charcoal sm:px-4">{plan.name}</th>)}</tr></thead>
              <tbody>
                <tr className="border-b border-border"><th scope="row" className="px-4 py-4 font-medium text-charcoal sm:px-5">Included rentable units</th>{plans.map(plan => <td key={plan.code} className="px-3 py-4 text-text-secondary sm:px-4">{plan.unit_limit ? `Up to ${plan.unit_limit}` : "Negotiated"}</td>)}</tr>
                {featureRows.map(row => <tr key={row.key} className="border-b border-border last:border-0"><th scope="row" className="px-4 py-4 font-medium text-charcoal sm:px-5"><span className="block">{row.label}</span><span className="mt-1 block max-w-xs text-xs font-normal leading-relaxed text-text-secondary">{row.detail}</span></th>{plans.map(plan => <td key={plan.code} className="px-3 py-4 sm:px-4"><span className={plan.entitlements[row.key] ? "font-semibold text-teal" : "text-text-secondary"}>{plan.entitlements[row.key] ? "Included" : "—"}</span></td>)}</tr>)}
              </tbody>
            </table>
          </div>}
          <p className="mt-4 text-xs text-text-secondary">Staff roles and organization access remain governed by your organization permissions.</p>
        </Container>
      </section>

      <section className="bg-surface py-14 sm:py-20">
        <Container className="grid items-center gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
          <div className="relative aspect-[4/3] overflow-hidden rounded-lg border border-border bg-bg">
            <Image src="/images/hodi/property-exterior.jpg" alt="Contemporary residential property exterior" fill sizes="(max-width: 1024px) 100vw, 42vw" className="object-cover object-center" />
          </div>
          <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal">A clear measure of portfolio size</p><h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-charcoal sm:text-4xl">What counts as a unit?</h2><p className="mt-5 text-base leading-relaxed text-text-secondary">Hodi counts rentable units through the existing Building → Property → Organization structure. Inactive units are excluded. Buildings, staff and tenants are not counted as units.</p><p className="mt-4 text-base leading-relaxed text-text-secondary">When you reach your plan limit, Hodi prevents adding more billable units until your plan or negotiated allowance changes. Your existing property, tenancy and financial records remain available.</p><a href="/platform" className="mt-6 inline-flex font-semibold text-teal underline decoration-teal/40 underline-offset-4 hover:decoration-teal">See how Hodi brings operations together</a></div>
        </Container>
      </section>

      <section className="border-y border-border bg-bg py-14 sm:py-20">
        <Container>
          <div className="mx-auto max-w-2xl text-center"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal">Getting started</p><h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-charcoal sm:text-4xl">Start with the work you already do</h2></div>
          <ol className="mt-10 grid gap-4 md:grid-cols-4">
            {[
              ["01", "Create your account", "Set up your landlord organization in Hodi."],
              ["02", "Add property and units", "Build your portfolio using Hodi’s property structure."],
              ["03", "Bring in your team", "Invite relevant staff through organization management."],
              ["04", "Run your operations", "Work with rent records and maintenance, then review plan capacity as your portfolio grows."],
            ].map(([number, title, body]) => <li key={number} className="border-t-2 border-teal bg-surface p-5 sm:p-6"><span className="font-mono text-xs font-semibold text-teal">{number}</span><h3 className="mt-4 font-semibold text-charcoal">{title}</h3><p className="mt-2 text-sm leading-relaxed text-text-secondary">{body}</p></li>)}
          </ol>
          <p className="mt-6 text-center text-sm text-text-secondary">Reach your unit allowance? Review an upgrade in the landlord subscription area. Existing records stay available.</p>
        </Container>
      </section>

      <section className="bg-surface py-14 sm:py-20">
        <Container className="max-w-4xl">
          <div className="max-w-xl"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal">Good to know</p><h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-charcoal sm:text-4xl">Pricing questions, answered</h2></div>
          <div className="mt-8 divide-y divide-border border-y border-border">
            {[
              ["Can I start with the Free plan?", "Yes. The Free plan supports up to five active rentable units. Create a landlord account and Hodi starts your organization on its available free plan."],
              ["What happens at my unit limit?", "You can continue to access your existing records. Hodi blocks creation of additional billable units until your plan allowance is increased or changed."],
              ["How does a paid plan become active?", "Choose a paid plan from the subscription area to request an invoice. Follow Hodi’s payment instructions, then submit the payment reference. An authorized Hodi administrator verifies it before activation."],
              ["Does choosing a plan or reporting payment activate it?", "No. A plan request creates a subscription invoice, and a submitted payment reference is only a report. Activation happens only after server-side verification by authorized Hodi staff."],
              ["Is Hodi subscription billing part of tenant rent?", "No. Hodi software subscription invoices are separate from rent invoices that landlords issue to tenants."],
              ["Can I upgrade later?", "Yes. Owners and property managers can request an available plan change in the landlord subscription panel. Any paid change remains pending until its payment is verified."],
              ["How do I discuss Enterprise?", "Use the contact form to talk with Hodi about negotiated pricing and a unit limit. An Enterprise plan is not created just by submitting the form."],
            ].map(([question, answer]) => <details key={question} className="group py-5"><summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal"><span>{question}</span><span className="text-xl text-teal transition-transform group-open:rotate-45" aria-hidden="true">+</span></summary><p className="mt-3 max-w-3xl pr-8 text-sm leading-relaxed text-text-secondary">{answer}</p></details>)}
          </div>
          <div className="mt-10 flex flex-col items-start justify-between gap-4 border border-border bg-bg p-5 sm:flex-row sm:items-center sm:p-6"><div><h3 className="font-semibold text-charcoal">Ready to bring your portfolio together?</h3><p className="mt-1 text-sm text-text-secondary">Compare the current plans or speak with Hodi about your setup.</p></div><div className="flex flex-wrap gap-3"><Button href="/signup?type=landlord">Create an account</Button><Button href="/contact" variant="secondary">Contact Hodi</Button></div></div>
        </Container>
      </section>
    </>
  );
}
