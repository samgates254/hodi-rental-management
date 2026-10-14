import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const roles = [
  {
    title: "Property owner",
    body: "Portfolio visibility and operational oversight without living in the day-to-day noise.",
  },
  {
    title: "Property manager",
    body: "Structure, tenancy, finance context, and maintenance — run from one working record.",
  },
  {
    title: "Tenant",
    body: "A clearer channel for home information, obligations, and service requests.",
  },
] as const;

export function Roles() {
  return (
    <section id="roles" className="section-pad bg-bg">
      <Container>
        <SectionHeading
          eyebrow="Who it’s for"
          title="One platform, three operational seats."
          description="Hodi serves the people who own, manage, and live in rental property — without splitting truth across separate tools. Deeper role journeys live in Solutions; this is the platform bridge."
        />

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {roles.map((role, index) => (
            <article
              key={role.title}
              className="flex h-full flex-col border border-border border-t-2 border-t-[#c6a66b] bg-surface p-6"
            >
              <span
                className="font-[family-name:var(--hodi-editorial)] text-3xl font-normal tabular-nums text-[#a8874f]"
                aria-hidden
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="mt-4 font-[family-name:var(--hodi-editorial)] text-2xl font-normal tracking-[-0.03em] text-charcoal">
                {role.title}
              </h3>
              <p className="mt-2.5 text-sm leading-relaxed text-text-secondary text-pretty">
                {role.body}
              </p>
            </article>
          ))}
        </div>
      </Container>
    </section>
  );
}
