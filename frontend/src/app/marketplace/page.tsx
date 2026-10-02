import type { Metadata } from "next";
import { MarketplaceBrowse } from "@/components/marketplace/MarketplaceBrowse";

export const metadata: Metadata = {
  title: "Marketplace",
  description: "Browse published Hodi homes. An inquiry does not reserve a unit.",
};

export default function MarketplacePage() {
  return <MarketplaceBrowse />;
}
