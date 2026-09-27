import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { ConnectedOps } from "@/components/platform/ConnectedOps";
import { Finance } from "@/components/platform/Finance";
import { Maintenance } from "@/components/platform/Maintenance";
import { PlatformCta } from "@/components/platform/PlatformCta";
import { PlatformGlance } from "@/components/platform/PlatformGlance";
import { PlatformHero } from "@/components/platform/PlatformHero";
import { PropertyStructure } from "@/components/platform/PropertyStructure";
import { Roles } from "@/components/platform/Roles";
import { Tenancy } from "@/components/platform/Tenancy";

export const metadata: Metadata = {
  title: "Platform",
  description:
    "Hodi platform — connected property structure, tenancy, financial records, maintenance, and day-to-day operations in one system.",
  openGraph: {
    title: "Hodi Platform — Connected property operations",
    description:
      "Manage properties, units, tenants, leases, and day-to-day work from one connected platform.",
  },
};

export default function PlatformPage() {
  return (
    <>
      <Header />
      <main id="main">
        <PlatformHero />
        <PlatformGlance />
        <PropertyStructure />
        <Tenancy />
        <Finance />
        <Maintenance />
        <ConnectedOps />
        <Roles />
        <PlatformCta />
      </main>
      <Footer />
    </>
  );
}
