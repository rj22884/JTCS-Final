import { isSessionToken } from "@/lib/auth-policy";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const PUBLIC_PAGE =
  /^\/(login|register|verify|forgot-password|forgot-user-id|reset-password)(\/|$)/;

/**
 * Cookie presence only (Edge cannot open SQLite).
 * Stale cookies are cleared by SessionGate; do not bounce /login ↔ / on cookie shape alone.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname.startsWith("/api/") || pathname.startsWith("/_next/") || pathname.includes(".")) {
    return NextResponse.next();
  }

  const sessionCookie = request.cookies.get("wa_admin")?.value ?? "";
  const hasCookie = isSessionToken(sessionCookie);
  const isPublic = PUBLIC_PAGE.test(pathname);

  if (!hasCookie && !isPublic) {
    const login = new URL("/login", request.url);
    if (pathname !== "/") login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
