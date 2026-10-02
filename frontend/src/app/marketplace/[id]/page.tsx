import type { Metadata } from "next";
import { MarketplaceDetail } from "@/components/marketplace/MarketplaceDetail";

export const metadata: Metadata = {
  title: "Listing",
  description: "A published Hodi home. Sending an inquiry does not create a lease.",
};

export default async function MarketplaceListingPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <MarketplaceDetail listingId={id} />;
}
