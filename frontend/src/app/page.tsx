import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { HomepageExperience } from "@/components/marketing/HomepageExperience";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Property management, made simpler",
  description:
    "Bring your properties, rent and everyday responsibilities into one calm workspace, built for Kenya.",
};

export default function HomePage() {
  return (
    <>
      <Header variant="homepage" />
      <HomepageExperience />
      <Footer />
    </>
  );
}
