import type { Metadata } from "next";
import AuthPage from "@/components/AuthPage";

export const metadata: Metadata = {
  title: "Create an account",
  description: "Create a Hodi landlord or client account.",
};

export default function SignUpPage() {
  return <AuthPage mode="signup" />;
}
