import Image from "next/image";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { images } from "@/lib/images";

const people = [
  {
    role: "The manager",
    line: "Following up on repairs, placing requests, keeping the day moving.",
  },
  {
    role: "The owner",
    line: "Trying to understand what is happening without chasing every update.",
  },
  {
    role: "The tenant",
    line: "Waiting for an issue to be seen, assigned, and resolved.",
  },
  {
    role: "The people in between",
    line: "Answering messages, holding context, filling gaps the tools leave open.",
  },
];

export function AboutPeople() {
  return (
    <section id="people" className="section-pad bg-surface">
      <Container>
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="order-2 lg:order-1 lg:col-span-6">
            <div className="relative aspect-[4/3] overflow-hidden bg-soft-teal shadow-soft">
              <Image
                src={images.operations.src}
                alt={images.operations.alt}
                fill
                sizes="(max-width: 1024px) 100vw, 48vw"
                className="object-cover"
              />
              <div
                className="absolute inset-0 bg-charcoal/25"
                aria-hidden
              />
              <div className="absolute bottom-0 left-0 right-0 bg-charcoal/70 px-5 py-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/70">
                  After the building is finished
                </p>
                <p className="mt-1 text-sm font-medium text-white">
                  The work of running it begins.
                </p>
              </div>
            </div>
          </div>

          <div className="order-1 lg:order-2 lg:col-span-6">
            <SectionHeading
              eyebrow="Who it’s for"
              title="We’re interested in the work that happens after the property is built."
              description="Hodi is being built around the people who carry the operation — not around a feature checklist."
            />

            <ul className="mt-10 space-y-0 border-t border-border">
              {people.map((item) => (
                <li
                  key={item.role}
                  className="border-b border-border py-5"
                >
                  <p className="text-sm font-semibold tracking-tight text-charcoal">
                    {item.role}
                  </p>
                  <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">
                    {item.line}
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
