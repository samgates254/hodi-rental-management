import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { demoMailto } from "@/lib/site";

export function PlatformHero() {
  return (
    <section className="relative overflow-hidden border-b border-border bg-bg">
      <Container className="py-16 md:py-20 lg:py-24">
        <div className="mx-auto max-w-5xl text-center">
          <p className="text-sm font-medium tracking-wide text-teal">
            Platform
          </p>
          <h1 className="mx-auto mt-4 max-w-4xl font-display text-[2.125rem] font-semibold leading-[1.12] tracking-[-0.02em] text-charcoal text-balance sm:text-5xl lg:text-[3.5rem]">
            Rental property operations, in one connected system.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-text-secondary text-pretty sm:text-lg">
            Manage properties, units, tenants, leases, and day-to-day work from
            a single platform — so rent, requests, and records stay attached to
            the same operational truth.
          </p>
          <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row sm:items-center">
            <Button href={demoMailto} external size="lg">
              Request a Demo
            </Button>
            <Button href="#glance" variant="secondary" size="lg">
              Explore the Platform
            </Button>
          </div>
        </div>
      </Container>
    </section>
  );
}
