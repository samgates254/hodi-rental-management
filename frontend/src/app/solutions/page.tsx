import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { SolutionsCompare } from "@/components/solutions/SolutionsCompare";
import { SolutionsCta } from "@/components/solutions/SolutionsCta";
import { SolutionsDifference } from "@/components/solutions/SolutionsDifference";
import { SolutionsFlow } from "@/components/solutions/SolutionsFlow";
import { PhotoEssay } from "@/components/marketing/PhotoEssay";
import { SolutionsHero } from "@/components/solutions/SolutionsHero";
import { SolutionsManagers } from "@/components/solutions/SolutionsManagers";
import { SolutionsOwners } from "@/components/solutions/SolutionsOwners";
import { SolutionsProblem } from "@/components/solutions/SolutionsProblem";
import { SolutionsSystem } from "@/components/solutions/SolutionsSystem";
import { SolutionsTenants } from "@/components/solutions/SolutionsTenants";

export const metadata: Metadata = {
  title: "Solutions — Hodi",
  description:
    "Hodi connects owners, managers, and tenants around the property — so work, rent, and maintenance stay attached to the right place.",
  openGraph: {
    title: "Solutions — Hodi",
    description:
      "Property operations for owners, managers, and tenants — connected to the property, not scattered across channels.",
  },
};

export default function SolutionsPage() {
  return (
    <>
      <Header />
      <main id="main">
        <SolutionsHero />
        <nav className="hodi-role-jump" aria-label="Solutions by role">
          <a href="#owners-solution"><strong>Owners</strong><span>Portfolio clarity</span></a>
          <a href="#managers-solution"><strong>Managers</strong><span>Day-to-day work</span></a>
          <a href="#tenants-solution"><strong>Tenants</strong><span>Home and requests</span></a>
        </nav>
        <PhotoEssay
          eyebrow="The same building, different work"
          title="Owners, managers, and tenants share the property — not the same tasks."
          shots={[
            {
              src: "/images/hodi/property-exterior.jpg",
              alt: "Hillside apartment block photographed from above",
              title: "Owners",
              note: "The portfolio, without chasing updates.",
            },
            {
              src: "/images/hodi/mixed-use-block.jpg",
              alt: "Street-front apartment building with timber balconies",
              title: "Managers",
              note: "Units, leases, and open work.",
            },
            {
              src: "/images/hodi/daylit-kitchen.jpg",
              alt: "Daylit kitchen and dining room",
              title: "Tenants",
              note: "Rent, the home, and a way to report issues.",
            },
          ]}
        />
        <SolutionsSystem />
        <SolutionsProblem />
        <SolutionsOwners />
        <SolutionsManagers />
        <SolutionsTenants />
        <SolutionsDifference />
        <SolutionsFlow />
        <SolutionsCompare />
        <SolutionsCta />
      </main>
      <Footer />
    </>
  );
}
