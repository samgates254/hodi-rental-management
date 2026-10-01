import Image from "next/image";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { images } from "@/lib/images";

export function FinalCta() {
  return (
    <section id="final-cta" className="relative overflow-hidden">
      <div className="absolute inset-0">
        <Image
          src={images.skyline.src}
          alt=""
          fill
          sizes="100vw"
          className="object-cover object-center"
          aria-hidden
        />
        <div
          className="absolute inset-0 bg-charcoal/88"
          aria-hidden
        />
      </div>

      <Container className="relative section-pad">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium tracking-wide text-teal">Hodi</p>
          <h2 className="mt-4 font-display text-3xl font-semibold tracking-tight text-white text-balance sm:text-4xl lg:text-[2.75rem]">
            Property operations, brought together.
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-white/75 text-pretty">
            Put rent, tenants, maintenance, and day-to-day property work on one
            connected system — and run homes with less fragmentation.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button
              href="/signup"
              size="lg"
            >
              Create an account
            </Button>
            <Button
              href="/signin"
              variant="outline-light"
              size="lg"
            >
              Sign in
            </Button>
            <Button
              href="mailto:hello@hodi.app?subject=Talk%20to%20Hodi"
              external
              variant="outline-light"
              size="lg"
            >
              Talk to Hodi
            </Button>
          </div>
        </div>
      </Container>
    </section>
  );
}
