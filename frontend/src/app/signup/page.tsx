import type { Metadata } from "next";
import AuthPage from "@/components/AuthPage";
import { Footer } from "@/components/layout/Footer";

export const metadata: Metadata = {
  title: "Create an account",
  description: "Create a Hodi landlord or client account.",
};

export default function SignUpPage() {
  return (
    <div className="bg-[#f7f8f7]">
      <AuthPage mode="signup" />
      <Footer />
    </div>
  );
}
