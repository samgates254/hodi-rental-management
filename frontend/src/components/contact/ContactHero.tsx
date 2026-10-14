import { EditorialHero } from "@/components/marketing/EditorialHero";
import { contactMailto } from "@/lib/site";

export function ContactHero() {
  return (
    <EditorialHero
      tone="photo-left"
      eyebrow="Contact"
      title="Tell us about the properties you run."
      description="Demo, partnership, or a practical question — we read every message. Typical reply within one business day."
      image="/images/hodi/kitchen-island.jpg"
      alt="Kitchen with a stone island, open shelving, and doors onto a deck"
      caption="A conversation, not a ticket queue."
      primary={{ href: "#contact-form", label: "Send a message" }}
      secondary={{ href: contactMailto, label: "Email us directly" }}
    />
  );
}
