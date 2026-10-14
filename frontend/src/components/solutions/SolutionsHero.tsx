import { EditorialHero } from "@/components/marketing/EditorialHero";

export function SolutionsHero() {
  return (
    <EditorialHero
      eyebrow="Who Hodi is for"
      title="One system for the people who run a property."
      description="Owners, managers, and tenants work against the same property record — rent, requests, and the daily work stay with the unit they belong to."
      image="/images/hodi/daylit-kitchen.jpg"
      alt="Daylit kitchen and dining room with a dark cabinet run and a window wall"
      caption="The rooms people live in. The records that keep them running."
      primary={{ href: "/#how-it-works", label: "See how Hodi works" }}
      secondary={{ href: "#owners-solution", label: "For owners" }}
    />
  );
}
