import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { demoMailto } from "@/lib/site";

export function AboutCta() {
  return (
    <section id="about-cta" className="section-pad bg-surface">
      <Container>
        <div className="mx-auto max-w-2xl border border-border border-l-[3px] border-l-teal bg-bg px-6 py-12 text-center sm:px-10 sm:py-14">
          <p className="text-sm font-medium tracking-wide text-teal">Next</p>
          <h2 className="mt-4 font-display text-2xl font-semibold tracking-tight text-charcoal text-balance sm:text-3xl">
            Better property operations start with better connections.
          </h2>
          <p className="mx-auto mt-4 max-w-md text-sm leading-relaxed text-text-secondary text-pretty sm:text-base">
            See how the operating layer is structured — or tell us about the
            property you run.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button href="/platform" size="lg">
              Explore Hodi
            </Button>
            <Button href={demoMailto} variant="secondary" size="lg">
              Get started
            </Button>
          </div>
        </div>
      </Container>
    </section>
  );
}
