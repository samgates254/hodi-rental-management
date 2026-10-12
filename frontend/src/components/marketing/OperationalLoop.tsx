import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const stages = [
  {
    title: "Tenant",
    body: "Pays rent or raises a request from the home context.",
  },
  {
    title: "Hodi",
    body: "Captures the work against the right unit, lease, and people.",
  },
  {
    title: "Manager",
    body: "Reviews, assigns, and tracks progress without losing the thread.",
  },
  {
    title: "Technician",
    body: "Completes field work with clear property context.",
  },
  {
    title: "Property",
    body: "Status returns to the record — ready for the next cycle.",
  },
] as const;

export function OperationalLoop() {
  return (
    <section id="operations" className="section-pad bg-bg text-text">
      <Container>
        <SectionHeading
          eyebrow="The operational loop"
          title="Every property has a living cycle of work."
          description="Hodi is more than rent collection. It keeps the loop between residents, managers, and field work attached to the property itself."
        />

        <div className="mt-12">
          <ol className="grid gap-0 sm:grid-cols-5">
            {stages.map((stage, index) => (
              <li
                key={stage.title}
                className="relative flex flex-col border-b border-border py-5 last:border-b-0 first:pt-0 last:pb-0 sm:border-b-0 sm:border-r sm:px-4 sm:py-8 sm:first:pt-8 sm:last:border-r-0 sm:last:pb-8 lg:px-6"
              >
                <div className="flex items-center gap-3 sm:flex-col sm:items-start sm:gap-3">
                  <span
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 border-teal bg-teal text-sm font-semibold tabular-nums text-brand-contrast"
                    aria-hidden
                  >
                    {index + 1}
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold tracking-tight text-charcoal sm:mt-1">
                      {stage.title}
                    </h3>
                    <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-text-secondary text-pretty">
                      {stage.body}
                    </p>
                  </div>
                </div>
                {index < stages.length - 1 ? (
                  <span
                    className="pointer-events-none absolute -bottom-2 left-1/2 hidden -translate-x-1/2 text-teal sm:left-auto sm:right-0 sm:top-1/2 sm:bottom-auto sm:block sm:translate-x-1/2 sm:-translate-y-1/2"
                    aria-hidden
                  >
                    →
                  </span>
                ) : null}
              </li>
            ))}
          </ol>

          <p className="pt-8 text-[0.9375rem] leading-relaxed text-text-secondary text-pretty md:max-w-3xl">
            Request in. Work assigned. Progress tracked. Outcome recorded. The
            next person always picks up from the same property truth — not a
            scattered message history.
          </p>
        </div>
      </Container>
    </section>
  );
}
