import Image from "next/image";

type PropertyBannerProps = {
  eyebrow: string;
  title: string;
  description: string;
  imageSrc: string;
  imageSizes?: string;
  className?: string;
  headingLevel?: "h1" | "h2";
};

export function PropertyBanner({
  eyebrow,
  title,
  description,
  imageSrc,
  imageSizes = "(max-width: 900px) 100vw, 78vw",
  className = "",
  headingLevel = "h2",
}: PropertyBannerProps) {
  const Heading = headingLevel;
  return (
    <section className={`hodi-property-banner ${className}`}>
      <Image
        src={imageSrc}
        alt=""
        fill
        sizes={imageSizes}
        className="hodi-property-banner-image"
      />
      <div className="hodi-property-banner-shade" aria-hidden="true" />
      <div className="hodi-property-banner-copy">
        <span className="hodi-property-banner-eyebrow">{eyebrow}</span>
        <Heading>{title}</Heading>
        <p>{description}</p>
      </div>
      <span className="hodi-property-banner-mark" aria-hidden="true">HODI · PROPERTY OPERATIONS</span>
    </section>
  );
}
