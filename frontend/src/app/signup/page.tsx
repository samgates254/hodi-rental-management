import type { Metadata } from "next";
import AuthPage from "@/components/AuthPage";
import { Footer } from "@/components/layout/Footer";

export const metadata: Metadata = {
  title: "Create an account",
  description: "Create a Hodi landlord or client account.",
};

export default function SignUpPage() {
  return (
    <div className="min-h-screen bg-bg">
      <AuthPage mode="signup" />
      <Footer />
    </div>
  );
}
