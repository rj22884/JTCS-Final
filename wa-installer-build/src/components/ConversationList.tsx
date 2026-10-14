"use client";

import { Avatar } from "@/components/Avatar";
import { ChatContextMenu, type ChatMenuAction } from "@/components/ChatContextMenu";
import { cn } from "@/lib/cn";
import { filterSummaries, isMuted } from "@/lib/filter-conversations";
import { formatListTime } from "@/lib/format";
import { FILTERS, type ConversationFilter, type ConversationSummary } from "@/lib/types";
import { Archive, ArrowLeft, BellOff, Heart, Pin, Search } from "lucide-react";
import { useState } from "react";

export function ConversationList({
  conversations,
  selectedId,
  query,
  filter,
  live,
  connected,
  onQuery,
  onFilter,
  onSelect,
  onMenuAction,
}: {
  conversations: ConversationSummary[];
  selectedId: string | null;
  query: string;
  filter: ConversationFilter;
  live: boolean;
  connected: boolean;
  onQuery: (value: string) => void;
  onFilter: (value: ConversationFilter) => void;
  onSelect: (id: string) => void;
  onMenuAction?: (conversation: ConversationSummary, action: ChatMenuAction) => void;
}) {
  const visible = filterSummaries(conversations, query, filter);
  const archivedCount = conversations.filter((item) => item.archived).length;
  const [menu, setMenu] = useState<{ conversation: ConversationSummary; x: number; y: number } | null>(
    null,
  );

  return (
    <section className="flex min-h-0 min-w-0 max-w-full flex-1 flex-col overflow-x-hidden bg-white" aria-label="Conversations">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-wa-line px-4 py-3">
        <div className="min-w-0">
          <h1 className="font-display truncate text-xl font-bold tracking-tight">Chats</h1>
          <p className="text-[13px] font-medium text-wa-muted">{live ? "WhatsApp number" : "Demo conversations"}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {connected ? (
            <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-wa-leaf px-2 py-1 text-[11px] font-medium text-wa-green-dark">
              <span className="h-1.5 w-1.5 rounded-full bg-wa-green" />
              Connected
            </span>
          ) : (
            <>
              <span className="inline-flex shrink-0 items-center rounded-full bg-wa-leaf px-2 py-1 text-[11px] font-medium text-wa-green-dark">
                Demo mode
              </span>
              <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-wa-app px-2 py-1 text-[11px] font-medium text-wa-icon">
                <span className="h-1.5 w-1.5 rounded-full bg-[#8696a0]" />
                Not connected
              </span>
            </>
          )}
        </div>
      </header>

      <div className="px-3 pt-3">
        <label htmlFor="conversation-search" className="sr-only">
          Search conversations
        </label>
        <div className="relative">
          <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-wa-icon" />
          <input
            id="conversation-search"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            placeholder="Search name, phone, or message"
            className="h-10 w-full rounded-lg bg-wa-app pl-10 pr-3 text-base text-wa-ink outline-none placeholder:text-wa-muted focus:ring-2 focus:ring-wa-green md:text-sm"
          />
        </div>
      </div>

      <div
        className="flex flex-wrap gap-1 px-3 py-1.5"
        role="toolbar"
        aria-label="Conversation filters"
      >
        {FILTERS.map((item) => {
          const count = filterSummaries(conversations, "", item.id).length;
          const active = filter === item.id;
          return (
            <button
              key={item.id}
              type="button"
              aria-pressed={active}
              onClick={() => onFilter(item.id)}
              className={cn(
                "h-7 shrink-0 rounded-full px-2 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green sm:text-[13px]",
                active ? "bg-wa-leaf font-medium text-wa-green-dark" : "bg-wa-app text-wa-icon hover:bg-[#e6e8ea]",
              )}
            >
              {item.label} {count}
            </button>
          );
        })}
      </div>

      {filter === "archived" ? (
        <div className="flex items-center gap-2 border-b border-wa-line px-3 py-2">
          <button
            type="button"
            onClick={() => onFilter("all")}
            className="inline-flex h-8 items-center gap-1 rounded-lg px-2 text-sm text-wa-ink hover:bg-wa-app"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </button>
          <p className="text-xs text-wa-muted">Archived chats — right-click a chat → Unarchive chat</p>
        </div>
      ) : null}

      {visible.length === 0 ? (
        <div className="px-6 py-10 text-center">
          <p className="font-medium">{filter === "archived" ? "No archived chats" : "No conversations"}</p>
          <p className="mt-1 text-sm text-wa-muted">
            {query.trim()
              ? `Nothing matches “${query.trim()}”.`
              : filter === "archived"
                ? "When you archive a chat, it appears here. Right-click → Unarchive chat to restore it."
                : live
                  ? "New WhatsApp messages to this number will show up here."
                  : "Nothing is in this filter."}
          </p>
          {query.trim() ? (
            <button
              type="button"
              onClick={() => onQuery("")}
              className="mt-3 text-sm font-medium text-wa-green-dark underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
            >
              Clear search
            </button>
          ) : filter === "archived" ? (
            <button
              type="button"
              onClick={() => onFilter("all")}
              className="mt-3 text-sm font-medium text-wa-green-dark underline-offset-2 hover:underline"
            >
              Back to all chats
            </button>
          ) : null}
        </div>
      ) : (
        <ul className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain overscroll-x-none">
          {filter !== "archived" && archivedCount > 0 ? (
            <li className="px-2">
              <button
                type="button"
                onClick={() => onFilter("archived")}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left hover:bg-[#f7f8fa] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
              >
                <span className="grid h-10 w-10 place-items-center rounded-full bg-wa-app text-wa-icon">
                  <Archive className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1 border-b border-wa-line pb-2">
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-[15px] font-medium">Archived</span>
                    <span className="text-xs font-medium text-wa-muted">{archivedCount}</span>
                  </span>
                  <span className="mt-0.5 block text-sm text-wa-muted">Tap to open · right-click chat to unarchive</span>
                </span>
              </button>
            </li>
          ) : null}
          {visible.map((conversation) => {
            const selected = conversation.id === selectedId;
            const preview =
              conversation.lastDirection === "outbound"
                ? `You: ${conversation.lastMessage}`
                : conversation.lastMessage;
            const muted = isMuted(conversation.mutedUntil);
            return (
              <li key={conversation.id} className="px-2">
                <div
                  className={cn(
                    "flex w-full items-start gap-2 rounded-lg px-2 py-2.5",
                    selected ? "bg-wa-app" : "hover:bg-[#f7f8fa]",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    onContextMenu={(event) => {
                      if (!onMenuAction) return;
                      event.preventDefault();
                      setMenu({ conversation, x: event.clientX, y: event.clientY });
                    }}
                    aria-current={selected ? "true" : undefined}
                    aria-label={`${conversation.name}. ${
                      conversation.unreadCount > 0 ? `${conversation.unreadCount} unread. ` : ""
                    }Last message: ${preview}`}
                    className="flex min-w-0 flex-1 items-start gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
                  >
                    <Avatar name={conversation.name} src={conversation.avatarUrl} />
                    <span className="min-w-0 flex-1 border-b border-wa-line pb-1.5">
                      <span className="flex items-center justify-between gap-2">
                        <span className="flex min-w-0 items-center gap-1">
                          <span className={cn("truncate text-[14px]", conversation.unreadCount > 0 && "font-semibold")}>
                            {conversation.name}
                          </span>
                          {conversation.labels.slice(0, 3).map((label) => (
                            <span
                              key={label}
                              className="shrink-0 rounded bg-wa-app px-1 py-px text-[10px] font-medium uppercase leading-4 text-wa-icon"
                            >
                              {label}
                            </span>
                          ))}
                          {conversation.labels.length > 3 ? (
                            <span className="shrink-0 text-[10px] text-wa-muted">+{conversation.labels.length - 3}</span>
                          ) : null}
                          {conversation.sample || !live ? (
                            <span className="shrink-0 rounded bg-[#fff4cc] px-1 py-px text-[10px] font-medium text-[#6d5a1e]">
                              {conversation.sample ? "Sample" : "Demo"}
                            </span>
                          ) : null}
                          {conversation.status !== "open" ? (
                            <span className="shrink-0 text-[10px] uppercase tracking-wide text-wa-muted">
                              {conversation.status}
                            </span>
                          ) : null}
                        </span>
                        <time
                          dateTime={conversation.lastMessageAt}
                          className={cn(
                            "shrink-0 text-[11px]",
                            conversation.unreadCount > 0 ? "font-medium text-wa-green-dark" : "text-wa-muted",
                          )}
                        >
                          {formatListTime(conversation.lastMessageAt)}
                        </time>
                      </span>
                      <span className="mt-0.5 flex items-center gap-2">
                        <span
                          className={cn(
                            "line-clamp-1 min-w-0 flex-1 break-all text-[13px] leading-4",
                            conversation.unreadCount > 0 ? "font-medium text-wa-ink" : "text-wa-muted",
                          )}
                          title={preview}
                        >
                          {preview}
                        </span>
                        <span className="flex shrink-0 items-center gap-1">
                          {conversation.pinned ? <Pin className="h-3.5 w-3.5 text-wa-muted" aria-label="Pinned" /> : null}
                          {muted ? <BellOff className="h-3.5 w-3.5 text-wa-muted" aria-label="Muted" /> : null}
                          {conversation.favourite ? (
                            <Heart className="h-3.5 w-3.5 fill-wa-green text-wa-green" aria-label="Favourite" />
                          ) : null}
                          {conversation.unreadCount > 0 ? (
                            <span className="grid h-5 min-w-5 place-items-center rounded-full bg-wa-green px-1.5 text-[11px] font-semibold text-white">
                              {conversation.unreadCount}
                            </span>
                          ) : null}
                        </span>
                      </span>
                    </span>
                  </button>
                  {filter === "archived" && onMenuAction ? (
                    <button
                      type="button"
                      onClick={() => onMenuAction(conversation, { type: "archive", value: false })}
                      className="mt-1 shrink-0 rounded-lg border border-wa-line px-2 py-1.5 text-xs font-medium text-wa-green-dark hover:bg-white"
                    >
                      Unarchive
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <ChatContextMenu
        menu={menu}
        onClose={() => setMenu(null)}
        onAction={(conversation, action) => onMenuAction?.(conversation, action)}
      />
    </section>
  );
}
