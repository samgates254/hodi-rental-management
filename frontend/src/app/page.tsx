import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { FinalCta } from "@/components/marketing/FinalCta";
import { Hero } from "@/components/marketing/Hero";
import { HowItWorks } from "@/components/marketing/HowItWorks";
import { OperationalLoop } from "@/components/marketing/OperationalLoop";
import { Problem } from "@/components/marketing/Problem";
import { Services } from "@/components/marketing/Services";
import { Solution } from "@/components/marketing/Solution";
import { Trust } from "@/components/marketing/Trust";
import { TwoSided } from "@/components/marketing/TwoSided";

export default function HomePage() {
  return (
    <>
      <Header />
      <main id="main">
        <Hero />
        <Problem />
        <Solution />
        <TwoSided />
        <HowItWorks />
        <OperationalLoop />
        <Services />
        <Trust />
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}
