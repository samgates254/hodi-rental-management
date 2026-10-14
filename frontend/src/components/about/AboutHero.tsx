import { EditorialHero } from "@/components/marketing/EditorialHero";

export function AboutHero() {
  return (
    <EditorialHero
      tone="photo-left"
      eyebrow="About Hodi"
      title="Property should be easier to run."
      description="Hodi exists to bring the fragmented work of running property into one connected operating system — so owners, managers, and tenants work from the same record."
      image="/images/hodi/property-exterior.jpg"
      alt="Hillside apartment block with stacked balconies and a courtyard, photographed from above"
      caption="The building is the record. The work stays attached to it."
      primary={{ href: "/platform", label: "Explore the platform" }}
      secondary={{ href: "/contact", label: "Talk to us" }}
    />
  );
}
