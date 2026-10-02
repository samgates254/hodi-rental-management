import type { Metadata } from "next";
import { ContactBody } from "@/components/contact/ContactBody";
import { ContactFaq } from "@/components/contact/ContactFaq";
import { ContactHero } from "@/components/contact/ContactHero";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";

export const metadata: Metadata = {
  title: "Contact",
  description:
    "Talk to the Hodi team about demos, property operations, partnerships, or product questions. We typically reply within one business day.",
};

export default function ContactPage() {
  return (
    <>
      <Header />
      <main id="main">
        <ContactHero />
        <ContactBody />
        <ContactFaq />
      </main>
      <Footer />
    </>
  );
}
