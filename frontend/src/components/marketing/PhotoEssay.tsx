import Image from "next/image";
import { Container } from "@/components/ui/Container";

type Shot = {
  src: string;
  alt: string;
  title: string;
  note: string;
};

export function PhotoEssay({
  eyebrow,
  title,
  shots,
}: {
  eyebrow: string;
  title: string;
  shots: readonly [Shot, Shot, Shot];
}) {
  return (
    <section className="hodi-photo-essay" aria-labelledby="photo-essay-title">
      <Container>
        <div className="hodi-photo-essay-head">
          <p className="hodi-editorial-kicker">
            <span aria-hidden="true" />
            {eyebrow}
          </p>
          <h2 id="photo-essay-title">{title}</h2>
        </div>
        <div className="hodi-photo-essay-grid">
          {shots.map((shot) => (
            <article key={shot.src}>
              <Image src={shot.src} alt={shot.alt} width={900} height={680} sizes="(max-width: 800px) 100vw, 33vw" />
              <div>
                <strong>{shot.title}</strong>
                <span>{shot.note}</span>
              </div>
            </article>
          ))}
        </div>
        <p className="hodi-photo-disclaimer">
          Illustrative architecture and interiors. These photographs are not Hodi listings, customer properties, or available homes.
        </p>
      </Container>
    </section>
  );
}
