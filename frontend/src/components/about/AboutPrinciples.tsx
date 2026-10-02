import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const principles = [
  {
    id: "01",
    title: "Keep context",
    body: "A request should stay connected to the place, the person, and the work involved. Context should not depend on whoever last held the chat thread.",
  },
  {
    id: "02",
    title: "Make the operation visible",
    body: "People should know what is happening without reconstructing it from messages, spreadsheets, and half-remembered handoffs.",
  },
  {
    id: "03",
    title: "Build for real work",
    body: "The software should make the daily operation easier — not add another layer of administration on top of the work already being done.",
  },
];

export function AboutPrinciples() {
  return (
    <section id="principles" className="section-pad bg-bg">
      <Container>
        <div className="max-w-2xl">
          <SectionHeading
            eyebrow="How we build"
            title="A few principles we hold to."
            description="Not a manifesto — a short list of what we refuse to lose while we ship."
          />
        </div>

        <div className="mt-14 border-t border-border">
          {principles.map((item) => (
            <div
              key={item.id}
              className="grid gap-4 border-b border-border py-8 md:grid-cols-12 md:gap-8 md:py-10"
            >
              <div className="md:col-span-2">
                <span className="font-mono text-sm text-teal">{item.id}</span>
              </div>
              <div className="md:col-span-4">
                <h3 className="text-xl font-semibold tracking-tight text-charcoal md:text-2xl">
                  {item.title}
                </h3>
              </div>
              <div className="md:col-span-6">
                <p className="max-w-lg text-sm leading-relaxed text-text-secondary md:text-base">
                  {item.body}
                </p>
              </div>
            </div>
          ))}
        </div>
      </Container>
    </section>
  );
}
