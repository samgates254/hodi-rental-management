import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const layers = [
  {
    id: "01",
    title: "Property structure",
    body: "Properties, buildings, and units as the spine everything else hangs on.",
  },
  {
    id: "02",
    title: "Tenancy",
    body: "Who lives where, under what terms — attached to the unit, not a separate list.",
  },
  {
    id: "03",
    title: "Payments",
    body: "Rent and obligations that stay visible against the same record.",
  },
  {
    id: "04",
    title: "Maintenance & work",
    body: "Requests, assignment, and outcomes that never leave the property thread.",
  },
  {
    id: "05",
    title: "People",
    body: "Owners, managers, and tenants each see what they need — without losing shared context.",
  },
];

export function AboutBuilding() {
  return (
    <section id="building" className="section-pad bg-bg">
      <Container>
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="lg:col-span-5 lg:sticky lg:top-28">
            <SectionHeading
              eyebrow="What we’re building"
              title="An operating layer for the property."
              description="Not a pile of features. A place where the operational state of a property stays understandable — from structure down to the latest request."
            />
            <p className="mt-6 max-w-md text-sm leading-relaxed text-text-secondary">
              The platform page shows how the product is structured. Here is the
              idea behind it: one connected record so day-to-day work does not
              have to be rebuilt from scratch.
            </p>
            <p className="mt-4">
              <a
                href="/platform"
                className="text-sm font-medium text-brand underline decoration-[var(--hodi-gold)] underline-offset-4"
              >
                See the platform →
              </a>
            </p>
          </div>

          <div className="lg:col-span-7">
            <ol className="border-t border-border">
              {layers.map((layer) => (
                <li
                  key={layer.id}
                  className="grid gap-3 border-b border-border py-6 sm:grid-cols-[3rem_1fr] sm:gap-6 sm:py-7"
                >
                  <span className="text-sm tracking-[0.14em] text-[#a8874f]">{layer.id}</span>
                  <div>
                    <h3 className="font-[family-name:var(--hodi-editorial)] text-2xl font-normal tracking-[-0.03em] text-charcoal">
                      {layer.title}
                    </h3>
                    <p className="mt-2 max-w-md text-sm leading-relaxed text-text-secondary">
                      {layer.body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </Container>
    </section>
  );
}
