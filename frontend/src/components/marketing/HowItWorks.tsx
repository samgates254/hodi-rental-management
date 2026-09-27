import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const steps = [
  {
    title: "Set up your organization",
    body: "Create your workspace and the structure your team will operate from — clear ownership from day one.",
  },
  {
    title: "Add properties and units",
    body: "Map buildings and units so every lease, payment, and request attaches to the right place.",
  },
  {
    title: "Manage tenants and leases",
    body: "Keep tenancy context with the unit it belongs to, instead of scattering it across files and chats.",
  },
  {
    title: "Operate from one place",
    body: "Coordinate day-to-day work — rent, requests, and follow-through — against a single connected record.",
  },
] as const;

export function HowItWorks() {
  return (
    <section id="how-it-works" className="section-pad border-y border-border bg-surface">
      <Container>
        <SectionHeading
          eyebrow="How Hodi works"
          title="Four steps from setup to daily operations."
          description="Start with structure. Grow into day-to-day work. Hodi is designed to be run — not merely configured once."
        />

        <ol className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
          {steps.map((step, index) => (
            <li
              key={step.title}
              className="relative flex h-full flex-col rounded-lg border border-border bg-bg p-6"
            >
              <span
                className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-teal/30 bg-soft-teal font-display text-lg font-semibold tabular-nums text-teal"
                aria-hidden
              >
                {index + 1}
              </span>
              <span className="sr-only">Step {index + 1}</span>
              <h3 className="mt-5 text-base font-semibold tracking-tight text-charcoal">
                {step.title}
              </h3>
              <p className="mt-2.5 text-sm leading-relaxed text-text-secondary text-pretty">
                {step.body}
              </p>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}
