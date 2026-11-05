"use client";

import { useAuth } from "@/components/AuthProvider";
import { Avatar } from "@/components/Avatar";
import { Tooltip } from "@/components/IconButton";
import { useChrome } from "@/components/chrome";
import { cn } from "@/lib/cn";
import { ClipboardCheck, Contact, MessageCircle, Settings, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

export function DesktopNav() {
  const { unreadCount } = useChrome();
  const { session } = useAuth();
  const isAdmin = session?.authenticated && session.role === "admin";
  return (
    <nav
      aria-label="Primary"
      className="hidden h-full w-[68px] shrink-0 flex-col items-center border-r border-wa-line bg-wa-app py-3 md:flex"
    >
      <Link
        href="/"
        aria-label="WhatsApp CRM home"
        className="grid h-10 w-10 place-items-center rounded-xl bg-wa-green text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green focus-visible:ring-offset-2"
      >
        <MessageCircle aria-hidden="true" className="h-5 w-5" />
      </Link>
      <div className="mt-4 flex flex-col gap-1">
        <NavLink href="/" label="Chats" icon="chats" unreadCount={unreadCount} side="right" />
        <NavLink href="/contacts" label="Contacts" icon="contacts" side="right" />
        {isAdmin ? <NavLink href="/approvals" label="Approvals" icon="approvals" side="right" /> : null}
        {isAdmin ? <NavLink href="/settings" label="Settings" icon="settings" side="right" /> : null}
        <NavLink href="/account" label="Profile" icon="account" side="right" />
      </div>
      <ConnectionDot />
    </nav>
  );
}

export function MobileNav() {
  const { hideMobileNav, unreadCount } = useChrome();
  const { session } = useAuth();
  const isAdmin = session?.authenticated && session.role === "admin";
  if (hideMobileNav) return null;
  return (
    <nav
      aria-label="Primary"
      className="flex min-h-14 shrink-0 items-stretch border-t border-wa-line bg-white pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <NavLink href="/" label="Chats" icon="chats" unreadCount={unreadCount} wide />
      <NavLink href="/contacts" label="Contacts" icon="contacts" wide />
      {isAdmin ? <NavLink href="/approvals" label="Approvals" icon="approvals" wide /> : null}
      {isAdmin ? <NavLink href="/settings" label="Settings" icon="settings" wide /> : null}
      <NavLink href="/account" label="Profile" icon="account" wide />
    </nav>
  );
}

function ConnectionDot() {
  const [live, setLive] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void fetch("/api/whatsapp/status", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) return;
        const data = (await response.json()) as { connection?: string };
        if (!cancelled) setLive(data.connection === "connected");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <div className="mt-auto mb-1" role="status" aria-label={live ? "WhatsApp is connected" : "WhatsApp is not connected"}>
      <Tooltip label={live ? "Connected" : "Not connected"} side="right">
        <span className="grid h-10 w-10 place-items-center">
          <span className={cn("h-2.5 w-2.5 rounded-full", live ? "bg-wa-green" : "bg-[#8696a0]")} />
        </span>
      </Tooltip>
    </div>
  );
}

function NavLink({
  href,
  label,
  icon,
  unreadCount = 0,
  side = "top",
  wide = false,
}: {
  href: string;
  label: string;
  icon: "chats" | "contacts" | "approvals" | "settings" | "account";
  unreadCount?: number;
  side?: "top" | "right";
  wide?: boolean;
}) {
  const pathname = usePathname();
  const { session } = useAuth();
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  const Icon =
    icon === "chats"
      ? MessageCircle
      : icon === "contacts"
        ? Contact
        : icon === "approvals"
          ? ClipboardCheck
          : icon === "account"
            ? UserRound
            : Settings;
  const accessible =
    icon === "chats" && unreadCount > 0 ? `${label}, ${unreadCount} unread` : label;
  const profileName = session?.name?.trim() || session?.email || "Profile";
  const profileSrc = icon === "account" ? session?.avatarUrl : null;

  const link = (
    <Link
      href={href}
      aria-label={accessible}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative inline-flex items-center justify-center text-wa-icon focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green",
        wide ? "h-14 flex-1 flex-col gap-0.5 text-[11px]" : "h-10 w-10 rounded-full",
        active && (wide ? "text-wa-green-dark" : "bg-[#e7f6f2] text-wa-green-dark"),
      )}
    >
      {profileSrc ? (
        <Avatar name={profileName} size={wide ? 22 : 28} src={profileSrc} className="ring-1 ring-wa-line" />
      ) : (
        <Icon aria-hidden="true" className="h-5 w-5" />
      )}
      {wide ? <span>{label}</span> : null}
      {icon === "chats" && unreadCount > 0 ? (
        <span className="absolute right-5 top-1 grid min-w-4 place-items-center rounded-full bg-wa-green px-1 text-[10px] font-semibold leading-4 text-white md:right-1 md:top-1">
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      ) : null}
    </Link>
  );

  if (wide) return link;
  return (
    <Tooltip label={accessible} side={side}>
      {link}
    </Tooltip>
  );
}
