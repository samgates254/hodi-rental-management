import Image from "next/image";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { images } from "@/lib/images";

const flow = [
  { step: "1", title: "Report", body: "Issue raised against the unit." },
  { step: "2", title: "Work order", body: "Work captured with property context." },
  { step: "3", title: "Assign", body: "Manager routes the job." },
  { step: "4", title: "Complete", body: "Field work finished and noted." },
  { step: "5", title: "Close", body: "Outcome returns to the record." },
] as const;

export function Maintenance() {
  return (
    <section id="maintenance" className="section-pad bg-bg">
      <Container>
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
          <div className="lg:col-span-6">
            <SectionHeading
              eyebrow="Maintenance"
              title="Requests that keep their property context."
              description="Maintenance is not a separate inbox. In Hodi, requests and work orders stay linked to the unit and tenancy — so handoffs do not lose the story."
            />

            <ol className="mt-10 space-y-0">
              {flow.map((item, index) => (
                <li key={item.title} className="relative flex gap-4 pb-6 last:pb-0">
                  {index < flow.length - 1 ? (
                    <span
                      className="absolute left-[17px] top-9 bottom-0 w-px bg-border"
                      aria-hidden
                    />
                  ) : null}
                  <span
                    className="relative z-[1] flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 border-teal bg-soft-teal text-sm font-semibold tabular-nums text-charcoal"
                    aria-hidden
                  >
                    {item.step}
                  </span>
                  <div className="pt-1">
                    <h3 className="text-sm font-semibold tracking-tight text-charcoal">
                      {item.title}
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                      {item.body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            <p className="mt-8 text-sm leading-relaxed text-text-secondary text-pretty">
              Field coordination and wider service networks can grow on this
              foundation. The platform page describes the operating model —
              not a claim that every marketplace capability is live today.
            </p>
          </div>

          <div className="lg:col-span-6">
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
