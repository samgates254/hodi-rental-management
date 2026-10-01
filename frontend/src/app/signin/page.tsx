import type { Metadata } from "next";
import AuthPage from "@/components/AuthPage";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to your Hodi landlord or client account.",
};

export default function SignInPage() {
  return <AuthPage mode="signin" />;
}
