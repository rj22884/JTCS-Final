"use client";

import type { AdminSessionState } from "@/lib/types";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type AuthContextValue = {
  session: AdminSessionState | null;
  ready: boolean;
  csrfToken: string;
  refresh: () => Promise<AdminSessionState | null>;
  applySession: (next: AdminSessionState | null) => void;
  authedFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AdminSessionState | null>(null);
  const [ready, setReady] = useState(false);

  const applySession = useCallback((next: AdminSessionState | null) => {
    setSession(next);
    setReady(true);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/admin/session", { cache: "no-store" });
      if (!response.ok) {
        setSession(null);
        setReady(true);
        return null;
      }
      const next = (await response.json()) as AdminSessionState;
      setSession(next);
      setReady(true);
      return next;
    } catch {
      setSession(null);
      setReady(true);
      return null;
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const csrfToken = session?.csrfToken ?? "";

  const authedFetch = useCallback(
    (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      if (csrfToken) headers.set("x-csrf-token", csrfToken);
      return fetch(input, { ...init, headers, cache: init?.cache ?? "no-store" });
    },
    [csrfToken],
  );

  const value = useMemo(
    () => ({ session, ready, csrfToken, refresh, applySession, authedFetch }),
    [session, ready, csrfToken, refresh, applySession, authedFetch],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth requires AuthProvider");
  return value;
}
