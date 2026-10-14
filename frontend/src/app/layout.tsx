import type { Metadata } from "next";
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/500.css";
import "@fontsource/dm-sans/600.css";
import "@fontsource/dm-sans/700.css";
import "@fontsource/fraunces/400.css";
import "@fontsource/fraunces/600.css";
import Script from "next/script";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Hodi — Property operations software",
    template: "%s · Hodi",
  },
  description:
    "Hodi is property operations software for owners, managers, and tenants — connecting properties, units, leases, and everyday work in one system.",
  metadataBase: new URL("https://hodi.app"),
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  openGraph: {
    title: "Hodi — Property operations software",
    description:
      "Run residential properties with clarity. One system for owners, managers, and tenants.",
    type: "website",
    locale: "en_KE",
    siteName: "Hodi",
    images: [{ url: "/brand/hodi-mark-512.png", width: 512, height: 512, alt: "Hodi" }],
  },
  twitter: {
    card: "summary",
    title: "Hodi — Property operations software",
    description:
      "Run residential properties with clarity. One system for owners, managers, and tenants.",
    images: ["/brand/hodi-mark-512.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <Script id="hodi-theme-init" strategy="beforeInteractive">
          {`try { var savedTheme = localStorage.getItem("hodi-theme"); document.documentElement.dataset.theme = savedTheme === "dark" ? "dark" : "light"; } catch (_) { document.documentElement.dataset.theme = "light"; }`}
        </Script>
      </head>
      <body className="antialiased">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
