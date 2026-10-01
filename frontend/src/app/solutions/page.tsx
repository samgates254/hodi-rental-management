import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { SolutionsCompare } from "@/components/solutions/SolutionsCompare";
import { SolutionsCta } from "@/components/solutions/SolutionsCta";
import { SolutionsDifference } from "@/components/solutions/SolutionsDifference";
import { SolutionsFlow } from "@/components/solutions/SolutionsFlow";
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
