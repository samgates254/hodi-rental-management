import type { Metadata } from "next";
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/500.css";
import "@fontsource/dm-sans/600.css";
import "@fontsource/dm-sans/700.css";
import "@fontsource/fraunces/400.css";
import "@fontsource/fraunces/600.css";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { SmoothScrollProvider } from "@/components/providers/SmoothScrollProvider";
import { AmbientMeshBackground } from "@/components/ui/AmbientMeshBackground";
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
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var saved=localStorage.getItem("hodi-theme");var theme=saved==="dark"||saved==="light"?saved:(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.dataset.theme=theme;}catch(e){document.documentElement.dataset.theme="light";}})();`,
          }}
        />
      </head>
      <body className="antialiased relative min-h-screen">
        <AmbientMeshBackground />
        <ThemeProvider>
          <SmoothScrollProvider>
            <div className="relative z-10">{children}</div>
          </SmoothScrollProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
