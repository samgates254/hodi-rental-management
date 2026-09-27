import Link from "next/link";
import { Container } from "@/components/ui/Container";

export default function NotFound() {
  return (
    <main className="flex min-h-[60vh] items-center bg-bg">
      <Container className="py-20 text-center">
        <p className="text-sm font-medium tracking-wide text-teal">404</p>
        <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight text-charcoal">
          Page not found
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-text-secondary">
          That page does not exist or has moved.
        </p>
        <Link
          href="/"
          className="mt-8 inline-flex h-11 items-center justify-center rounded-md bg-teal px-5 text-sm font-medium text-white transition-colors hover:bg-teal/90"
        >
          Back to home
        </Link>
      </Container>
    </main>
  );
}
