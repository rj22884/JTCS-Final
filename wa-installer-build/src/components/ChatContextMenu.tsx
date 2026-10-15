"use client";

import { useAppDialog } from "@/components/AppDialog";
import { cn } from "@/lib/cn";
import { isMuted } from "@/lib/filter-conversations";
import type { ConversationSummary, MuteDuration } from "@/lib/types";
import {
  Archive,
  ArchiveRestore,
  BellOff,
  BellRing,
  ChevronRight,
  Heart,
  HeartOff,
  Pin,
  PinOff,
  Trash2,
  Eraser,
  MessageSquareDot,
  MessageSquareCheck,
} from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

export type ChatMenuAction =
  | { type: "archive"; value: boolean }
  | { type: "pin"; value: boolean }
  | { type: "favourite"; value: boolean }
  | { type: "mute"; value: MuteDuration | null }
  | { type: "markUnread" }
  | { type: "markRead" }
  | { type: "clearChat" }
  | { type: "deleteChat" };

type MenuState = {
  conversation: ConversationSummary;
  x: number;
  y: number;
};

export function ChatContextMenu({
  menu,
  onClose,
  onAction,
}: {
  menu: MenuState | null;
  onClose: () => void;
  onAction: (conversation: ConversationSummary, action: ChatMenuAction) => void;
}) {
  const { confirm } = useAppDialog();
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: 0, top: 0 });
  const [muteOpen, setMuteOpen] = useState(false);

  useLayoutEffect(() => {
    if (!menu || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const pad = 8;
    let left = menu.x;
    let top = menu.y;
    if (left + rect.width > window.innerWidth - pad) left = window.innerWidth - rect.width - pad;
    if (top + rect.height > window.innerHeight - pad) top = window.innerHeight - rect.height - pad;
    if (left < pad) left = pad;
    if (top < pad) top = pad;
    setPos({ left, top });
  }, [menu, muteOpen]);

  useEffect(() => {
    if (!menu) return;
    setMuteOpen(false);
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    function onPointer() {
      onClose();
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onPointer, true);
    window.addEventListener("resize", onPointer);
    // Delay so the opening contextmenu click does not instantly close.
    const timer = window.setTimeout(() => {
      window.addEventListener("mousedown", onPointer);
    }, 0);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onPointer, true);
      window.removeEventListener("resize", onPointer);
      window.removeEventListener("mousedown", onPointer);
    };
  }, [menu, onClose]);

  if (!menu) return null;
  const chat = menu.conversation;
  const muted = isMuted(chat.mutedUntil);

  function run(action: ChatMenuAction) {
    onAction(chat, action);
    onClose();
  }

  return (
    <div
      ref={ref}
      role="menu"
      aria-label="Chat options"
      className="fixed z-[80] min-w-[220px] rounded-xl border border-wa-line bg-white py-1.5 text-sm shadow-lg"
      style={{ left: pos.left, top: pos.top }}
      onMouseDown={(event) => event.stopPropagation()}
      onContextMenu={(event) => event.preventDefault()}
    >
      <MenuItem
        icon={chat.archived ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
        label={chat.archived ? "Unarchive chat" : "Archive chat"}
        onClick={() => run({ type: "archive", value: !chat.archived })}
      />

      {muted ? (
        <MenuItem
          icon={<BellRing className="h-4 w-4" />}
          label="Unmute notifications"
          onClick={() => run({ type: "mute", value: null })}
        />
      ) : (
        <div
          className="relative"
          onMouseEnter={() => setMuteOpen(true)}
          onMouseLeave={() => setMuteOpen(false)}
        >
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-wa-app"
            onClick={() => setMuteOpen((value) => !value)}
          >
            <BellOff className="h-4 w-4 text-wa-icon" />
            <span className="flex-1">Mute notifications</span>
            <ChevronRight className="h-4 w-4 text-wa-muted" />
          </button>
          {muteOpen ? (
            <div className="absolute left-full top-0 z-[81] ml-1 min-w-[150px] rounded-xl border border-wa-line bg-white py-1 shadow-lg">
              <MenuItem label="8 hours" onClick={() => run({ type: "mute", value: "8h" })} />
              <MenuItem label="1 week" onClick={() => run({ type: "mute", value: "1w" })} />
              <MenuItem label="Always" onClick={() => run({ type: "mute", value: "always" })} />
            </div>
          ) : null}
        </div>
      )}

      <MenuItem
        icon={chat.pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
        label={chat.pinned ? "Unpin chat" : "Pin chat"}
        onClick={() => run({ type: "pin", value: !chat.pinned })}
      />
      <MenuItem
        icon={
          chat.unreadCount > 0 ? (
            <MessageSquareCheck className="h-4 w-4" />
          ) : (
            <MessageSquareDot className="h-4 w-4" />
          )
        }
        label={chat.unreadCount > 0 ? "Mark as read" : "Mark as unread"}
        onClick={() => run(chat.unreadCount > 0 ? { type: "markRead" } : { type: "markUnread" })}
      />
      <MenuItem
        icon={chat.favourite ? <HeartOff className="h-4 w-4" /> : <Heart className="h-4 w-4" />}
        label={chat.favourite ? "Remove from favourites" : "Add to favourites"}
        onClick={() => run({ type: "favourite", value: !chat.favourite })}
      />

      <div className="my-1 border-t border-wa-line" />

      <MenuItem
        icon={<Eraser className="h-4 w-4" />}
        label="Clear chat"
        onClick={() => {
          void confirm(`Clear all messages in “${chat.name}”? Messages stay on WhatsApp phones.`, {
            title: "Clear chat",
            confirmLabel: "Clear",
            danger: true,
          }).then((ok) => {
            if (ok) run({ type: "clearChat" });
          });
        }}
      />
      <MenuItem
        icon={<Trash2 className="h-4 w-4" />}
        label="Delete chat"
        danger
        onClick={() => {
          void confirm(`Delete chat “${chat.name}” from this inbox?`, {
            title: "Delete chat",
            confirmLabel: "Delete",
            danger: true,
          }).then((ok) => {
            if (ok) run({ type: "deleteChat" });
          });
        }}
      />
    </div>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  danger,
}: {
  icon?: ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-wa-app",
        danger && "text-red-700 hover:bg-red-50",
      )}
    >
      {icon ? <span className={cn("text-wa-icon", danger && "text-red-600")}>{icon}</span> : null}
      <span>{label}</span>
    </button>
  );
}
