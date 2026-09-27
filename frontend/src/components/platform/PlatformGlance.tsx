import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const areas = [
  {
    id: "01",
    title: "Property",
    body: "Properties, buildings, and units structured so every record has a place.",
  },
  {
    id: "02",
    title: "Tenancy",
    body: "Tenants, leases, and rent schedules kept with the units they occupy.",
  },
  {
    id: "03",
    title: "Finance",
    body: "Charges, invoices, payments, and financial records against the right tenancy.",
  },
  {
    id: "04",
    title: "Maintenance",
    body: "Requests and work orders that stay attached to unit and property context.",
  },
  {
    id: "05",
    title: "Operations",
    body: "Day-to-day property work coordinated from one connected operating record.",
  },
] as const;

export function PlatformGlance() {
  return (
    <section id="glance" className="section-pad bg-bg">
      <Container>
        <SectionHeading
          eyebrow="At a glance"
          title="Five areas. One operating record."
          description="Hodi is not a loose set of tools. These are the connected parts of the platform — each one feeds the next."
        />

        <ol className="mt-12 divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
          {areas.map((area) => (
            <li
              key={area.id}
              className="grid gap-3 px-5 py-5 sm:grid-cols-12 sm:items-baseline sm:gap-6 sm:px-7 sm:py-6"
            >
              <span className="font-display text-sm font-semibold tabular-nums text-teal sm:col-span-1">
                {area.id}
              </span>
              <h3 className="text-base font-semibold tracking-tight text-charcoal sm:col-span-3">
                {area.title}
              </h3>
              <p className="text-sm leading-relaxed text-text-secondary text-pretty sm:col-span-8">
                {area.body}
              </p>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}
