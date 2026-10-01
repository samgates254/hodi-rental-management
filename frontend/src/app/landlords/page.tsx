import type { Metadata } from "next";
import LandlordDashboard from "@/components/LandlordDashboard";

export const metadata: Metadata = {
  title: "Landlord dashboard",
  description: "Manage your properties, units, tenants, and leases with Hodi.",
};

export default function LandlordsPage() {
  return <LandlordDashboard />;
}
