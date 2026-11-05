"use client";

import { AppDialogProvider } from "@/components/AppDialog";
import { AuthProvider } from "@/components/AuthProvider";
import { ChromeProvider } from "@/components/chrome";
import { SessionGate } from "@/components/SessionGate";
import { DesktopNav, MobileNav } from "@/components/Sidebar";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const AUTH_PATH = /^\/(login|register|verify|forgot-password|forgot-user-id|reset-password)$/;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const authPage = AUTH_PATH.test(pathname);

  return (
    <AuthProvider>
      <AppDialogProvider>
        <SessionGate>
          {authPage ? (
            <div className="flex h-dvh min-h-0 flex-col bg-wa-app">{children}</div>
          ) : (
            <ChromeProvider>
              <div id="app-shell" className="h-dvh max-w-[100vw] overflow-hidden overscroll-x-none bg-wa-canvas md:max-w-none md:p-4">
                <div className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col overflow-hidden overscroll-x-none bg-white md:flex-row md:shadow-sm">
                  <DesktopNav />
                  <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden">
                    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden">{children}</div>
                    <MobileNav />
                  </div>
                </div>
              </div>
            </ChromeProvider>
          )}
        </SessionGate>
      </AppDialogProvider>
    </AuthProvider>
  );
}
