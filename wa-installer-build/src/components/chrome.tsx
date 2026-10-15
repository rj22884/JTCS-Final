"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

type ChromeContextValue = {
  hideMobileNav: boolean;
  setHideMobileNav: (hidden: boolean) => void;
  unreadCount: number;
  setUnreadCount: (count: number) => void;
};

const ChromeContext = createContext<ChromeContextValue | null>(null);

export function useChrome() {
  const value = useContext(ChromeContext);
  if (!value) throw new Error("useChrome must be used within ChromeProvider");
  return value;
}

export function ChromeProvider({ children }: { children: ReactNode }) {
  const [hideMobileNav, setHideMobileNav] = useState(false);
  const [unreadCount, setUnreadState] = useState(0);
  const unreadTouched = useRef(false);

  const setUnreadCount = useCallback((count: number) => {
    unreadTouched.current = true;
    setUnreadState(count);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/conversations", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: { conversations?: { unreadCount: number }[] } | null) => {
        if (cancelled || unreadTouched.current || !data?.conversations) return;
        const total = data.conversations.reduce((sum, item) => sum + item.unreadCount, 0);
        setUnreadState(total);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ChromeContext.Provider value={{ hideMobileNav, setHideMobileNav, unreadCount, setUnreadCount }}>
      {children}
    </ChromeContext.Provider>
  );
}
