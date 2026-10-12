import type { Metadata } from "next";
import AuthPage from "@/components/AuthPage";
import { Footer } from "@/components/layout/Footer";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to your Hodi landlord or client account.",
};

export default function SignInPage() {
  return (
    <div className="min-h-screen bg-bg">
      <AuthPage mode="signin" />
      <Footer />
    </div>
  );
}
