import { Logo } from "@/components/layout/Logo";
import { Container } from "@/components/ui/Container";
import { contactMailto, demoMailto } from "@/lib/site";

const columns = [
  {
    title: "Product",
    links: [
      { label: "Home", href: "/" },
      { label: "Platform", href: "/platform" },
      { label: "Marketplace", href: "/marketplace" },
      { label: "Solutions", href: "/solutions" },
      { label: "How it works", href: "/#how-it-works" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About", href: "/about" },
      { label: "Contact", href: "/contact" },
      { label: "For owners", href: "/solutions#owners-solution" },
      { label: "For tenants", href: "/solutions#tenants-solution" },
    ],
  },
  {
    title: "Get started",
    links: [
      { label: "Request a demo", href: demoMailto },
      { label: "Talk to Hodi", href: contactMailto },
      { label: "Explore platform", href: "/platform" },
    ],
  },
] as const;

export function Footer() {
  return (
    <footer className="border-t border-border bg-surface">
      <Container className="section-pad !py-14 md:!py-16">
        <div className="grid gap-10 md:grid-cols-2 lg:grid-cols-12 lg:gap-8">
          <div className="lg:col-span-4">
            <Logo size={36} />
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-text-secondary">
              Property operations software for owners, managers, and the people
              who live in the homes they run.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3 lg:col-span-8 lg:grid-cols-3">
            {columns.map((col) => (
              <div key={col.title}>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-charcoal">
                  {col.title}
                </p>
                <ul className="mt-4 space-y-2.5">
                  {col.links.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        className="text-sm text-text-secondary transition-colors hover:text-charcoal"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-border pt-8 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-text-secondary">
            © {new Date().getFullYear()} Hodi. All rights reserved.
          </p>
          <div className="flex gap-5 text-sm text-text-secondary">
            <span className="cursor-default opacity-70" title="Coming soon">
              Privacy
            </span>
            <span className="cursor-default opacity-70" title="Coming soon">
              Terms
            </span>
            <a href="/contact" className="hover:text-charcoal">
              Contact
            </a>
          </div>
        </div>
      </Container>
    </footer>
  );
}
