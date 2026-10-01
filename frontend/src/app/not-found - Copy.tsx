import Link from "next/link";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { Container } from "@/components/ui/Container";

export default function NotFound() {
  return (
    <>
      <Header />
      <main id="main" className="flex min-h-[60vh] items-center bg-bg">
        <Container className="py-20 text-center md:py-28">
          <p className="font-display text-sm font-semibold tracking-wide text-brand">404</p>
          <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight text-ink md:text-4xl">
            Page not found
          </h1>
          <p className="mx-auto mt-4 max-w-md text-base text-muted">
            That route doesn&apos;t exist — or it moved. Head home or reach out if you expected something
            here.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link href="/" className="btn-primary">
              Home
            </Link>
            <Link href="/contact" className="btn-secondary">
              Contact
            </Link>
          </div>
        </Container>
      </main>
      <Footer />
    </>
  );
}
