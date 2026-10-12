import Image from "next/image";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { images } from "@/lib/images";

const principles = [
  {
    title: "Real property structure",
    body: "Designed around properties, units, people, and leases — the objects operators already understand.",
  },
  {
    title: "Operational honesty",
    body: "We prioritize a coherent system of record over decorative dashboards and inflated claims.",
  },
  {
    title: "Human workflows",
    body: "Built for owners, managers, and tenants working together — not for a generic SaaS persona.",
  },
] as const;

export function Trust() {
  return (
    <section id="about" className="section-pad bg-bg">
      <Container>
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="relative order-2 lg:order-1 lg:col-span-5">
            <div className="relative aspect-[4/3] overflow-hidden rounded-lg border border-border bg-soft-teal shadow-soft">
              <Image
                src={images.propertyExterior.src}
                alt={images.propertyExterior.alt}
                fill
                sizes="(max-width: 1024px) 100vw, 40vw"
                className="object-cover object-center"
              />
            </div>
          </div>

          <div className="order-1 lg:order-2 lg:col-span-7">
            <SectionHeading
              eyebrow="Why Hodi"
              title="Designed around real property operations."
              description="Hodi exists because running homes is operational work — not a spreadsheet hobby and not a marketing slide. The product is shaped by the day-to-day reality of portfolios, people, and places."
            />

            <ul className="mt-10 space-y-6">
              {principles.map((item) => (
                <li key={item.title} className="border-l-2 border-teal pl-5">
                  <h3 className="text-base font-semibold tracking-tight text-charcoal">
                    {item.title}
                  </h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-text-secondary text-pretty">
                    {item.body}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Container>
    </section>
  );
}
