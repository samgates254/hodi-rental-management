import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import AgentEmailVerification from "@/components/AgentEmailVerification";

export const metadata: Metadata = {
  title: "Verify your email",
  robots: { index: false, follow: false },
};

export default function VerifyEmailPage() {
  return <><AgentEmailVerification /><Footer /></>;
}
