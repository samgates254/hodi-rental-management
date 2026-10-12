import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const principles = [
  {
    id: "01",
    title: "One operating record",
    body: "Property, building, unit, tenant, and lease stay connected. Work does not start from a blank message — it starts from the place it belongs.",
  },
  {
    id: "02",
    title: "Work keeps its context",
    body: "Requests, payments, and maintenance remain attached to the right unit and people. History does not scatter across chats and files.",
  },
  {
    id: "03",
    title: "Every role sees what matters",
    body: "Owners get visibility. Managers get control of the work. Tenants get a dependable channel for the home they live in.",
  },
];

export function SolutionsDifference() {
  return (
    <section id="difference" className="section-pad bg-contrast-surface text-white">
      <Container>
        <div className="max-w-2xl">
          <SectionHeading
            light
            eyebrow="The Hodi difference"
            title="Built around the property — not around disconnected features."
            description="Hodi is structured the way property work actually runs: from the site down to the unit, the tenancy, the money, and the request."
          />
        </div>

        <div className="mt-14 border-t border-white/10">
          {principles.map((item) => (
            <div
              key={item.id}
              className="grid gap-4 border-b border-white/10 py-8 md:grid-cols-12 md:gap-8 md:py-10"
            >
              <div className="md:col-span-2">
                <span className="font-mono text-sm text-teal">{item.id}</span>
              </div>
              <div className="md:col-span-4">
                <h3 className="text-xl font-semibold tracking-tight text-white md:text-2xl">
                  {item.title}
                </h3>
              </div>
              <div className="md:col-span-6">
                <p className="max-w-lg text-sm leading-relaxed text-white/65 md:text-base">
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
