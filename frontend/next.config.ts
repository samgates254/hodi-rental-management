import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: false },
  devIndicators: false,
  skipTrailingSlashRedirect: true,
  async rewrites() {
    // This value is captured when `next build` generates the rewrite manifest.
    // Production deployments must set API_PROXY_TARGET at build time (or route
    // /api/v1/ to Django at the hosting layer).
    const backendOrigin = process.env.API_PROXY_TARGET ??
      (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : undefined);

    return backendOrigin
      ? [{
          source: "/api/v1/:path*",
          // Django auth/API routes are slash-terminated. With
          // skipTrailingSlashRedirect enabled, preserve the canonical slash
          // even if an incoming caller omitted it.
          destination: `${backendOrigin.replace(/\/+$/, "")}/api/v1/:path*/`,
        }]
      : [];
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "images.unsplash.com", pathname: "/**" },
      { protocol: "https", hostname: "**", pathname: "/**" },
      { protocol: "http", hostname: "**", pathname: "/**" },
    ],
  },
};

export default nextConfig;
