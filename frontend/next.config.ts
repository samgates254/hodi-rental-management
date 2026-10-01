import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: false },
  async rewrites() {
    const backendOrigin = process.env.API_PROXY_TARGET ??
      (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : undefined);

    return backendOrigin
      ? [{
          source: "/api/v1/:path*",
          destination: `${backendOrigin.replace(/\/+$/, "")}/api/v1/:path*`,
        }]
      : [];
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "images.unsplash.com",
        pathname: "/**",
      },
    ],
  },
};

export default nextConfig;
