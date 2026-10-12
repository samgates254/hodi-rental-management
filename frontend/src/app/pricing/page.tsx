import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import PricingExperience from "@/components/marketing/PricingExperience";

export const metadata: Metadata = {
  title: "Plans and pricing",
  description: "Compare Hodi plans for landlords and property managers. Start free and choose a unit allowance that fits your portfolio.",
};

export default function PricingPage() {
  return (
    <>
      <Header />
      <main id="main"><PricingExperience /></main>
      <Footer />
    </>
  );
}
