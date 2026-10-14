import { EditorialHero } from "@/components/marketing/EditorialHero";
import { demoMailto } from "@/lib/site";

export function PlatformHero() {
  return (
    <EditorialHero
      tone="forest"
      eyebrow="Platform"
      title="Rental operations, on one record."
      description="Properties, units, tenants, leases, rent, and maintenance stay attached to the same operational truth — instead of living in separate chats and spreadsheets."
      image="/images/hodi/mixed-use-block.jpg"
      alt="Street-front apartment building with timber balconies"
      caption="Structure first. Then the everyday work."
      primary={{ href: demoMailto, label: "Request a demo", external: true }}
      secondary={{ href: "#glance", label: "See the platform" }}
    />
  );
}
