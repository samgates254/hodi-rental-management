import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const steps = [
  {
    actor: "Tenant",
    action: "Reports an issue from their home",
    note: "The request starts with the person who lives there",
  },
  {
    actor: "Hodi",
    action: "Attaches it to the unit and tenancy",
    note: "Property, unit, and tenant stay linked",
  },
  {
    actor: "Manager",
    action: "Reviews and assigns the work",
    note: "Context travels with the assignment",
  },
  {
    actor: "Technician",
    action: "Completes the repair",
    note: "Progress stays on the request",
  },
  {
    actor: "Property",
    action: "The outcome returns to the record",
    note: "History remains on the unit",
  },
];

export function SolutionsFlow() {
  return (
    <section id="flow" className="section-pad bg-surface">
      <Container>
        <div className="grid gap-12 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-4">
            <SectionHeading
              eyebrow="Operational flow"
              title="One event. One continuous thread."
              description="When something happens in a home, Hodi keeps the path intact — from the person who reported it to the record that remains."
            />
            <p className="mt-8 max-w-sm border-l-2 border-[#c6a66b] pl-4 text-sm leading-relaxed text-text-secondary">
              Request in. Work assigned. Progress tracked. Outcome recorded.
            </p>
          </div>

          <div className="lg:col-span-8">
            <ol className="relative space-y-0 border border-border bg-bg">
              {steps.map((step, index) => (
                <li
                  key={step.actor}
                  className="grid gap-4 border-b border-border px-5 py-5 last:border-b-0 sm:grid-cols-[7rem_1fr] sm:gap-6 sm:px-6 sm:py-6"
                >
                  <div className="flex items-start gap-3 sm:block">
                    <span className="font-mono text-[11px] text-text-secondary">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#a8874f] sm:mt-2">
                      {step.actor}
                    </p>
                  </div>
                  <div>
                    <p className="text-base font-medium tracking-tight text-charcoal sm:text-lg">
                      {step.action}
                    </p>
                    <p className="mt-1.5 text-sm text-text-secondary">
                      {step.note}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </Container>
    </section>
  );
}
