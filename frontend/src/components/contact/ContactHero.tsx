import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { contactMailto } from "@/lib/site";

export function ContactHero() {
  return (
    <section className="border-b border-border bg-bg">
      <Container className="py-14 md:py-16 lg:py-20">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium tracking-wide text-teal">Contact</p>
          <h1 className="mt-4 font-display text-[2rem] font-semibold leading-[1.12] tracking-[-0.02em] text-charcoal text-balance sm:text-4xl lg:text-[2.75rem]">
            Tell us about your property operations.
          </h1>
          <p className="mx-auto mt-5 max-w-lg text-base leading-relaxed text-text-secondary text-pretty sm:text-lg">
            Demo, partnership, or a practical question — we read every message.
            Typical reply within one business day.
          </p>

          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button href="#contact-form" size="lg">
              Send a message
            </Button>
            <Button href={contactMailto} variant="secondary" size="lg">
              Email us directly
            </Button>
          </div>
        </div>
      </Container>
    </section>
  );
}
