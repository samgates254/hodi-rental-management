import { NextResponse } from "next/server";

export function GET() {
  const adminUrl =
    process.env.DJANGO_ADMIN_URL ?? "http://127.0.0.1:8000/admin/";

  return NextResponse.redirect(adminUrl);
}