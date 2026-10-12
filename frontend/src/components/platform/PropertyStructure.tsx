import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const levels = [
  {
    label: "Property",
    detail: "The site or portfolio asset you operate.",
    sample: "Westlands Court",
  },
  {
    label: "Building",
    detail: "Blocks or structures within the property.",
    sample: "Block B",
  },
  {
    label: "Unit",
    detail: "The rentable space — where tenancy and work attach.",
    sample: "Unit B-12",
  },
] as const;

export function PropertyStructure() {
  return (
    <section id="property" className="section-pad border-y border-border bg-surface">
      <Container>
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="lg:col-span-5">
            <SectionHeading
              eyebrow="Property structure"
              title="Organize the place before you run the work."
              description="Hodi starts with a clear property hierarchy. When units sit under the right building and property, leases, payments, and requests inherit context instead of being re-explained every time."
            />
          </div>

          <div className="lg:col-span-7">
            <div className="rounded-lg border border-border bg-bg p-5 sm:p-7">
              <p className="text-[0.6875rem] font-medium uppercase tracking-[0.08em] text-text-secondary">
                Structure
              </p>
              <ol className="mt-5 space-y-0">
                {levels.map((level, index) => (
                  <li key={level.label} className="relative flex gap-4 pb-8 last:pb-0">
                    {index < levels.length - 1 ? (
                      <span
                        className="absolute left-[15px] top-9 bottom-0 w-px bg-border"
                        aria-hidden
                      />
                    ) : null}
                    <span
                      className="relative z-[1] flex h-10 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md border border-charcoal/15 bg-contrast-surface text-sm font-semibold tabular-nums text-white shadow-soft"
                      aria-hidden
                    >
                      {index + 1}
                      <span className="absolute inset-x-0 bottom-0 h-1 bg-teal" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1 pt-0.5">
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <h3 className="text-base font-semibold tracking-tight text-charcoal">
                          {level.label}
                        </h3>
                        <span className="rounded border border-border bg-surface px-2 py-0.5 font-mono text-xs text-text-secondary">
                          {level.sample}
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">
                        {level.detail}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
              <p className="mt-2 border-t border-border pt-5 text-sm leading-relaxed text-text-secondary text-pretty">
                Everything below — tenancy, finance, maintenance — attaches to
                this structure. That is how Hodi stays operational rather than
                becoming another disconnected list.
              </p>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
