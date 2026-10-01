import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const pieces = [
  "Rent",
  "Tenancy",
  "Maintenance",
  "Requests",
  "Payments",
  "People",
  "Units",
  "Buildings",
];

export function AboutWhy() {
  return (
    <section id="why" className="section-pad bg-surface">
      <Container>
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-5 lg:sticky lg:top-28">
            <SectionHeading
              eyebrow="Why we exist"
              title="The work is real. The connections usually aren’t."
              description="Property operations are full of small, necessary actions. Each one can work on its own. The strain shows up between them."
            />
          </div>

          <div className="lg:col-span-7">
            <p className="max-w-xl text-base leading-relaxed text-text-secondary text-pretty sm:text-lg">
              A tenant reports a leak. Someone has to place it on the right unit.
              A manager assigns the work. A technician needs context. Payment
              status sits in another place. The owner asks what happened — and
              the answer has to be reconstructed from chats, notes, and memory.
            </p>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-text-secondary text-pretty sm:text-lg">
              Hodi is being built for that gap: not another inbox, but a place
              where the pieces stay attached to the property they belong to.
            </p>

            <ul className="mt-10 flex flex-wrap gap-2" aria-label="Operational pieces Hodi connects">
              {pieces.map((item) => (
                <li
                  key={item}
                  className="border border-border bg-bg px-3.5 py-2 text-sm text-charcoal"
                >
                  {item}
                </li>
              ))}
            </ul>
            <p className="mt-4 text-sm text-text-secondary">
              Individually familiar. Collectively scattered — until they share
              one thread.
            </p>
          </div>
        </div>
      </Container>
    </section>
  );
}
