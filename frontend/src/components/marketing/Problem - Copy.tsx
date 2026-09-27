import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const frictions = [
  {
    title: "Operations scatter",
    body: "Unit details, tenant messages, payment notes, and maintenance threads live in different places — so nothing stays current.",
  },
  {
    title: "Owners lose visibility",
    body: "When the day-to-day is fragmented, owners cannot see occupancy, obligations, or issues without chasing updates.",
  },
  {
    title: "Managers juggle tools",
    body: "Spreadsheets, chats, and inboxes become the system of record. Handoffs slow down. Context drops between people.",
  },
  {
    title: "Tenants wait in the dark",
    body: "Requests and service updates get buried. Residents need a reliable place to raise issues and follow progress.",
  },
];

export function Problem() {
  return (
    <section id="problem" className="section-pad bg-bg">
      <Container>
        <SectionHeading
          eyebrow="The reality"
          title="Property work falls apart when information does."
          description="Most portfolios do not fail from a lack of effort. They strain because rent, tenants, maintenance, and money are managed as separate streams."
        />

        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
          {frictions.map((item, index) => (
            <article
              key={item.title}
              className="flex h-full flex-col rounded-lg border border-border bg-surface p-6 shadow-soft"
            >
              <span
                className="font-display text-3xl font-semibold tabular-nums leading-none text-teal"
                aria-hidden
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="mt-5 text-base font-semibold tracking-tight text-charcoal">
                {item.title}
              </h3>
              <p className="mt-2.5 text-sm leading-relaxed text-text-secondary text-pretty">
                {item.body}
              </p>
            </article>
          ))}
        </div>

        {/* Without → With bridge */}
        <div className="mt-14 grid gap-4 overflow-hidden rounded-lg border border-border bg-surface md:grid-cols-2">
          <div className="border-b border-border p-6 md:border-b-0 md:border-r md:p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-text-secondary">
              Without Hodi
            </p>
            <ul className="mt-4 space-y-2.5 text-sm leading-relaxed text-text-secondary">
              <li className="flex gap-2">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-text-secondary/50" aria-hidden />
                Spreadsheets and side notes for units and leases
              </li>
              <li className="flex gap-2">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-text-secondary/50" aria-hidden />
                WhatsApp threads for maintenance and follow-ups
              </li>
              <li className="flex gap-2">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-text-secondary/50" aria-hidden />
                Separate payment records and unclear balances
              </li>
              <li className="flex gap-2">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-text-secondary/50" aria-hidden />
                Fragmented information across people and tools
              </li>
            </ul>
          </div>
          <div className="bg-soft-teal/40 p-6 md:p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-teal">
              With Hodi
            </p>
            <p className="mt-4 text-base font-medium leading-snug text-charcoal">
              Property → units → tenants → leases → payments → maintenance →
              operations
            </p>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">
              One connected system — so the work of running homes stays in one
              place.
            </p>
          </div>
        </div>
      </Container>
    </section>
  );
}
