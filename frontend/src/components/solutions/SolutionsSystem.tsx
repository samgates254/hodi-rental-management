import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const chain = [
  { label: "Property", sample: "The site" },
  { label: "Building", sample: "A block" },
  { label: "Unit", sample: "A unit" },
  { label: "Tenant", sample: "Not entered" },
  { label: "Lease", sample: "Not entered" },
  { label: "Request", sample: "None in this preview" },
  { label: "Work", sample: "None in this preview" },
  { label: "Outcome", sample: "None in this preview" },
];

export function SolutionsSystem() {
  return (
    <section id="one-system" className="section-pad bg-surface">
      <Container>
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="lg:col-span-5 lg:sticky lg:top-28">
            <SectionHeading
              eyebrow="One property thread"
              title="Everything stays attached to the property."
              description="Not another inbox. A single operating record where structure, tenancy, requests, and work share the same spine."
            />
            <p className="mt-6 max-w-md text-sm leading-relaxed text-text-secondary">
              When rent, maintenance, and people all reference the same unit and
              lease, managers stop reconstructing context — and owners see what
              actually happened.
            </p>
          </div>

          <div className="lg:col-span-7">
            <div className="border border-border border-l-[3px] border-l-teal bg-surface shadow-[0_20px_50px_-30px_rgba(25,32,42,0.28)]">
              <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border bg-bg px-5 py-4 sm:px-6">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-secondary">
                    Operating record
                  </p>
                  <p className="mt-1 text-sm font-medium text-charcoal">
                    One property thread
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className="size-1.5 shrink-0 rounded-full bg-teal"
                    aria-hidden
                  />
                  <p className="text-[11px] text-text-secondary">
                    Illustrative structure
                  </p>
                </div>
              </div>

              <ol className="divide-y divide-border">
                {chain.map((step, index) => {
                  const isActive = step.label === "Request";
                  return (
                    <li
                      key={step.label}
                      className={`grid grid-cols-[2.5rem_1fr_auto] items-center gap-3 px-5 py-3.5 sm:grid-cols-[3rem_1fr_auto] sm:gap-4 sm:px-6 sm:py-4 ${
                        isActive ? "bg-soft-teal/60" : ""
                      }`}
                    >
                      <span
                        className={`font-mono text-[11px] tabular-nums ${
                          isActive ? "text-teal" : "text-text-secondary"
                        }`}
                      >
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium tracking-tight text-charcoal">
                          {step.label}
                        </p>
                      </div>
                      <p
                        className={`truncate text-right font-mono text-xs sm:text-[13px] ${
                          isActive ? "text-charcoal" : "text-text-secondary"
                        }`}
                      >
                        {step.sample}
                      </p>
                    </li>
                  );
                })}
              </ol>

              <div className="border-t border-border bg-bg px-5 py-4 sm:px-6">
                <p className="text-xs leading-relaxed text-text-secondary text-pretty sm:text-sm">
                  Every step stays attached to the property. That is the
                  difference — not more features, fewer broken threads.
                </p>
              </div>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
