import Image from "next/image";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { images } from "@/lib/images";

export function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-border bg-bg">
      <Container className="grid items-center gap-10 py-12 md:gap-14 md:py-16 lg:grid-cols-12 lg:gap-16 lg:py-20">
        <div className="lg:col-span-6">
          <p className="text-sm font-medium tracking-wide text-teal">
            Property operations software
          </p>
          <h1 className="mt-4 font-display text-[2.125rem] font-semibold leading-[1.12] tracking-[-0.02em] text-charcoal text-balance sm:text-5xl lg:text-[3.25rem]">
            Run every property from one connected system.
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-text-secondary text-pretty sm:text-lg">
            Hodi brings rent, tenants, maintenance, and daily property work
            together for owners and managers.
          </p>
          <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button href="/pricing" size="lg">
              Explore plans
            </Button>
            <Button href="#how-it-works" variant="secondary" size="lg">
              See How It Works
            </Button>
          </div>
          <p className="mt-7 max-w-md text-sm leading-relaxed text-text-secondary">
            Built for the people who run homes and the tenants who live in them.
          </p>
        </div>

        <div className="relative lg:col-span-6">
          <div className="relative aspect-[3/2] overflow-hidden rounded-lg bg-soft-teal shadow-soft">
            <Image
              src={images.hero.src}
              alt={images.hero.alt}
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 50vw"
              className="object-cover object-center"
            />
            <div
              className="pointer-events-none absolute inset-0 bg-gradient-to-t from-charcoal/25 via-transparent to-transparent"
              aria-hidden
            />
          </div>

          {/* Subtle product context — not a fake dashboard */}
          <div className="mt-4 border-l-2 border-teal pl-4 sm:mt-5 sm:pl-5">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-teal">
              Connected operations
            </p>
            <p className="mt-2 max-w-sm text-base font-medium leading-snug text-charcoal sm:text-lg">
              Property, units, tenants, leases, and work in one clear record.
            </p>
          </div>
        </div>
      </Container>
    </section>
  );
}
