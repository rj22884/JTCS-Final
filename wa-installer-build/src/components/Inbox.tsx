"use client";

import { useAuth } from "@/components/AuthProvider";
import type { ChatMenuAction } from "@/components/ChatContextMenu";
import { ChatView } from "@/components/ChatView";
import { useChrome } from "@/components/chrome";
import { ContactPanel } from "@/components/ContactPanel";
import { ConversationList } from "@/components/ConversationList";
import { EmptyThread, ErrorState, InboxSkeleton } from "@/components/States";
import { cn } from "@/lib/cn";
import {
  canShowDesktopNotification,
  detectNewInboundUnread,
  getNotifyPermission,
  getNotifyPreference,
  requestNotifyPermission,
  setAppUnreadBadge,
  setDocumentUnreadTitle,
  setNotifyPreference,
  showDesktopNotification,
  syncPushSubscription,
  type UnreadSnapshot,
} from "@/lib/desktop-notifications";
import { isMuted, sortSummaries } from "@/lib/filter-conversations";
import type { ConversationDetail, ConversationFilter, ConversationSummary } from "@/lib/types";
import { Bell, BellOff } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

type Pane = "list" | "chat" | "contact";

export function Inbox() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { session, authedFetch, refresh } = useAuth();
  const { setHideMobileNav, setUnreadCount } = useChrome();
  const [phase, setPhase] = useState<"loading" | "error" | "ready">("loading");
  const [errorDetail, setErrorDetail] = useState("The inbox did not respond. Sign in again or retry.");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [detailPhase, setDetailPhase] = useState<"idle" | "loading" | "error" | "ready">("idle");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ConversationFilter>("all");
  const [pane, setPane] = useState<Pane>("list");
  const [contactOpen, setContactOpen] = useState(true);
  const [wideLayout, setWideLayout] = useState(false);
  const [unreadDivider, setUnreadDivider] = useState(0);
  const [detailNonce, setDetailNonce] = useState(0);
  const [live, setLive] = useState(false);
  const [connected, setConnected] = useState(false);
  const [focusComposer, setFocusComposer] = useState(false);
  const [notifyBanner, setNotifyBanner] = useState(false);
  const unreadSnapshot = useRef<Map<string, UnreadSnapshot> | null>(null);
  const selectedIdRef = useRef<string | null>(null);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const permission = getNotifyPermission();
    const pref = getNotifyPreference();
    // Prompt until push is granted (needed for closed-app alerts + icon badge).
    setNotifyBanner(permission !== "granted" && permission !== "unsupported" && pref !== "off");
  }, []);

  useEffect(() => {
    if (!session?.authenticated) return;
    void syncPushSubscription(authedFetch);
  }, [session?.authenticated, authedFetch]);

  const load = useCallback(async () => {
    const response = await fetch("/api/conversations", { cache: "no-store" });
    if (response.status === 401 || response.status === 403) {
      // Re-probe session once; SessionGate redirects. Do not DELETE (that caused login blink).
      await refresh();
      throw new Error("unauthorized");
    }
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { error?: string; detail?: string };
      throw new Error(body.detail || body.error || "load_failed");
    }
    const data = (await response.json()) as { conversations: ConversationSummary[]; demo?: boolean };
    setLive(data.demo === false);
    const next = sortSummaries(data.conversations);
    const { map, gained } = detectNewInboundUnread(unreadSnapshot.current, next);
    unreadSnapshot.current = map;
    if (gained.length && canShowDesktopNotification()) {
      const activeId = selectedIdRef.current;
      const tabHidden = typeof document !== "undefined" && document.hidden;
      for (const item of gained) {
        // Skip toast only when user is already reading that chat in a focused tab.
        if (!tabHidden && activeId === item.id) continue;
        const summary = next.find((row) => row.id === item.id);
        if (summary && isMuted(summary.mutedUntil)) continue;
        showDesktopNotification({
          title: item.name || "WhatsApp",
          body: item.body,
          conversationId: item.id,
          tag: `wa-msg-${item.id}`,
        });
      }
    }
    setConversations(next);
    void fetch("/api/whatsapp/status", { cache: "no-store" })
      .then(async (statusResponse) => {
        if (!statusResponse.ok) return;
        const status = (await statusResponse.json()) as { connection?: string };
        setConnected(status.connection === "connected");
      })
      .catch(() => setConnected(false));
    setPhase("ready");
  }, [refresh]);

  useEffect(() => {
    // SessionGate already redirects unauthenticated users. Wait for a confirmed
    // authenticated session before loading — never bounce to /login from a stale null.
    if (!session?.authenticated) return;
    let cancelled = false;
    setPhase("loading");
    const timer = window.setTimeout(() => {
      load().catch((reason) => {
        if (cancelled) return;
        if (reason instanceof Error && reason.message === "unauthorized") return;
        setErrorDetail(
          reason instanceof Error && reason.message !== "load_failed"
            ? reason.message
            : "Could not load conversations. Sign in at /login, then try again.",
        );
        setPhase("error");
      });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [load, session?.authenticated]);

  useEffect(() => {
    if (!live) return;
    const timer = window.setInterval(() => {
      void load().catch(() => undefined);
      if (!selectedId) return;
      void fetch(`/api/conversations/${selectedId}`, { cache: "no-store" })
        .then(async (response) => {
          if (!response.ok) return;
          const data = (await response.json()) as { conversation: ConversationDetail };
          setDetail((current) => (current && current.id === data.conversation.id ? data.conversation : current));
        })
        .catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(timer);
  }, [live, load, selectedId]);

  useEffect(() => {
    if (phase !== "ready") return;
    const total = conversations.reduce((sum, item) => sum + item.unreadCount, 0);
    setUnreadCount(total);
    setDocumentUnreadTitle(total);
    void setAppUnreadBadge(total);
    return () => {
      setDocumentUnreadTitle(0);
      void setAppUnreadBadge(0);
    };
  }, [conversations, phase, setUnreadCount]);

  useEffect(() => {
    setHideMobileNav(pane !== "list");
    return () => setHideMobileNav(false);
  }, [pane, setHideMobileNav]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1280px)");
    const onChange = () => setWideLayout(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (pane === "contact") setPane("chat");
      else if (pane === "chat") setPane("list");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pane]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;

    async function openConversation() {
      try {
        const response = await fetch(`/api/conversations/${selectedId}`, { cache: "no-store" });
        if (!response.ok) throw new Error("load_failed");
        const data = (await response.json()) as { conversation: ConversationDetail };
        if (cancelled) return;
        setDetail(data.conversation);
        setUnreadDivider(data.conversation.unreadCount);
        setDetailPhase("ready");
        if (data.conversation.unreadCount > 0) {
          const readResponse = await authedFetch(`/api/conversations/${selectedId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ markRead: true }),
          });
          if (!readResponse.ok || cancelled) return;
          const readData = (await readResponse.json()) as { summary: ConversationSummary };
          setConversations((items) =>
            items.map((item) => (item.id === readData.summary.id ? readData.summary : item)),
          );
        }
      } catch {
        if (!cancelled) setDetailPhase("error");
      }
    }

    void openConversation();
    return () => {
      cancelled = true;
    };
  }, [selectedId, detailNonce, authedFetch]);

  function selectConversation(id: string, options?: { focusComposer?: boolean }) {
    setPane("chat");
    setFocusComposer(Boolean(options?.focusComposer));
    // Same chat again: keep messages. Clearing detail would leave a blank pane because
    // the load effect only re-runs when selectedId changes.
    if (id === selectedIdRef.current) return;
    setSelectedId(id);
    setDetail(null);
    setDetailPhase("loading");
    setUnreadDivider(0);
  }

  useEffect(() => {
    const chatId = searchParams.get("c");
    if (!chatId) return;
    selectConversation(chatId, { focusComposer: searchParams.get("focus") === "composer" });
    router.replace("/", { scroll: false });
  }, [searchParams, router]);

  function applyUpdate(summary: ConversationSummary, nextDetail: ConversationDetail) {
    setDetail((current) => (current && current.id === nextDetail.id ? nextDetail : current));
    setConversations((items) => sortSummaries(items.map((item) => (item.id === summary.id ? summary : item))));
  }

  async function handleMenuAction(conversation: ConversationSummary, action: ChatMenuAction) {
    try {
      if (action.type === "deleteChat") {
        const response = await authedFetch(`/api/conversations/${conversation.id}`, { method: "DELETE" });
        if (!response.ok) throw new Error("delete_failed");
        setConversations((items) => items.filter((item) => item.id !== conversation.id));
        if (selectedId === conversation.id) {
          setSelectedId(null);
          setDetail(null);
          setDetailPhase("idle");
          setPane("list");
        }
        return;
      }

      const body: Record<string, unknown> = {};
      if (action.type === "archive") body.archived = action.value;
      if (action.type === "pin") body.pinned = action.value;
      if (action.type === "favourite") body.favourite = action.value;
      if (action.type === "mute") body.mute = action.value;
      if (action.type === "markUnread") body.markUnread = true;
      if (action.type === "markRead") body.markRead = true;
      if (action.type === "clearChat") body.clearChat = true;

      const response = await authedFetch(`/api/conversations/${conversation.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error("update_failed");
      const data = (await response.json()) as {
        summary: ConversationSummary;
        conversation: ConversationDetail;
      };
      setConversations((items) => sortSummaries(items.map((item) => (item.id === data.summary.id ? data.summary : item))));
      if (selectedId === conversation.id) {
        setDetail(data.conversation);
        if (action.type === "clearChat") setUnreadDivider(0);
      }
    } catch {
      // Keep UI quiet; next poll refreshes state.
    }
  }

  if (phase === "loading") return <InboxSkeleton />;
  if (phase === "error") {
    return (
      <ErrorState
        title="Could not load conversations"
        detail={errorDetail}
        onRetry={() => {
          setPhase("loading");
          void load().catch(() => setPhase("error"));
        }}
      />
    );
  }

  const showContact = Boolean(selectedId && detail && detail.id === selectedId);

  async function enableDesktopNotifications() {
    const result = await requestNotifyPermission(authedFetch);
    setNotifyBanner(result === "default");
    if (result === "granted") {
      showDesktopNotification({
        title: "WhatsApp CRM",
        body: "Push notifications are on — including when the browser is closed.",
        tag: "wa-notify-enabled",
      });
    }
  }

  function dismissNotifyBanner() {
    setNotifyPreference("off");
    setNotifyBanner(false);
  }

  return (
    <div className="flex min-h-0 min-w-0 max-w-full flex-1 flex-col overflow-x-hidden overscroll-x-none">
      {notifyBanner ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          <p className="inline-flex items-center gap-2">
            <Bell className="h-4 w-4 shrink-0" />
            Enable push notifications for new WhatsApp messages (desktop + mobile, even if the browser is closed).
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void enableDesktopNotifications()}
              className="inline-flex h-8 items-center rounded-lg bg-wa-green px-3 text-xs font-medium text-white hover:bg-wa-green-dark"
            >
              Allow
            </button>
            <button
              type="button"
              onClick={dismissNotifyBanner}
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-amber-300 px-3 text-xs hover:bg-amber-100"
            >
              <BellOff className="h-3.5 w-3.5" />
              Not now
            </button>
          </div>
        </div>
      ) : null}
      <div className="flex min-h-0 min-w-0 max-w-full flex-1 overflow-x-hidden">
      <div
        className={cn(
          "min-h-0 w-full max-w-full shrink-0 flex-col overflow-x-hidden border-wa-line md:w-[340px] md:border-r lg:w-[380px]",
          pane === "list" ? "flex" : "hidden md:flex",
        )}
      >
        <ConversationList
          conversations={conversations}
          selectedId={selectedId}
          query={query}
          filter={filter}
          live={live}
          connected={connected}
          onQuery={setQuery}
          onFilter={setFilter}
          onSelect={selectConversation}
          onMenuAction={(conversation, action) => void handleMenuAction(conversation, action)}
        />
      </div>

      <div
        className={cn(
          "min-h-0 min-w-0 max-w-full flex-1 flex-col overflow-x-hidden bg-wa-app",
          pane === "chat" ? "flex" : "hidden md:flex",
        )}
      >
        {selectedId ? (
          <ChatView
            conversation={detail && detail.id === selectedId ? detail : null}
            phase={detailPhase === "idle" ? "loading" : detailPhase}
            unreadDivider={unreadDivider}
            live={live}
            contactOpen={pane === "contact" || (contactOpen && wideLayout)}
            focusComposer={focusComposer}
            onBack={() => setPane("list")}
            onOpenContact={() => {
              setContactOpen(true);
              setPane("contact");
            }}
            onRetry={() => {
              setDetail(null);
              setDetailPhase("loading");
              setDetailNonce((value) => value + 1);
            }}
            onSent={(nextDetail, summary) => applyUpdate(summary, nextDetail)}
          />
        ) : (
          <EmptyThread live={live} />
        )}
      </div>

      {showContact ? (
        <div
          className={cn(
            "min-h-0 max-w-full shrink-0 flex-col overflow-x-hidden border-l border-wa-line bg-white",
            pane === "contact" ? "flex w-full md:w-[300px] xl:w-[320px]" : "hidden",
            contactOpen && "xl:flex xl:w-[320px]",
          )}
        >
          <ContactPanel
            conversation={detail as ConversationDetail}
            onBack={() => setPane("chat")}
            onClose={() => {
              setContactOpen(false);
              setPane("chat");
            }}
            onUpdated={applyUpdate}
          />
        </div>
      ) : null}
      </div>
    </div>
  );
}
