import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const chain = [
  { label: "Unit", hint: "B-12" },
  { label: "Tenant", hint: "Occupant record" },
  { label: "Lease", hint: "Terms & dates" },
  { label: "Rent schedule", hint: "What is due" },
] as const;

const points = [
  {
    title: "Tenant records with unit context",
    body: "People are linked to the homes they occupy — not stranded in a separate contact list.",
  },
  {
    title: "Leases on the unit",
    body: "Agreements sit with the unit so occupancy, obligations, and history stay readable.",
  },
  {
    title: "Rent schedules that follow the lease",
    body: "What is due and when remains attached to the tenancy, not a side spreadsheet.",
  },
] as const;

export function Tenancy() {
  return (
    <section id="tenancy" className="section-pad bg-bg">
      <Container>
        <SectionHeading
          eyebrow="Tenants & leases"
          title="Occupancy is a relationship, not a row."
          description="Hodi keeps unit, tenant, lease, and rent schedule connected — so managers and owners see tenancy as it actually works."
        />

        <div className="mt-12 overflow-x-auto pb-1">
          <ol className="flex min-w-max items-stretch gap-0 sm:min-w-0 sm:flex-wrap lg:flex-nowrap lg:justify-center">
            {chain.map((item, index) => (
              <li key={item.label} className="flex items-center">
                <div className="min-w-[8.5rem] rounded-lg border border-charcoal/15 bg-charcoal px-4 py-3.5 text-center shadow-soft sm:min-w-[9.5rem]">
                  <p className="text-sm font-semibold tracking-tight text-white">
                    {item.label}
                  </p>
                  <p className="mt-1 text-xs text-white/70">{item.hint}</p>
                </div>
                {index < chain.length - 1 ? (
                  <span className="mx-2 hidden text-teal sm:inline" aria-hidden>
                    →
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        </div>

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {points.map((point) => (
            <article
              key={point.title}
              className="rounded-lg border border-border bg-surface p-6"
            >
              <h3 className="text-base font-semibold tracking-tight text-charcoal">
                {point.title}
              </h3>
              <p className="mt-2.5 text-sm leading-relaxed text-text-secondary text-pretty">
                {point.body}
              </p>
            </article>
          ))}
        </div>
      </Container>
    </section>
  );
}
