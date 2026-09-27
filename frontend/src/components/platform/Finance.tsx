import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const items = [
  {
    title: "Charges & rent",
    body: "Amounts owed stay tied to the lease and unit — not floating in a separate workbook.",
  },
  {
    title: "Invoices & records",
    body: "Financial documents sit with the tenancy so history is reviewable when questions arise.",
  },
  {
    title: "Payments in context",
    body: "Received payments can be recorded against the right obligations, keeping balances clearer.",
  },
  {
    title: "Operational finance",
    body: "Finance is part of running the property — visible alongside occupancy and day-to-day work.",
  },
] as const;

export function Finance() {
  return (
    <section id="finance" className="section-pad border-y border-border bg-surface">
      <Container>
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="lg:col-span-5">
            <SectionHeading
              eyebrow="Financial operations"
              title="Money stays attached to the tenancy."
              description="Hodi treats financial activity as part of the operating record. Charges, invoices, payments, and history belong with the unit and lease they relate to — so owners and managers are not reconciling from memory."
            />
            <p className="mt-5 text-sm leading-relaxed text-text-secondary text-pretty">
              Language here reflects the platform model: connected financial
              records for property operations. Specific payment rails and
              integrations depend on how your workspace is configured.
            </p>
          </div>

          <div className="lg:col-span-7">
            <div className="rounded-lg border border-border bg-bg p-5 sm:p-7">
              <p className="text-[0.6875rem] font-medium uppercase tracking-[0.08em] text-text-secondary">
                Financial record
              </p>
              <ol className="mt-5 grid gap-4 sm:grid-cols-2">
                {items.map((item, index) => (
                  <li
                    key={item.title}
                    className="relative flex min-h-full flex-col gap-4 rounded-lg border border-border bg-surface p-5"
                  >
                    <span
                      className="relative z-[1] flex h-10 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md border border-charcoal/15 bg-charcoal text-sm font-semibold tabular-nums text-white shadow-soft"
                      aria-hidden
                    >
                      {String(index + 1).padStart(2, "0")}
                      <span className="absolute inset-x-0 bottom-0 h-1 bg-teal" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-base font-semibold tracking-tight text-charcoal">
                        {item.title}
                      </h3>
                      <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-text-secondary text-pretty">
                        {item.body}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
