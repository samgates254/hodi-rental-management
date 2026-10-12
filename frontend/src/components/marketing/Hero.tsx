import Image from "next/image";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { images } from "@/lib/images";

export function Hero() {
  return (
    <section className="hodi-home-hero" aria-labelledby="home-hero-title">
      <Container className="hodi-home-hero-inner">
        <div className="hodi-home-hero-copy">
          <p className="hodi-home-hero-eyebrow"><span aria-hidden="true" />Property operations, made clear</p>
          <h1 id="home-hero-title">A better way to care for the places people call home.</h1>
          <p className="hodi-home-hero-description">
            Bring properties, tenancies, rent records and maintenance work into one considered workspace.
          </p>
          <div className="hodi-home-hero-actions">
            <Button href="/pricing" size="lg">Explore plans</Button>
            <Button href="#how-it-works" variant="secondary" size="lg">See how HODI works</Button>
          </div>
          <p className="hodi-home-hero-footnote">One connected record for owners, property teams and residents.</p>
        </div>

        <figure className="hodi-home-hero-visual">
          <Image
            src={images.hero.src}
            alt={images.hero.alt}
            fill
            priority
            sizes="(max-width: 900px) 100vw, 58vw"
            className="hodi-home-hero-image"
          />
          <div className="hodi-home-hero-image-shade" aria-hidden="true" />
          <figcaption className="hodi-home-hero-caption">
            <span>PROPERTY · PEOPLE · EVERYDAY WORK</span>
            <strong>Everything has its place.</strong>
          </figcaption>
          <span className="hodi-home-hero-index" aria-hidden="true">HODI / 01</span>
        </figure>
      </Container>
      <div className="hodi-home-hero-rule" aria-hidden="true"><span /></div>
    </section>
  );
}
