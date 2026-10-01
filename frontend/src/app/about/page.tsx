import type { Metadata } from "next";
import { AboutBelief } from "@/components/about/AboutBelief";
import { AboutBuilding } from "@/components/about/AboutBuilding";
import { AboutCta } from "@/components/about/AboutCta";
import { AboutHero } from "@/components/about/AboutHero";
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
