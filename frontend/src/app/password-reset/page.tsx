import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import { PasswordResetRequest } from "@/components/PasswordReset";

export const metadata: Metadata = {
  title: "Reset your password",
  robots: { index: false, follow: false },
};

export default function PasswordResetPage() {
  return <><PasswordResetRequest /><Footer /></>;
}
