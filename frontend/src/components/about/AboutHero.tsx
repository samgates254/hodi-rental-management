import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";

export function AboutHero() {
  return (
    <section className="border-b border-border bg-bg">
      <Container className="py-16 md:py-20 lg:py-24">
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-sm font-medium tracking-wide text-teal">About Hodi</p>
          <h1 className="mt-5 font-display text-[2.25rem] font-semibold leading-[1.1] tracking-[-0.02em] text-charcoal text-balance sm:text-5xl lg:text-[3.25rem]">
            Property should be easier to run.
          </h1>
          <p className="mx-auto mt-7 max-w-xl text-base leading-relaxed text-text-secondary text-pretty sm:text-lg">
            Hodi exists to bring the fragmented work of running property into one
            connected operating system — so owners, managers, and tenants work from
            the same record.
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button href="/platform" size="lg">
              Explore the platform
            </Button>
            <Button href="/contact" variant="secondary" size="lg">
              Talk to us
            </Button>
          </div>
        </div>
      </Container>
    </section>
  );
}
