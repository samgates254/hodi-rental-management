import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const owners = [
  "Portfolio and property structure in one place",
  "Units, occupancy, and lease context without chasing files",
  "Operational visibility across rent, requests, and day-to-day work",
  "A shared record your team can actually run from",
] as const;

const tenants = [
  "Clear home information tied to your unit",
  "Rent and related obligations in context",
  "A reliable channel for maintenance and service requests",
  "Updates that stay attached to the right property work",
] as const;

export function TwoSided() {
  return (
    <section id="owners" className="section-pad bg-bg">
      <Container>
        <SectionHeading
          eyebrow="Two sides of the same home"
          title="Built for the people who own, manage, and live there."
          description="Owners and managers need operational control. Tenants need a dependable home experience. Hodi serves both without splitting the truth across tools."
        />

        <div className="mt-12 grid items-stretch gap-5 md:grid-cols-2 lg:gap-6">
          <article
            id="for-owners"
            className="flex flex-col rounded-lg border border-border bg-surface p-7 shadow-soft sm:p-8"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-teal">
              Owners & managers
            </p>
            <h3 className="mt-3 font-display text-2xl font-semibold tracking-tight text-charcoal">
              Run the property side with clarity.
            </h3>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">
              Organize the portfolio, keep unit and lease context close, and
              coordinate everyday operations without rebuilding the picture each
              week.
            </p>
            <ul className="mt-6 flex-1 space-y-3">
              {owners.map((item) => (
                <li
                  key={item}
                  className="flex gap-3 text-sm leading-relaxed text-charcoal"
                >
                  <span
                    className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal"
                    aria-hidden
                  />
                  {item}
                </li>
              ))}
            </ul>
          </article>

          <article id="tenants" className="flex flex-col rounded-lg border border-border bg-surface p-7 shadow-soft sm:p-8">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-teal">
                Tenants
              </p>
              <h3 className="mt-3 font-display text-2xl font-semibold tracking-tight text-charcoal">
                A clearer way to live with your home.
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-text-secondary">
                Residents should not need five chats to understand rent,
                requests, or who is handling an issue. Hodi keeps home matters in
                one reliable place.
              </p>
              <ul className="mt-6 space-y-3">
                {tenants.map((item) => (
                  <li
                    key={item}
                    className="flex gap-3 text-sm leading-relaxed text-charcoal"
                  >
                    <span
                      className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal"
                      aria-hidden
                    />
                    {item}
                  </li>
                ))}
              </ul>
          </article>
        </div>
      </Container>
    </section>
  );
}
