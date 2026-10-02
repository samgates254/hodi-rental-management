import { Container } from "@/components/ui/Container";

const faqs = [
  {
    q: "Do I need a demo to get started?",
    a: "No. A demo helps when you want to see workflows against your own portfolio shape, but you can email us with questions first. If a walkthrough makes sense, we’ll schedule one — no hard sell.",
  },
  {
    q: "Who is Hodi for?",
    a: "Owners, property managers, and operators who want one system for property, tenancy, finance, and maintenance — instead of spreadsheets and disconnected tools. Tenants get a clearer experience as part of that same record.",
  },
  {
    q: "How quickly do you reply?",
    a: "We aim to respond within one business day. Urgent operational issues should include “urgent” in the subject and a phone number we can reach.",
  },
  {
    q: "Is there a pilot or trial?",
    a: "Yes for qualified portfolios. Tell us unit count, locations, and what you run on today. We’ll propose a scoped pilot with clear success criteria rather than an open-ended trial.",
  },
  {
    q: "Can tenants use Hodi?",
    a: "Yes. Tenant-facing flows sit on the same operating record as owners and managers — requests, payments context, and documents without a separate shadow system.",
  },
  {
    q: "What should I include in my message?",
    a: "Role, rough unit count, cities or regions, tools you use now, and the outcome you care about most (e.g. fewer payment disputes, faster maintenance close-out, portfolio visibility). Screenshots or a short list of pain points help.",
  },
  {
    q: "Where does onboarding start?",
    a: "After we align on fit, we map your properties and roles, connect the workflows you need first, and go live in stages — not a big-bang cutover. You’ll always know what’s live and what’s next.",
  },
] as const;

export function ContactFaq() {
  return (
    <section
      id="contact-faq"
      className="border-b border-border bg-bg"
      aria-labelledby="contact-faq-heading"
    >
      <Container className="py-14 md:py-16 lg:py-20">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium tracking-wide text-teal">FAQ</p>
          <h2
            id="contact-faq-heading"
            className="mt-3 font-display text-2xl font-semibold tracking-[-0.02em] text-charcoal text-balance sm:text-3xl"
          >
            Questions before you write.
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-base leading-relaxed text-text-secondary text-pretty">
            Quick answers so you can skip the back-and-forth — or still send a
            message if you need something specific.
          </p>
        </div>

        <div className="mx-auto mt-12 max-w-3xl divide-y divide-border border-y border-border">
          {faqs.map((item) => (
            <details
              key={item.q}
              className="group py-1 open:bg-transparent"
            >
              <summary className="cursor-pointer list-none py-5 font-display text-base font-semibold tracking-[-0.01em] text-charcoal outline-none marker:content-none sm:text-lg [&::-webkit-details-marker]:hidden">
                <span className="flex items-start justify-between gap-4">
                  <span className="text-left text-balance">{item.q}</span>
                  <span
                    className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center border border-border text-sm text-text-secondary transition-transform group-open:rotate-45"
                    aria-hidden
                  >
                    +
                  </span>
                </span>
              </summary>
              <p className="max-w-2xl pb-5 pr-10 text-sm leading-relaxed text-text-secondary text-pretty sm:text-base">
                {item.a}
              </p>
            </details>
          ))}
        </div>
      </Container>
    </section>
  );
}
