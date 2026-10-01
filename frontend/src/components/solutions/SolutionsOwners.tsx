import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const portfolio = {
  name: "Westlands Court",
  units: 24,
  occupied: 21,
  rent: "KES 1.84M",
  open: 3,
  collection: "98%",
};

const activity = [
  {
    label: "Rent received",
    detail: "Unit A-07 · KES 42,000",
    time: "Today",
  },
  {
    label: "Request opened",
    detail: "Unit B-12 · Water leak",
    time: "09:42",
  },
  {
    label: "Work completed",
    detail: "Unit C-03 · Door lock",
    time: "Yesterday",
  },
  {
    label: "Lease renewed",
    detail: "Unit D-01 · 12 months",
    time: "Mon",
  },
];

export function SolutionsOwners() {
  return (
    <section id="owners-solution" className="section-pad bg-surface">
      <Container>
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="order-1 lg:order-2 lg:col-span-5 lg:sticky lg:top-28">
            <SectionHeading
              eyebrow="For owners"
              title="See what is happening across your property."
              description="Owners need visibility without running every operational task themselves. Hodi keeps properties, buildings, units, tenants, leases, rent, and maintenance on one operating record."
            />
            <ul className="mt-8 space-y-3 border-t border-border pt-6">
              {[
                "Portfolio and unit status in one place",
                "Rent and open work without chasing updates",
                "Operational activity tied to the property",
              ].map((item) => (
                <li
                  key={item}
                  className="flex gap-3 text-sm leading-relaxed text-text-secondary"
                >
                  <span
                    className="mt-2 h-1 w-1 shrink-0 rounded-full bg-teal"
                    aria-hidden
                  />
                  {item}
                </li>
              ))}
            </ul>
            <p className="mt-6 text-xs text-text-secondary">
              Illustrative product view — not live portfolio data.
            </p>
          </div>

          <div className="order-2 lg:order-1 lg:col-span-7">
            <div className="overflow-hidden border border-border border-l-[3px] border-l-teal bg-surface shadow-[0_20px_50px_-30px_rgba(25,32,42,0.35)]">
              {/* Window chrome */}
              <div className="flex items-center gap-2 border-b border-border bg-bg px-4 py-3">
                <span className="h-2 w-2 rounded-full bg-border" />
                <span className="h-2 w-2 rounded-full bg-border" />
                <span className="h-2 w-2 rounded-full bg-teal/50" />
                <span className="ml-3 text-[11px] font-medium tracking-wide text-text-secondary">
                  Portfolio · illustrative
                </span>
                <span
                  className="ml-auto size-1.5 shrink-0 rounded-full bg-teal"
                  aria-hidden
                />
              </div>

              <div className="p-5 sm:p-6">
                <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-secondary">
                      Property
                    </p>
                    <h3 className="mt-1 text-xl font-semibold tracking-tight text-charcoal">
                      {portfolio.name}
                    </h3>
                  </div>
                  <p className="text-sm text-text-secondary">
                    <span className="font-medium text-charcoal">
                      {portfolio.occupied}
                    </span>
                    <span className="text-text-secondary">
                      {" "}
                      / {portfolio.units} units occupied
                    </span>
                  </p>
                </div>

                <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden border border-border bg-border sm:grid-cols-4">
                  {[
                    {
                      label: "Monthly rent",
                      value: portfolio.rent,
                      emphasize: false,
                    },
                    {
                      label: "Open requests",
                      value: String(portfolio.open),
                      emphasize: true,
                    },
                    {
                      label: "Collection",
                      value: portfolio.collection,
                      emphasize: false,
                    },
                    {
                      label: "Occupied",
                      value: `${portfolio.occupied}/${portfolio.units}`,
                      emphasize: false,
                    },
                  ].map((stat) => (
                    <div
                      key={stat.label}
                      className={`px-4 py-4 ${
                        stat.emphasize ? "bg-soft-teal/70" : "bg-surface"
                      }`}
                    >
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-secondary">
                        {stat.label}
                      </p>
                      <p
                        className={`mt-2 text-lg font-semibold tracking-tight ${
                          stat.emphasize ? "text-teal" : "text-charcoal"
                        }`}
                      >
                        {stat.value}
                      </p>
                    </div>
                  ))}
                </div>

                <div className="mt-6">
                  <div className="mb-3 flex items-center justify-between">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-secondary">
                      Recent activity
                    </p>
                    <span className="text-[11px] text-text-secondary">
                      Property-linked
                    </span>
                  </div>
                  <ul className="divide-y divide-border border border-border">
                    {activity.map((row, index) => (
                      <li
                        key={row.label + row.detail}
                        className={`flex items-start justify-between gap-4 px-4 py-3.5 ${
                          index === 0 ? "bg-soft-teal/50" : "bg-surface"
                        }`}
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-charcoal">
                            {row.label}
                          </p>
                          <p className="mt-0.5 text-xs text-text-secondary">
                            {row.detail}
                          </p>
                        </div>
                        <span
                          className={`shrink-0 text-[11px] ${
                            index === 0
                              ? "font-medium text-teal"
                              : "text-text-secondary"
                          }`}
                        >
                          {row.time}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
