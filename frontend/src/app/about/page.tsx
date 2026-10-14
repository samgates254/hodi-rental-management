import type { Metadata } from "next";
import { AboutBelief } from "@/components/about/AboutBelief";
import { AboutBuilding } from "@/components/about/AboutBuilding";
import { AboutCta } from "@/components/about/AboutCta";
import { AboutHero } from "@/components/about/AboutHero";
import { PhotoEssay } from "@/components/marketing/PhotoEssay";
import { AboutPeople } from "@/components/about/AboutPeople";
import { AboutPrinciples } from "@/components/about/AboutPrinciples";
import { AboutWhy } from "@/components/about/AboutWhy";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";

export const metadata: Metadata = {
  title: "About Hodi | Property operations, connected",
  description:
    "Hodi exists to bring the fragmented work of running property into one connected operating system — for owners, managers, and tenants.",
};

export default function AboutPage() {
  return (
    <>
      <Header />
      <main id="main">
        <AboutHero />
        <PhotoEssay
          eyebrow="The places"
          title="Buildings, rooms, and the work between them."
          shots={[
            {
              src: "/images/hodi/timber-bedroom.jpg",
              alt: "Bedroom with a timber ceiling, a bench at the foot of the bed, and a large artwork",
              title: "Lived-in rooms",
              note: "A tenancy is more than a unit number.",
            },
            {
              src: "/images/hodi/bedroom-nook.jpg",
              alt: "Bedroom with floral wallpaper, a daybed, and windows above the main bed",
              title: "Quiet details",
              note: "Maintenance starts with a clear place.",
            },
            {
              src: "/images/hodi/open-living-dining.jpg",
              alt: "Open-plan living and dining room with a glazed wall",
              title: "Shared homes",
              note: "One record for the people inside.",
            },
          ]}
        />
        <AboutWhy />
        <AboutBelief />
        <AboutBuilding />
        <AboutPeople />
        <AboutPrinciples />
        <AboutCta />
      </main>
      <Footer />
    </>
  );
}
