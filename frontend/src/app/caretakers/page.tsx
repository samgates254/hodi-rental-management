import type { Metadata } from "next";
import CaretakerDashboard from "@/components/CaretakerDashboard";

export const metadata: Metadata = {
  title: "Caretaker dashboard",
  description: "Review maintenance requests and rent status for your property.",
};

export default function CaretakersPage() {
  return <CaretakerDashboard />;
}
