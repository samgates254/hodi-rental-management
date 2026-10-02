import Image from "next/image";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { images } from "@/lib/images";
import { demoMailto } from "@/lib/site";

export function SolutionsCta() {
  return (
    <section id="solutions-cta" className="relative overflow-hidden">
      <div className="absolute inset-0">
        <Image
          src={images.skyline.src}
          alt=""
          fill
          sizes="100vw"
          className="object-cover object-center"
          aria-hidden
        />
        <div className="absolute inset-0 bg-charcoal/88" aria-hidden />
      </div>

      <Container className="relative section-pad">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium tracking-wide text-teal">
            Get started
          </p>
          <h2 className="mt-4 font-display text-3xl font-semibold tracking-tight text-white text-balance sm:text-4xl lg:text-[2.75rem]">
            Run the property. Not the paperwork around it.
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-white/75 text-pretty">
            Hodi brings property operations, tenancy, payments, and maintenance
            into one connected system — so owners, managers, and tenants work
            from the same property context.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button href={demoMailto} external size="lg">
              Get started
            </Button>
            <Button href="/#how-it-works" variant="outline-light" size="lg">
              See how Hodi works
            </Button>
          </div>
        </div>
      </Container>
    </section>
  );
}
