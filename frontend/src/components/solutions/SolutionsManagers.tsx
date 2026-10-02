import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const chain = [
  "Unit",
  "Tenant",
  "Lease",
  "Request",
  "Technician",
  "Resolution",
];

const queue = [
  {
    unit: "B-12",
    title: "Water leak",
    reported: "09:42",
    status: "In progress",
    statusTone: "active" as const,
    assignee: "Technician · assigned",
  },
  {
    unit: "C-04",
    title: "Electrical issue",
    reported: "10:18",
    status: "Awaiting visit",
    statusTone: "wait" as const,
    assignee: "Unassigned",
  },
  {
    unit: "A-09",
    title: "Gate remote",
    reported: "Yesterday",
    status: "Resolved",
    statusTone: "done" as const,
    assignee: "Closed · recorded",
  },
];

const toneClass = {
  active: "border-teal/30 bg-soft-teal text-charcoal",
  wait: "border-border bg-bg text-text-secondary",
  done: "border-border bg-surface text-text-secondary",
};

export function SolutionsManagers() {
  return (
    <section id="managers-solution" className="section-pad bg-bg">
      <Container>
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="lg:col-span-5 lg:sticky lg:top-28">
            <SectionHeading
              eyebrow="For managers"
              title="Run the work without losing the thread."
              description="Managers sit at the center of property operations. Hodi keeps unit, tenant, lease, request, and resolution connected so assignment and follow-through do not depend on memory or chat history."
            />
            <div className="mt-8 space-y-4 border-t border-border pt-6">
              {[
                {
                  t: "Assign with context",
                  d: "The unit and tenant stay on the request.",
                },
                {
                  t: "Track progress",
                  d: "Status moves with the work — not across inboxes.",
                },
                {
                  t: "Close the loop",
                  d: "Resolution returns to the property record.",
                },
              ].map((row) => (
                <div key={row.t} className="grid grid-cols-[auto_1fr] gap-4">
                  <span className="mt-1.5 h-px w-6 bg-teal" aria-hidden />
                  <div>
                    <p className="text-sm font-medium text-charcoal">{row.t}</p>
                    <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                      {row.d}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="lg:col-span-7">
            <div className="overflow-hidden border border-border border-l-[3px] border-l-teal bg-surface shadow-[0_20px_50px_-30px_rgba(25,32,42,0.3)]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-bg px-5 py-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-secondary">
                    Today · Maintenance
                  </p>
                  <p className="mt-1 text-sm font-medium text-charcoal">
                    Open work with unit context
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className="size-1.5 shrink-0 rounded-full bg-teal"
                    aria-hidden
                  />
                  <span className="border border-border bg-bg px-2.5 py-1 text-[11px] font-medium text-text-secondary">
                    Illustrative queue
                  </span>
                </div>
              </div>

              {/* Context chain */}
              <div className="border-b border-border bg-surface/80 px-5 py-4">
                <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-text-secondary">
                  Context stays attached
                </p>
                <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
                  {chain.map((node, i) => {
                    const isFocus = node === "Request";
                    return (
                      <div key={node} className="flex items-center gap-1">
                        <span
                          className={`px-2.5 py-1 text-[11px] font-medium ${
                            isFocus
                              ? "border border-teal/40 bg-soft-teal text-charcoal"
                              : "border border-charcoal/15 bg-surface text-charcoal"
                          }`}
                        >
                          {node}
                        </span>
                        {i < chain.length - 1 ? (
                          <span
                            className="px-0.5 text-text-secondary"
                            aria-hidden
                          >
                            →
                          </span>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>

              <ul className="divide-y divide-border">
                {queue.map((item) => {
                  const isHero = item.statusTone === "active";
                  return (
                    <li
                      key={item.unit + item.title}
                      className={`grid gap-3 px-5 py-4 sm:grid-cols-[4.5rem_1fr_auto] sm:items-start ${
                        isHero ? "bg-soft-teal/50" : "bg-bg"
                      }`}
                    >
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-secondary">
                          Unit
                        </p>
                        <p
                          className={`mt-1 font-mono text-sm font-semibold ${
                            isHero ? "text-teal" : "text-charcoal"
                          }`}
                        >
                          {item.unit}
                        </p>
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-charcoal">
                          {item.title}
                        </p>
                        <p className="mt-1 text-xs text-text-secondary">
                          Reported {item.reported} · {item.assignee}
                        </p>
                      </div>
                      <span
                        className={`inline-flex w-fit border px-2.5 py-1 text-[11px] font-medium ${toneClass[item.statusTone]}`}
                      >
                        {item.status}
                      </span>
                    </li>
                  );
                })}
              </ul>

              <div className="border-t border-border bg-bg px-5 py-3.5">
                <p className="text-xs leading-relaxed text-text-secondary">
                  Managers run the work without reconstructing who lives where,
                  what the lease says, or where the last update went.
                </p>
              </div>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
