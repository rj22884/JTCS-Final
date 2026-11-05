"use client";

import { useAuth } from "@/components/AuthProvider";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

const PUBLIC =
  /^\/(login|register|verify|forgot-password|forgot-user-id|reset-password)(\/|$)/;
const ADMIN_ONLY = /^\/(settings|approvals)(\/|$)/;

/**
 * Single gate driven by AuthProvider — avoids a second /session fetch racing login/logout
 * and the login ↔ home blink when AuthProvider remounted per route.
 */
export function SessionGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, ready } = useAuth();
  const publicPage = PUBLIC.test(pathname);
  const adminOnlyPage = ADMIN_ONLY.test(pathname);
  const authenticated = Boolean(session?.authenticated);
  const isAdmin = Boolean(session?.authenticated && session.role === "admin");

  useEffect(() => {
    if (!ready || !session) return;

    if (authenticated && publicPage) {
      router.replace("/");
      return;
    }
    if (!authenticated && !publicPage) {
      const next = pathname === "/" ? "/login" : `/login?next=${encodeURIComponent(pathname)}`;
      router.replace(next);
      return;
    }
    if (authenticated && adminOnlyPage && !isAdmin) {
      router.replace("/");
    }
  }, [ready, session, authenticated, publicPage, adminOnlyPage, isAdmin, pathname, router]);

  // Public auth screens paint immediately once CSRF/session probe finished (even if logged out).
  if (!ready) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-wa-app text-sm text-wa-muted" role="status">
        Checking sign-in…
      </div>
    );
  }

  // Redirect in progress — keep the wait screen to avoid flashing the wrong page.
  if (authenticated && publicPage) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-wa-app text-sm text-wa-muted" role="status">
        Opening inbox…
      </div>
    );
  }
  if (!authenticated && !publicPage) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-wa-app text-sm text-wa-muted" role="status">
        Checking sign-in…
      </div>
    );
  }
  if (authenticated && adminOnlyPage && !isAdmin) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-wa-app text-sm text-wa-muted" role="status">
        Opening inbox…
      </div>
    );
  }

  return <>{children}</>;
}
