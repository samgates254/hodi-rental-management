import { NextResponse } from "next/server";

export function GET() {
  const configuredUrl = process.env.DJANGO_ADMIN_URL?.trim();
  const apiOrigin = process.env.API_PROXY_TARGET?.trim();
  let adminUrl = configuredUrl;

  if (!adminUrl && apiOrigin) {
    try {
      adminUrl = new URL("/admin/", apiOrigin).toString();
    } catch {
      return NextResponse.json(
        { detail: "Django admin is not configured with a valid backend URL." },
        { status: 503 },
      );
    }
  }

  if (!adminUrl && process.env.NODE_ENV === "development") {
    adminUrl = "http://127.0.0.1:8000/admin/";
  }

  if (!adminUrl) {
    return NextResponse.json(
      { detail: "Set DJANGO_ADMIN_URL to enable the Django admin route." },
      { status: 503 },
    );
  }

  return NextResponse.redirect(adminUrl);
}
