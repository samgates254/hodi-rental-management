import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";

const roles = [
  { label: "Owners", hint: "Portfolio clarity", href: "#owners-solution" },
  { label: "Managers", hint: "Day-to-day ops", href: "#managers-solution" },
  { label: "Tenants", hint: "Simple service", href: "#tenants-solution" },
];

export function SolutionsHero() {
  return (
    <section className="relative overflow-hidden border-b border-border bg-bg">
      <Container className="py-16 md:py-20 lg:py-24">
        <div className="mx-auto max-w-5xl text-center">
          <p className="text-sm font-medium tracking-wide text-teal">
            Property operations
          </p>
          <h1 className="mx-auto mt-4 max-w-4xl font-display text-[2.125rem] font-semibold leading-[1.12] tracking-[-0.02em] text-charcoal text-balance sm:text-5xl lg:text-[3.5rem]">
            Property operations should work as one system.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-text-secondary text-pretty sm:text-lg">
            Hodi connects owners, managers, tenants, payments, maintenance, and
            the daily work of running a property — all against the same property
            record.
          </p>

          <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row sm:items-center">
            <Button href="/#how-it-works" size="lg">
              See how Hodi works
            </Button>
            <Button href="#owners-solution" variant="secondary" size="lg">
              Who Hodi is for
            </Button>
          </div>

          <nav
            aria-label="Solutions by role"
            className="mx-auto mt-12 max-w-xl border-t border-border pt-8"
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-secondary">
              Jump to
            </p>
            <ul className="mt-5 flex flex-wrap items-center justify-center gap-x-10 gap-y-3">
              {roles.map((role) => (
                <li key={role.label}>
                  <a
                    href={role.href}
                    className="group inline-flex flex-col items-center gap-0.5 text-sm text-charcoal transition-colors hover:text-teal sm:inline-flex sm:flex-row sm:items-baseline sm:gap-2"
                  >
                    <span className="font-medium tracking-tight">
                      {role.label}
                    </span>
                    <span className="text-xs text-text-secondary transition-colors group-hover:text-teal/80 sm:text-sm">
                      {role.hint}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </Container>
    </section>
  );
}
