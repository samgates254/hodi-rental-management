import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const fragmented = [
  "Tenant message",
  "WhatsApp thread",
  "Phone call",
  "Spreadsheet note",
  "Technician chat",
  "Owner follow-up",
];

const connected = [
  { label: "Request", detail: "Logged on the unit" },
  { label: "Context", detail: "Tenant · lease · history" },
  { label: "Assignment", detail: "Technician with full brief" },
  { label: "Progress", detail: "Status on the same thread" },
  { label: "Resolution", detail: "Outcome on the property" },
  { label: "Visibility", detail: "Owner sees what happened" },
];

export function SolutionsProblem() {
  return (
    <section id="problem" className="section-pad bg-bg">
      <Container>
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-16">
          {/* Cards left — opposite of System (copy | card) */}
          <div className="order-2 lg:order-1 lg:col-span-7">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="border border-border bg-surface p-5 sm:p-6">
                <div className="flex items-center justify-between gap-3 border-b border-border pb-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                    Fragmented
                  </p>
                  <span className="text-[11px] text-text-secondary">
                    Scattered
                  </span>
                </div>
                <ol className="mt-5 space-y-0">
                  {fragmented.map((step, i) => (
                    <li
                      key={step}
                      className="flex items-start gap-3 border-b border-border/70 py-2.5 last:border-b-0"
                    >
                      <span className="mt-0.5 w-5 shrink-0 font-mono text-[11px] text-text-secondary">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="text-sm text-text-secondary">{step}</span>
                    </li>
                  ))}
                </ol>
                <p className="mt-5 border-t border-border pt-4 text-xs leading-relaxed text-text-secondary">
                  Each step may be handled. The property context is not.
                </p>
              </div>

              <div className="border border-charcoal bg-charcoal p-5 text-white sm:p-6">
                <div className="flex items-center justify-between gap-3 border-b border-white/10 pb-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-teal">
                    With Hodi
                  </p>
                  <span className="text-[11px] text-white/45">Connected</span>
                </div>
                <ol className="mt-5 space-y-0">
                  {connected.map((step, i) => (
                    <li
                      key={step.label}
                      className="flex items-start gap-3 border-b border-white/10 py-2.5 last:border-b-0"
                    >
                      <span className="mt-0.5 w-5 shrink-0 font-mono text-[11px] text-teal/80">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-white">
                          {step.label}
                        </p>
                        <p className="mt-0.5 text-xs text-white/50">
                          {step.detail}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
                <p className="mt-5 border-t border-white/10 pt-4 text-xs leading-relaxed text-white/55">
                  Request in. Work assigned. Progress tracked. Outcome recorded.
                </p>
              </div>
            </div>
          </div>

          <div className="order-1 lg:order-2 lg:col-span-5 lg:sticky lg:top-28">
            <SectionHeading
              eyebrow="The real problem"
              title="Most property problems aren’t isolated."
              description="A tenant reports an issue. Someone has to place it. A manager assigns it. A technician needs context. The work has to be tracked. The outcome has to return to the property."
            />
            <p className="mt-6 max-w-md text-sm leading-relaxed text-text-secondary">
              The hard part is rarely any single task. It is fragmentation —
              messages, money, tenancy, and work living in different places with
              no shared property thread.
            </p>
          </div>
        </div>
      </Container>
    </section>
  );
}
