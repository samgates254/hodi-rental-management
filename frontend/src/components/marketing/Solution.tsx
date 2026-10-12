import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const chain = [
  "Property",
  "Buildings",
  "Units",
  "Tenants",
  "Leases",
  "Operations",
  "Services",
] as const;

const pillars = [
  {
    title: "A single operating record",
    body: "Properties, units, people, and leases share one structure — so every action sits on the same foundation.",
  },
  {
    title: "Work that stays attached",
    body: "Payments, requests, and day-to-day tasks stay linked to the right unit and tenancy instead of floating in inboxes.",
  },
  {
    title: "Clarity for every role",
    body: "Owners see the portfolio. Managers run the work. Tenants get a dependable home channel — without parallel systems.",
  },
] as const;

export function Solution() {
  return (
    <section id="product" className="section-pad border-y border-border bg-surface">
      <Container>
        <SectionHeading
          eyebrow="The Hodi system"
          title="Property operations, connected end to end."
          description="Hodi is the operating layer between the building and the daily work of living in it — not a pile of disconnected feature cards."
        />

        <div className="mt-12">
          <ol className="grid grid-cols-2 gap-y-7 sm:grid-cols-3 sm:gap-y-8 lg:grid-cols-7 lg:gap-0">
            {chain.map((item, index) => (
              <li key={item} className="relative flex items-center justify-center">
                <div className="flex flex-col items-center gap-2 px-2 py-1 text-center">
                  <span className="relative flex h-12 w-14 items-center justify-center overflow-hidden rounded-md border border-charcoal/15 bg-contrast-surface text-sm font-semibold tabular-nums text-white shadow-soft">
                    {String(index + 1).padStart(2, "0")}
                    <span className="absolute inset-x-0 bottom-0 h-1 bg-teal" aria-hidden />
                  </span>
                  <span className="text-sm font-medium tracking-tight text-charcoal">
                    {item}
                  </span>
                </div>
                {index < chain.length - 1 ? (
                  <span
                    className="absolute left-[calc(50%+2.5rem)] hidden h-px w-[calc(100%-5rem)] bg-border lg:block"
                    aria-hidden
                  />
                ) : null}
              </li>
            ))}
          </ol>
        </div>

        <div className="mt-14 grid gap-4 md:grid-cols-3 md:gap-5">
          {pillars.map((pillar) => (
            <article
              key={pillar.title}
              className="rounded-lg border border-border bg-bg p-6"
            >
              <h3 className="text-base font-semibold tracking-tight text-charcoal">
                {pillar.title}
              </h3>
              <p className="mt-2.5 text-sm leading-relaxed text-text-secondary text-pretty">
                {pillar.body}
              </p>
            </article>
          ))}
        </div>
      </Container>
    </section>
  );
}
