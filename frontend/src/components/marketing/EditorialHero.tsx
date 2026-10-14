import Image from "next/image";
import { Button } from "@/components/ui/Button";

type Action = {
  href: string;
  label: string;
  external?: boolean;
};

export function EditorialHero({
  eyebrow,
  title,
  description,
  image,
  alt,
  caption,
  primary,
  secondary,
  tone = "split",
}: {
  eyebrow: string;
  title: string;
  description: string;
  image: string;
  alt: string;
  caption: string;
  primary: Action;
  secondary?: Action;
  tone?: "split" | "forest" | "photo-left";
}) {
  return (
    <section
      className={`hodi-editorial-hero ${tone === "forest" ? "is-forest" : ""} ${tone === "photo-left" ? "is-photo-left" : ""}`}
      aria-labelledby="editorial-hero-title"
    >
      <div className="hodi-editorial-copy">
        <p className="hodi-editorial-kicker">
          <span aria-hidden="true" />
          {eyebrow}
        </p>
        <h1 id="editorial-hero-title">{title}</h1>
        <p>{description}</p>
        <div className="hodi-editorial-actions">
          <Button href={primary.href} external={primary.external} size="lg">
            {primary.label}
          </Button>
          {secondary ? (
            <Button
              href={secondary.href}
              external={secondary.external}
              variant={tone === "forest" ? "outline-light" : "secondary"}
              size="lg"
            >
              {secondary.label}
            </Button>
          ) : null}
        </div>
      </div>
      <figure className="hodi-editorial-visual">
        <Image
          src={image}
          alt={alt}
          fill
          priority
          sizes="(max-width: 899px) 100vw, 52vw"
          className="hodi-editorial-image"
        />
        <figcaption>
          <span>{caption}</span>
          <small>ILLUSTRATIVE PHOTOGRAPH</small>
        </figcaption>
      </figure>
    </section>
  );
}
