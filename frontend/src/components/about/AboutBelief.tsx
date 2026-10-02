import { Container } from "@/components/ui/Container";

const pillars = [
  { label: "People", hint: "Owners, managers, and tenants" },
  { label: "Property", hint: "Buildings, units, and leases" },
  { label: "Money", hint: "Rent, obligations, and status" },
  { label: "Work", hint: "Requests, assignment, and outcomes" },
  { label: "Information", hint: "Context that stays with the place" },
];

export function AboutBelief() {
  return (
    <section id="belief" className="section-pad bg-charcoal text-white">
      <Container>
        <div className="mx-auto max-w-3xl text-center lg:mx-0 lg:max-w-3xl lg:text-left">
          <p className="text-sm font-medium tracking-wide text-teal">The belief</p>
          <h2 className="mt-5 font-display text-3xl font-semibold leading-[1.12] tracking-[-0.02em] text-white text-balance sm:text-4xl lg:text-[2.85rem]">
            Running property is an operational problem.
          </h2>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-white/65 text-pretty sm:text-lg lg:mx-0">
            Good property management is not only collecting rent or answering a
            maintenance request. It is keeping people, property, money, work, and
            information connected — so the day can run without reconstructing
            what already happened.
          </p>
        </div>

        <div className="mt-14 border-t border-white/10">
          <ul className="divide-y divide-white/10 sm:grid sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-5">
            {pillars.map((item, index) => (
              <li
                key={item.label}
                className={`py-6 sm:px-5 sm:py-8 sm:first:pl-0 ${
                  index < pillars.length - 1
                    ? "sm:border-r sm:border-white/10"
                    : ""
                }`}
              >
                <p className="text-base font-semibold tracking-tight text-white">
                  {item.label}
                </p>
                <p className="mt-2 text-sm leading-relaxed text-white/50">
                  {item.hint}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </Container>
    </section>
  );
}
