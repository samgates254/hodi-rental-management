import type { Metadata } from "next";
import AuthPage from "@/components/AuthPage";
import { Footer } from "@/components/layout/Footer";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to Hodi and continue to the workspaces your account can access.",
};

export default function SignInPage() {
  return (
    <div className="min-h-screen bg-bg">
      <AuthPage mode="signin" />
      <Footer />
    </div>
  );
}
