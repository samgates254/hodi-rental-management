import type { Metadata } from "next";
import AgentWorkspace from "@/components/AgentWorkspace";

export const metadata: Metadata = {
  title: "Property agent workspace",
  description: "Manage your Hodi agent profile, owner-authorized listings, enquiries, and viewings.",
};

export default function AgentsPage() {
  return <AgentWorkspace />;
}
