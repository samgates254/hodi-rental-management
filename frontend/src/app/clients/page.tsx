import type { Metadata } from "next";
import ClientDashboard from "@/components/ClientDashboard";

export const metadata: Metadata = {
  title: "Tenant dashboard",
  description: "View your home, rent, payments, and maintenance updates with Hodi.",
};

export default function ClientsPage() {
  return <ClientDashboard />;
}
