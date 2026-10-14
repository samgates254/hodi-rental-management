import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const chain = [
  "Property",
  "Unit",
  "Tenant",
  "Lease",
  "Payment",
  "Maintenance",
  "Operations",
] as const;

export function ConnectedOps() {
  return (
    <section id="connected" className="section-pad border-y border-border bg-surface">
      <Container>
        <SectionHeading
          eyebrow="Connected operations"
          title="Features matter less than the links between them."
          description="Hodi’s value is not a longer feature list. It is that property work shares one record — so a payment, a lease change, or a repair still points back to the same unit and people."
        />

        <div className="mt-12 bg-[#163d32] p-6 text-white sm:p-8 lg:p-10">
          <p className="text-center text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-[#c6a66b]">
            One connected path
          </p>
          <ol className="mt-6 flex flex-wrap items-center justify-center gap-x-1 gap-y-3">
            {chain.map((item, index) => (
              <li key={item} className="flex items-center gap-1 sm:gap-2">
                <span className="border border-white/15 px-3 py-2 text-sm font-medium tracking-tight text-white">
                  {item}
                </span>
                {index < chain.length - 1 ? (
                  <span className="px-0.5 text-[#c6a66b]" aria-hidden>
                    →
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
          <p className="mx-auto mt-8 max-w-2xl text-center text-[0.9375rem] leading-relaxed text-white/75 text-pretty">
            When information stays linked, owners see a coherent portfolio,
            managers stop rebuilding context, and tenants get answers that match
            the actual home they live in.
          </p>
        </div>
      </Container>
    </section>
  );
}
