import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import { PasswordResetConfirm } from "@/components/PasswordReset";

export const metadata: Metadata = {
  title: "Choose a new password",
  robots: { index: false, follow: false },
};

export default function PasswordResetConfirmPage() {
  return <><PasswordResetConfirm /><Footer /></>;
}
