import Image from "next/image";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { images } from "@/lib/images";

export function SolutionsTenants() {
  return (
    <section id="tenants-solution" className="section-pad bg-surface">
      <Container>
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-14">
          {/* Visual first on desktop — opposite of Managers (copy | card) */}
          <div className="order-2 lg:order-1 lg:col-span-7">
            <div className="grid gap-4 sm:grid-cols-12 sm:gap-5">
              <div className="relative hidden overflow-hidden bg-soft-teal shadow-soft sm:col-span-5 sm:block sm:min-h-[22rem]">
                <Image
                  src={images.living.src}
                  alt={images.living.alt}
                  fill
                  sizes="(max-width: 1024px) 40vw, 22vw"
                  className="object-cover"
                />
                <div className="absolute inset-0 bg-contrast-surface/20" aria-hidden />
                <div className="absolute bottom-0 left-0 right-0 p-4">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-white/70">
                    Home
                  </p>
                  <p className="mt-1 text-sm font-medium text-white">
                    Unit B-12 · Westlands Court
                  </p>
                </div>
              </div>

              <div className="border border-border border-l-[3px] border-l-teal bg-surface sm:col-span-7">
                <div className="border-b border-border bg-bg px-5 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-secondary">
                      My home · illustrative
                    </p>
                    <span
                      className="size-1.5 shrink-0 rounded-full bg-teal"
                      aria-hidden
                    />
                  </div>
                  <h3 className="mt-1 text-lg font-semibold tracking-tight text-charcoal">
                    Unit B-12
                  </h3>
                  <p className="mt-0.5 text-sm text-text-secondary">
                    Westlands Court
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-px border-b border-border bg-border">
                  <div className="bg-surface px-5 py-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-secondary">
                      Rent
                    </p>
                    <p className="mt-2 text-xl font-semibold tracking-tight text-charcoal">
                      KES 35,000
                    </p>
                    <p className="mt-1 text-xs text-text-secondary">Due 5 Oct</p>
                  </div>
                  <div className="bg-soft-teal/50 px-5 py-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-secondary">
                      Status
                    </p>
                    <p className="mt-2 text-sm font-medium text-teal">Current</p>
                    <p className="mt-1 text-xs text-text-secondary">
                      Lease active
                    </p>
                  </div>
                </div>

                <div className="px-5 py-4">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-secondary">
                    Maintenance
                  </p>
                  <div className="mt-3 border border-border bg-bg px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-charcoal">
                          Water leak
                        </p>
                        <p className="mt-1 text-xs text-text-secondary">
                          Latest update · Technician assigned
                        </p>
                      </div>
                      <span className="shrink-0 border border-teal/30 bg-soft-teal px-2 py-1 text-[11px] font-medium text-charcoal">
                        In progress
                      </span>
                    </div>
                  </div>
                  <p className="mt-4 text-xs leading-relaxed text-text-secondary">
                    Simple, trustworthy, and tied to the unit — not a pile of
                    messages.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="order-1 lg:order-2 lg:col-span-5">
            <SectionHeading
              eyebrow="For tenants"
              title="One reliable place for the home you live in."
              description="Tenants should not have to guess who to message, where rent stands, or whether a request was seen. Hodi gives a calm channel for rent, maintenance, updates, and property information."
            />
            <ul className="mt-8 grid gap-3 sm:grid-cols-2">
              {[
                "Rent due and payment status",
                "Maintenance requests",
                "Clear progress updates",
                "Property and unit details",
              ].map((item) => (
                <li
                  key={item}
                  className="border border-border bg-bg px-4 py-3 text-sm text-text-secondary"
                >
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
