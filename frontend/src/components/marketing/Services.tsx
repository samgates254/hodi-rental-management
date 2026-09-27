import Image from "next/image";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { images } from "@/lib/images";

const services = [
  {
    title: "Maintenance",
    body: "Keep requests, unit context, and follow-through in one operational trail.",
  },
  {
    title: "Technicians & field work",
    body: "Give field work a clear property anchor — who, where, and what needs doing.",
  },
  {
    title: "Property services",
    body: "Extend day-to-day property support without inventing a second system of record.",
  },
  {
    title: "Utilities & support",
    body: "Room to grow into broader resident support as your operation matures.",
  },
] as const;

export function Services() {
  return (
    <section id="services" className="section-pad border-y border-border bg-surface">
      <Container>
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="lg:col-span-6">
            <SectionHeading
              eyebrow="Hodi services"
              title="An operating system that can grow with the property ecosystem."
              description="Today Hodi connects the core of property operations. Over time, the same foundation can extend into maintenance networks, field coordination, and resident support — without restarting from scratch."
            />
            <p className="mt-4 text-sm leading-relaxed text-text-secondary">
              This is the direction of the product. Capabilities expand as the
              platform matures — we do not claim a full marketplace is live today.
            </p>

            <ul className="mt-8 grid gap-4 sm:grid-cols-2">
              {services.map((item) => (
                <li
                  key={item.title}
                  className="rounded-lg border border-border bg-bg p-5"
                >
                  <h3 className="text-sm font-semibold tracking-tight text-charcoal">
                    {item.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-text-secondary text-pretty">
                    {item.body}
                  </p>
                </li>
              ))}
            </ul>
          </div>

          <div className="relative lg:col-span-6">
            <div className="relative aspect-[4/5] overflow-hidden rounded-lg border border-border bg-soft-teal shadow-soft sm:aspect-[5/4] lg:aspect-[4/5]">
              <Image
                src={images.operations.src}
                alt={images.operations.alt}
                fill
                sizes="(max-width: 1024px) 100vw, 50vw"
                className="object-cover object-center"
              />
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
