import type { Metadata } from "next";
import AuthPage from "@/components/AuthPage";
import { Footer } from "@/components/layout/Footer";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to your Hodi landlord or client account.",
};

export default function SignInPage() {
  return (
    <div className="bg-[#f7f8f7]">
      <AuthPage mode="signin" />
      <Footer />
    </div>
  );
}
