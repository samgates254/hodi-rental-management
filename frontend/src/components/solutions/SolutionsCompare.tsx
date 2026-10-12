import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const left = [
  "Messages in different channels",
  "Payment records separated from tenancy",
  "Maintenance history spread across conversations",
  "Managers reconstructing context",
  "Owners asking for updates",
];

const right = [
  "Requests tied to the home",
  "Tenancy and payment context connected",
  "Maintenance attached to the unit",
  "Operational history stays together",
  "Property activity remains visible",
];

export function SolutionsCompare() {
  return (
    <section id="compare" className="section-pad bg-bg">
      <Container>
        <div className="mx-auto max-w-2xl text-center">
          <SectionHeading
            align="center"
            eyebrow="Side by side"
            title="Same work. Different structure."
            description="The argument is not louder marketing. It is whether property work keeps its context."
          />
        </div>

        <div className="mx-auto mt-12 grid max-w-5xl gap-4 md:grid-cols-2 md:gap-0 md:overflow-hidden md:border md:border-border">
          <div className="border border-border bg-surface p-6 md:border-0 md:border-r md:border-border md:p-8">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-secondary">
              Fragmented property operations
            </p>
            <ul className="mt-6 space-y-4">
              {left.map((item) => (
                <li
                  key={item}
                  className="flex gap-3 border-b border-border/80 pb-4 text-sm leading-relaxed text-text-secondary last:border-b-0 last:pb-0"
                >
                  <span
                    className="mt-2 h-px w-4 shrink-0 bg-border"
                    aria-hidden
                  />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="border border-charcoal bg-contrast-surface p-6 text-white md:border-0 md:p-8">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-teal">
              With Hodi
            </p>
            <ul className="mt-6 space-y-4">
              {right.map((item) => (
                <li
                  key={item}
                  className="flex gap-3 border-b border-white/10 pb-4 text-sm leading-relaxed text-white/80 last:border-b-0 last:pb-0"
                >
                  <span
                    className="mt-2 h-px w-4 shrink-0 bg-teal"
                    aria-hidden
                  />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Container>
    </section>
  );
}
