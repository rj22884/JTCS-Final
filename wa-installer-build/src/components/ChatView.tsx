"use client";

import { useAppDialog } from "@/components/AppDialog";
import { useAuth } from "@/components/AuthProvider";
import { Avatar } from "@/components/Avatar";
import { DeliveryMark } from "@/components/DeliveryMark";
import { IconButton } from "@/components/IconButton";
import { ErrorState } from "@/components/States";
import { filesFromClipboardData, filesFromClipboardRead } from "@/lib/clipboard-files";
import { cn } from "@/lib/cn";
import { dayKey, formatDateSeparator, formatMessageTime } from "@/lib/format";
import {
  actionsForMessage,
  attachmentCaptionText,
  buildAttachmentDrafts,
  canSendComposer,
  copyTextForMessage,
  DELETE_FOR_EVERYONE_REASON,
  FORWARD_CLOUD_REASON,
  isAttachmentMessage,
  messageAttachments,
  type MessageAction,
} from "@/lib/message-actions";
import {
  COMPOSER_APPEARANCE,
  composerAppearanceCss,
  wrapWaTextStyle,
  type ComposerFontFamily,
  type ComposerFontSize,
  type ComposerTextColor,
  type WaTextStyle,
} from "@/lib/message-format";
import type {
  ConversationDetail,
  ConversationSummary,
  Message,
  MessageAttachment,
  MessageReferral,
} from "@/lib/types";
import {
  attachmentLooksLikeAudio,
  attachmentLooksLikeImage,
  attachmentLooksLikePdf,
  attachmentLooksLikeVideo,
  extractHttpUrls,
  splitTextWithUrls,
} from "@/lib/links";
import {
  ArrowLeft,
  Camera,
  ContactRound,
  FileText,
  Film,
  ImageIcon,
  Info,
  LoaderCircle,
  MapPin,
  Maximize2,
  Minimize2,
  Music,
  Paperclip,
  Send,
  Smile,
  UserPlus,
  X,
} from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ClipboardEvent as ReactClipboardEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";

const MESSAGE_LIMIT = 4096;
const ACCEPT =
  "image/jpeg,image/png,image/webp,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation,text/plain,audio/*,video/mp4,video/3gpp";
const ACCEPT_PHOTOS = "image/*,video/mp4,video/3gpp,video/quicktime";
const ACCEPT_CAMERA = "image/*";
const EMOJIS =
  "😀 😃 😄 😁 😆 😅 😂 🙂 😊 😇 🥰 😍 🤩 😘 😗 😚 😙 🥲 😋 😛 😜 🤪 😝 🤑 🤗 🤭 🤫 🤔 🤐 🤨 😐 😑 😶 😏 😒 🙄 😬 😮‍💨 🤥 😌 😔 😪 🤤 😴 😷 🤒 🤕 🤢 🤮 🥵 🥶 🥴 😵 🤯 🤠 🥳 🥸 😎 🤓 🧐 😕 😟 🙁 ☹️ 😮 😯 😲 😳 🥺 😦 😧 😨 😰 😥 😢 😭 😱 😖 😣 😞 😓 😩 😫 🥱 😤 😡 😠 🤬 😈 👿 💀 👍 👎 👏 🙏 🙌 ✌️ 🤞 🤝 💪 ❤️ 🧡 💛 💚 💙 💜 🖤 🤍 💯 🔥 ✨ ✅ ❌ ⭐ 🎉 🎊".split(
    /\s+/,
  );

type DraftFile = {
  id: string;
  file: File;
  name: string;
  size: number;
  mimeType: string;
  previewUrl: string | null;
};

export function ChatView({
  conversation,
  phase,
  unreadDivider,
  live,
  onBack,
  onOpenContact,
  contactOpen,
  onRetry,
  onSent,
  focusComposer = false,
}: {
  conversation: ConversationDetail | null;
  phase: "idle" | "loading" | "error" | "ready";
  unreadDivider: number;
  live: boolean;
  onBack: () => void;
  onOpenContact: () => void;
  contactOpen: boolean;
  onRetry: () => void;
  onSent: (detail: ConversationDetail, summary: ConversationSummary) => void;
  focusComposer?: boolean;
}) {
  if (phase === "error") {
    return (
      <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-wa-chat">
        <ErrorState title="Could not open this chat" detail="The sample conversation did not load." onRetry={onRetry} />
      </section>
    );
  }

  if (!conversation || phase === "loading") {
    return (
      <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-wa-chat" aria-busy="true">
        <div className="flex h-14 items-center border-b border-black/5 px-3">
          <div className="h-10 w-40 animate-pulse rounded bg-white/70" />
        </div>
        <p className="sr-only">Loading conversation</p>
      </section>
    );
  }

  return (
    <ChatThread
      conversation={conversation}
      unreadDivider={unreadDivider}
      live={live}
      contactOpen={contactOpen}
      onBack={onBack}
      onOpenContact={onOpenContact}
      onSent={onSent}
      focusComposer={focusComposer}
    />
  );
}

function ChatThread({
  conversation,
  unreadDivider,
  live,
  contactOpen,
  onBack,
  onOpenContact,
  onSent,
  focusComposer,
}: {
  conversation: ConversationDetail;
  unreadDivider: number;
  live: boolean;
  contactOpen: boolean;
  onBack: () => void;
  onOpenContact: () => void;
  onSent: (detail: ConversationDetail, summary: ConversationSummary) => void;
  focusComposer: boolean;
}) {
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [viewer, setViewer] = useState<MediaViewerState | null>(null);

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-wa-chat" aria-label={`Messages with ${conversation.name}`}>
      <header className="flex h-14 shrink-0 items-center gap-1 border-b border-black/5 bg-wa-app px-1 md:px-2">
        <IconButton label="Back to conversations" onClick={onBack} className="md:hidden">
          <ArrowLeft className="h-5 w-5" />
        </IconButton>
        <Avatar name={conversation.name} size={40} src={conversation.avatarUrl} />
        <div className="min-w-0 flex-1 px-2">
          <h2 className="font-display truncate text-[15px] font-bold tracking-tight">{conversation.name}</h2>
          <p className="truncate text-xs text-wa-muted">
            {conversation.phone} · {conversation.status}
            {conversation.blocked ? " · Blocked" : ""}
            {conversation.sample ? " · Sample" : live ? "" : " · Demo"}
          </p>
        </div>
        <IconButton label="Contact details" aria-expanded={contactOpen} onClick={onOpenContact}>
          <Info className="h-5 w-5" />
        </IconButton>
      </header>
      {conversation.blocked ? (
        <p className="shrink-0 bg-red-50 px-3 py-1.5 text-center text-[12px] leading-4 text-red-800">
          Contact blocked. New messages from this number are ignored. Unblock to chat again.
        </p>
      ) : null}
      {live ? null : (
        <p className="shrink-0 bg-[#fff8e1] px-3 py-1.5 text-center text-[12px] leading-4 text-[#6d5a1e]">
          Demo conversation. Nothing in this thread is sent to WhatsApp, and the ticks are not live receipts.
        </p>
      )}
      <MessageList
        conversationId={conversation.id}
        messages={conversation.messages}
        unreadDivider={unreadDivider}
        live={live}
        onUpdated={onSent}
        onReply={setReplyTo}
        onOpenViewer={setViewer}
      />
      <Composer
        key={conversation.id}
        conversationId={conversation.id}
        live={live}
        blocked={Boolean(conversation.blocked)}
        replyTo={replyTo}
        onClearReply={() => setReplyTo(null)}
        onSent={onSent}
        focusComposer={focusComposer}
      />
      {viewer ? <MediaViewer viewer={viewer} onClose={() => setViewer(null)} /> : null}
    </section>
  );
}

type MediaViewerState = {
  url: string;
  filename: string;
  mimeType: string;
};

function MessageList({
  conversationId,
  messages,
  unreadDivider,
  live,
  onUpdated,
  onReply,
  onOpenViewer,
}: {
  conversationId: string;
  messages: Message[];
  unreadDivider: number;
  live: boolean;
  onUpdated: (detail: ConversationDetail, summary: ConversationSummary) => void;
  onReply: (message: Message) => void;
  onOpenViewer: (viewer: MediaViewerState) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const dividerIndex = unreadDivider > 0 ? Math.max(messages.length - unreadDivider, 0) : -1;
  const lastMessageId = messages[messages.length - 1]?.id;
  const [menu, setMenu] = useState<{ message: Message; x: number; y: number } | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, lastMessageId]);

  useEffect(() => {
    if (!menu) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenu(null);
    }
    function onPointer() {
      setMenu(null);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onPointer, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onPointer, true);
    };
  }, [menu]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain overscroll-x-none px-3 py-3">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-1">
        {messages.map((message, index) => {
          const showDay = index === 0 || dayKey(messages[index - 1].at) !== dayKey(message.at);
          const outbound = message.direction === "outbound";
          return (
            <div key={message.id}>
              {showDay ? (
                <div className="my-2 flex justify-center">
                  <span className="rounded-lg bg-white px-3 py-1 text-[12px] text-wa-icon shadow-sm">
                    {formatDateSeparator(message.at)}
                  </span>
                </div>
              ) : null}
              {index === dividerIndex ? (
                <div className="my-2 flex items-center gap-2">
                  <span className="h-px flex-1 bg-wa-green/40" />
                  <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-wa-green-dark">
                    {unreadDivider} unread
                  </span>
                  <span className="h-px flex-1 bg-wa-green/40" />
                </div>
              ) : null}
              <MessageBubble
                conversationId={conversationId}
                message={message}
                outbound={outbound}
                live={live}
                onOpenMenu={(next, x, y) => setMenu({ message: next, x, y })}
                onOpenViewer={onOpenViewer}
              />
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
      {menu ? (
        <MessageContextMenu
          conversationId={conversationId}
          message={menu.message}
          x={menu.x}
          y={menu.y}
          live={live}
          onClose={() => setMenu(null)}
          onUpdated={onUpdated}
          onReply={onReply}
          onOpenViewer={onOpenViewer}
        />
      ) : null}
    </div>
  );
}

async function fetchMessageMedia(
  authedFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
  conversationId: string,
  message: Message,
  attachment: MessageAttachment,
  index: number,
  live: boolean,
) {
  if (!attachment.mediaId || !live) {
    throw new Error(attachment.filename || message.body || "Attachment has no downloadable media id.");
  }
  const response = await authedFetch(
    `/api/conversations/${conversationId}/messages/${encodeURIComponent(message.id)}/media?index=${index}`,
  );
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(data.detail || "Could not open media.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  return {
    url,
    filename: attachment.filename || "whatsapp-file",
    mimeType: blob.type || attachment.mimeType || "application/octet-stream",
  };
}

function downloadMediaUrl(url: string, filename: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
}

function MessageBubble({
  conversationId,
  message,
  outbound,
  live,
  onOpenMenu,
  onOpenViewer,
}: {
  conversationId: string;
  message: Message;
  outbound: boolean;
  live: boolean;
  onOpenMenu: (message: Message, x: number, y: number) => void;
  onOpenViewer: (viewer: MediaViewerState) => void;
}) {
  const { authedFetch } = useAuth();
  const pressTimer = useRef<number | null>(null);
  const longPressOpened = useRef(false);
  const attachments = messageAttachments(message);
  const attachment = isAttachmentMessage(message);
  const caption = attachmentCaptionText(message);
  const [mediaError, setMediaError] = useState("");

  function openMenu(event: { clientX: number; clientY: number; preventDefault: () => void }) {
    event.preventDefault();
    longPressOpened.current = true;
    onOpenMenu(message, event.clientX, event.clientY);
  }

  async function openAttachment(item: MessageAttachment, index: number) {
    if (longPressOpened.current) {
      longPressOpened.current = false;
      return;
    }
    setMediaError("");
    try {
      const media = await fetchMessageMedia(authedFetch, conversationId, message, item, index, live);
      onOpenViewer(media);
    } catch (reason) {
      setMediaError(reason instanceof Error ? reason.message : "Could not open attachment.");
    }
  }

  return (
    <div className={cn("flex", outbound ? "justify-end" : "justify-start")}>
      <div
        onContextMenu={(event) => openMenu(event)}
        onKeyDown={(event) => {
          if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
            event.preventDefault();
            const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
            onOpenMenu(message, rect.left + rect.width / 2, rect.top + rect.height / 2);
          }
        }}
        onTouchStart={(event) => {
          longPressOpened.current = false;
          const touch = event.touches[0];
          if (!touch) return;
          pressTimer.current = window.setTimeout(() => {
            longPressOpened.current = true;
            onOpenMenu(message, touch.clientX, touch.clientY);
          }, 480);
        }}
        onTouchEnd={() => {
          if (pressTimer.current) window.clearTimeout(pressTimer.current);
        }}
        onTouchMove={() => {
          if (pressTimer.current) window.clearTimeout(pressTimer.current);
        }}
        className={cn(
          "max-w-[min(92%,32rem)] rounded-lg px-2 py-1.5 shadow-sm outline-none focus-within:ring-2 focus-within:ring-wa-green",
          outbound ? "rounded-br-sm bg-wa-leaf" : "rounded-bl-sm bg-white",
        )}
      >
        {message.referral ? <ReferralCard referral={message.referral} /> : null}
        {attachment ? (
          <ul className="mt-1.5 space-y-1.5">
            {attachments.map((item, index) => (
              <li key={item.id}>
                <AttachmentCard
                  conversationId={conversationId}
                  messageId={message.id}
                  item={item}
                  index={index}
                  live={live}
                  onOpen={() => void openAttachment(item, index)}
                />
              </li>
            ))}
            {caption ? (
              <li>
                <FormattedBody text={caption} />
              </li>
            ) : null}
          </ul>
        ) : message.kind === "location" || message.kind === "contact" ? (
          <div className={message.referral ? "mt-1.5" : undefined}>
            <SpecialMessageCard kind={message.kind} text={message.body} inbound={!outbound} />
          </div>
        ) : isTemplateMessage(message) ? (
          <div className={message.referral ? "mt-1.5" : undefined}>
            <TemplateBody text={message.body} />
          </div>
        ) : (
          <div className={message.referral ? "mt-1.5" : undefined}>
            <FormattedBody text={message.body} />
          </div>
        )}
        <p className="mt-0.5 flex items-center justify-end gap-1 text-[11px] text-wa-muted">
          <time dateTime={message.at}>{formatMessageTime(message.at)}</time>
          {message.delivery ? <DeliveryMark status={message.delivery} /> : null}
        </p>
        {mediaError ? <p className="pb-0.5 text-[11px] text-red-700">{mediaError}</p> : null}
        {message.delivery === "failed" ? (
          <p className="max-w-[min(92%,32rem)] pb-0.5 text-right text-[11px] text-red-700">
            {message.deliveryError?.trim() || "Meta did not accept this message."}
          </p>
        ) : null}
        {message.delivery === "not_sent" ? (
          <p className="pb-0.5 text-right text-[11px] text-[#9a6b12]">Saved here only. Not sent to WhatsApp.</p>
        ) : null}
      </div>
    </div>
  );
}

function isTemplateMessage(message: Message) {
  if (message.kind === "template") return true;
  return /^Template:\s+\S+/i.test(message.body.trim());
}

function parseSharedContact(text: string) {
  const cleaned = text.replace(/^👤\s*/gm, "").trim();
  const telMatch = cleaned.match(/(\+?\d[\d\s-]{7,}\d)/);
  const phone = telMatch ? telMatch[1].replace(/[^\d+]/g, "") : "";
  const namePart = cleaned
    .split(/[·|]/)
    .map((part) => part.trim())
    .find((part) => part && !/^\+?\d[\d\s-]{7,}\d$/.test(part));
  const name = (namePart || cleaned.split("\n")[0] || "Contact").replace(/^👤\s*/, "").trim();
  return { name: name || "Contact", phone };
}

function SpecialMessageCard({
  kind,
  text,
  inbound,
}: {
  kind: "location" | "contact";
  text: string;
  inbound: boolean;
}) {
  const { authedFetch } = useAuth();
  const { alert } = useAppDialog();
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveNote, setSaveNote] = useState("");
  const cleaned = text.replace(/^📍\s*/, "").replace(/^👤\s*/gm, "").trim();
  const coordMatch = cleaned.match(/(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)/);
  const mapsQuery =
    kind === "location"
      ? coordMatch
        ? `${coordMatch[1]},${coordMatch[2]}`
        : cleaned.split("\n").filter(Boolean).join(", ")
      : "";
  const mapsUrl =
    kind === "location" && mapsQuery
      ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(mapsQuery)}`
      : null;
  const shared = kind === "contact" ? parseSharedContact(text) : null;
  const telHref = shared?.phone ? `tel:${shared.phone}` : null;

  async function saveSharedContact() {
    if (!shared?.phone) {
      await alert("Is contact card me mobile number nahi mila.", { title: "Save contact" });
      return;
    }
    setSaveBusy(true);
    setSaveNote("");
    try {
      const response = await authedFetch("/api/contacts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: shared.name, mobile: shared.phone }),
      });
      const data = (await response.json().catch(() => ({}))) as { detail?: string; error?: string };
      if (response.status === 409) {
        setSaveNote("Already saved in Contacts.");
        return;
      }
      if (!response.ok) {
        setSaveNote(data.detail || data.error || "Could not save contact.");
        return;
      }
      setSaveNote("Contact saved.");
    } catch {
      setSaveNote("Could not save contact.");
    } finally {
      setSaveBusy(false);
    }
  }

  return (
    <div className="min-w-[12rem] rounded-md border border-wa-line/80 bg-white/70 px-2.5 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-wa-muted">
        {kind === "location" ? "Location" : "Contact"}
      </p>
      <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-5 text-wa-ink">{text}</p>
      {mapsUrl ? (
        <a
          href={mapsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1.5 inline-block text-xs font-medium text-wa-green-dark underline-offset-2 hover:underline"
        >
          Open in Maps
        </a>
      ) : null}
      {telHref ? (
        <a href={telHref} className="mt-1.5 block text-xs font-medium text-wa-green-dark underline-offset-2 hover:underline">
          Call number
        </a>
      ) : null}
      {kind === "contact" && inbound ? (
        <button
          type="button"
          disabled={saveBusy}
          onClick={() => void saveSharedContact()}
          className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-lg bg-wa-green px-2.5 text-xs font-medium text-white hover:bg-wa-green-dark disabled:opacity-50"
        >
          <UserPlus className="h-3.5 w-3.5" />
          {saveBusy ? "Saving…" : "Save contact"}
        </button>
      ) : null}
      {saveNote ? <p className="mt-1 text-[11px] text-wa-muted">{saveNote}</p> : null}
    </div>
  );
}

function TemplateBody({ text }: { text: string }) {
  const lines = text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const titleLine = lines[0] || "Template";
  const title = titleLine.replace(/^Template:\s*/i, "") || "Template";
  const buttonLine = lines.find((line) => /\[[^\]]+\]/.test(line) && line === lines[lines.length - 1]);
  const contentLines = lines.slice(1).filter((line) => line !== buttonLine);
  const buttons = buttonLine
    ? [...buttonLine.matchAll(/\[([^\]]+)\]/g)].map((match) => match[1].trim()).filter(Boolean)
    : [];

  return (
    <div className="min-w-[12rem] max-w-sm overflow-hidden rounded-md border border-wa-line/70 bg-white/80">
      <div className="border-b border-wa-line/70 bg-wa-app px-2.5 py-1.5">
        <p className="text-[11px] font-medium uppercase tracking-wide text-wa-muted">Template</p>
        <p className="truncate text-[13px] font-semibold text-wa-ink">{title}</p>
      </div>
      <div className="space-y-1.5 px-2.5 py-2">
        {contentLines.length > 0 ? (
          contentLines.map((line, index) => (
            <p key={`${index}-${line.slice(0, 24)}`} className="whitespace-pre-wrap text-[14px] leading-5 [overflow-wrap:anywhere]">
              {line}
            </p>
          ))
        ) : (
          <p className="text-[13px] text-wa-muted">Sent to WhatsApp</p>
        )}
        {buttons.length > 0 ? (
          <ul className="mt-1 space-y-1 border-t border-wa-line/60 pt-1.5">
            {buttons.map((label) => (
              <li
                key={label}
                className="rounded-md border border-wa-line bg-white px-2 py-1 text-center text-[12px] font-medium text-wa-green-dark"
              >
                {label}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function FormattedBody({ text }: { text: string }) {
  const urls = extractHttpUrls(text, 3);
  const parts = text.split(/(\*[^*\n]+\*|_[^_\n]+_|~[^~\n]+~|```[\s\S]*?```)/g);
  return (
    <div className="space-y-1.5">
      <p className="whitespace-pre-wrap text-[14.5px] leading-5 [overflow-wrap:anywhere]">
        {parts.map((part, index) => {
          if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
            return <strong key={index}>{renderInlineWithLinks(part.slice(1, -1), `${index}-b`)}</strong>;
          }
          if (part.startsWith("_") && part.endsWith("_") && part.length > 2) {
            return <em key={index}>{renderInlineWithLinks(part.slice(1, -1), `${index}-i`)}</em>;
          }
          if (part.startsWith("~") && part.endsWith("~") && part.length > 2) {
            return (
              <span key={index} className="line-through">
                {renderInlineWithLinks(part.slice(1, -1), `${index}-s`)}
              </span>
            );
          }
          if (part.startsWith("```") && part.endsWith("```") && part.length > 6) {
            return (
              <code key={index} className="rounded bg-black/5 px-1 font-mono text-[13px]">
                {part.slice(3, -3)}
              </code>
            );
          }
          return <span key={index}>{renderInlineWithLinks(part, `${index}-t`)}</span>;
        })}
      </p>
      {urls.length > 0 ? (
        <ul className="space-y-1.5">
          {urls.map((url) => (
            <li key={url}>
              <LinkPreviewCard url={url} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function renderInlineWithLinks(text: string, keyPrefix: string) {
  return splitTextWithUrls(text).map((part, index) => {
    if (part.type === "url") {
      return (
        <a
          key={`${keyPrefix}-${index}`}
          href={part.value}
          target="_blank"
          rel="noopener noreferrer"
          className="break-all text-wa-green-dark underline underline-offset-2 hover:text-wa-green"
          onClick={(event) => event.stopPropagation()}
        >
          {part.value}
        </a>
      );
    }
    return <span key={`${keyPrefix}-${index}`}>{part.value}</span>;
  });
}

function LinkPreviewCard({ url }: { url: string }) {
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [preview, setPreview] = useState<{
    title: string;
    description: string;
    image: string | null;
    siteName: string;
    url: string;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPhase("loading");
    void fetch(`/api/link-preview?url=${encodeURIComponent(url)}`, { cache: "no-store" })
      .then(async (response) => {
        const data = (await response.json().catch(() => ({}))) as {
          preview?: { title: string; description: string; image: string | null; siteName: string; url: string };
        };
        if (cancelled) return;
        if (!response.ok || !data.preview) {
          setPhase("error");
          return;
        }
        setPreview(data.preview);
        setPhase("ready");
      })
      .catch(() => {
        if (!cancelled) setPhase("error");
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (phase === "error") {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="block overflow-hidden rounded-md border border-wa-line bg-white/80 px-2.5 py-2 text-[12px] text-wa-green-dark hover:bg-white"
        onClick={(event) => event.stopPropagation()}
      >
        <span className="block truncate font-medium">{safeHostname(url)}</span>
        <span className="mt-0.5 block truncate text-wa-muted">{url}</span>
      </a>
    );
  }

  return (
    <a
      href={preview?.url || url}
      target="_blank"
      rel="noopener noreferrer"
      className="block overflow-hidden rounded-md border border-wa-line bg-white text-wa-ink hover:bg-white"
      onClick={(event) => event.stopPropagation()}
    >
      {phase === "ready" && preview?.image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={preview.image}
          alt=""
          className="max-h-40 w-full object-cover"
          loading="lazy"
          referrerPolicy="no-referrer"
        />
      ) : null}
      <div className="space-y-0.5 px-2.5 py-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-wa-muted">
          {phase === "loading" ? "Loading preview…" : preview?.siteName || safeHostname(url)}
        </p>
        <p className="font-display text-[13px] font-bold leading-5 tracking-tight">
          {phase === "ready" ? preview?.title || safeHostname(url) : safeHostname(url)}
        </p>
        {phase === "ready" && preview?.description ? (
          <p className="line-clamp-2 text-[12px] leading-4 text-wa-ink/80">{preview.description}</p>
        ) : null}
      </div>
    </a>
  );
}

function safeHostname(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./i, "");
  } catch {
    return url;
  }
}

function AttachmentCard({
  conversationId,
  messageId,
  item,
  index,
  live,
  onOpen,
}: {
  conversationId: string;
  messageId: string;
  item: MessageAttachment;
  index: number;
  live: boolean;
  onOpen: () => void;
}) {
  const { authedFetch } = useAuth();
  const canPreview = Boolean(item.mediaId);
  const isImage = attachmentLooksLikeImage(item);
  const isVideo = attachmentLooksLikeVideo(item);
  const isAudio = attachmentLooksLikeAudio(item);
  const isPdf = attachmentLooksLikePdf(item);
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  const [thumbFailed, setThumbFailed] = useState(false);
  const kindLabel = isImage ? "Photo" : isVideo ? "Video" : isAudio ? "Audio" : isPdf ? "PDF" : "Document";
  const Icon = isImage ? ImageIcon : isVideo ? Film : isAudio ? Music : FileText;
  const showMedia = canPreview && (isImage || isVideo) && thumbUrl && !thumbFailed;

  useEffect(() => {
    if (!canPreview || (!isImage && !isVideo && !isAudio) || !live) return;
    let cancelled = false;
    let objectUrl = "";
    void (async () => {
      try {
        const response = await authedFetch(
          `/api/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/media?index=${index}&inline=1`,
        );
        if (!response.ok) throw new Error("media_failed");
        const blob = await response.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setThumbUrl(objectUrl);
        setThumbFailed(false);
      } catch {
        if (!cancelled) setThumbFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [authedFetch, canPreview, conversationId, index, isAudio, isImage, isVideo, live, messageId]);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="block w-full max-w-full overflow-hidden rounded-md border border-wa-line/80 bg-white/70 text-left hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
      aria-label={`Open ${item.filename}`}
      title={item.filename}
    >
      {showMedia && isImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={thumbUrl}
          alt=""
          className="max-h-72 w-full bg-black/5 object-cover"
          loading="lazy"
          onError={() => setThumbFailed(true)}
        />
      ) : null}
      {showMedia && isVideo ? (
        <video
          src={thumbUrl}
          className="max-h-72 w-full bg-black object-contain"
          muted
          playsInline
          preload="metadata"
          onError={() => setThumbFailed(true)}
        />
      ) : null}
      {canPreview && isAudio && thumbUrl ? (
        <div className="px-2 pt-2" onClick={(event) => event.stopPropagation()}>
          <audio controls preload="metadata" src={thumbUrl} className="w-full" />
        </div>
      ) : null}
      <span className="flex min-w-0 items-start gap-2 px-2 py-2">
        {!showMedia ? (
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-wa-coral/15 text-wa-coral">
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
        ) : null}
        <span className="min-w-0 flex-1">
          {showMedia && isImage ? null : (
            <span className="block whitespace-pre-wrap break-all text-[14px] font-medium leading-5 text-wa-ink">
              {item.filename === "image" || item.filename === "Photo" ? kindLabel : item.filename}
            </span>
          )}
          <span className="mt-0.5 block text-[11px] text-wa-muted">
            {kindLabel}
            {" · "}
            {canPreview ? "Tap to open" : "No downloadable media id"}
          </span>
        </span>
      </span>
    </button>
  );
}

function ReferralCard({ referral }: { referral: MessageReferral }) {
  const image = referral.imageUrl || referral.thumbnailUrl;
  const title = referral.headline || "Facebook / Instagram ad";
  const detail = referral.body;
  return (
    <article className="overflow-hidden rounded-md border border-wa-line bg-white text-wa-ink">
      {image ? (
        // Meta CDN URLs are short-lived; plain img avoids next/image domain allowlists.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={image} alt="" className="max-h-56 w-full object-cover" loading="lazy" referrerPolicy="no-referrer" />
      ) : null}
      <div className="space-y-1 px-2.5 py-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-wa-muted">
          {referral.sourceType === "ad" ? "Click to WhatsApp ad" : referral.sourceType || "Referral"}
        </p>
        <p className="font-display text-[14px] font-bold leading-5 tracking-tight">{title}</p>
        {detail ? <p className="whitespace-pre-wrap text-[13px] leading-5 text-wa-ink/90 [overflow-wrap:anywhere]">{detail}</p> : null}
        {referral.sourceUrl ? (
          <a
            href={referral.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block break-all text-[12px] font-medium text-wa-green-dark hover:underline"
          >
            View ad source
          </a>
        ) : null}
      </div>
    </article>
  );
}

function MessageContextMenu({
  conversationId,
  message,
  x,
  y,
  live,
  onClose,
  onUpdated,
  onReply,
  onOpenViewer,
}: {
  conversationId: string;
  message: Message;
  x: number;
  y: number;
  live: boolean;
  onClose: () => void;
  onUpdated: (detail: ConversationDetail, summary: ConversationSummary) => void;
  onReply: (message: Message) => void;
  onOpenViewer: (viewer: MediaViewerState) => void;
}) {
  const { authedFetch } = useAuth();
  const { confirm } = useAppDialog();
  const actions = actionsForMessage(message);
  const menuRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const first = menuRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)");
    first?.focus();
  }, []);

  async function run(action: MessageAction) {
    if (!action.enabled || busy) {
      if (action.id === "delete_for_everyone") setError(DELETE_FOR_EVERYONE_REASON);
      return;
    }
    if (action.id === "reply") {
      onReply(message);
      onClose();
      return;
    }
    if (action.id === "forward") {
      await navigator.clipboard.writeText(copyTextForMessage(message));
      setError(FORWARD_CLOUD_REASON);
      window.setTimeout(() => onClose(), 1200);
      return;
    }
    if (action.id === "copy") {
      await navigator.clipboard.writeText(copyTextForMessage(message));
      onClose();
      return;
    }
    if (action.id === "view" || action.id === "save" || action.id === "save_all") {
      const attachments = messageAttachments(message);
      const indexes =
        action.id === "save_all" ? attachments.map((_, index) => index) : [0];
      try {
        for (const index of indexes) {
          const attachment = attachments[index];
          if (!attachment) continue;
          if (!live) {
            setError("Media download needs a connected WhatsApp Business account.");
            return;
          }
          const media = await fetchMessageMedia(
            authedFetch,
            conversationId,
            message,
            attachment,
            index,
            live,
          );
          if (action.id === "view") {
            onOpenViewer(media);
          } else {
            downloadMediaUrl(media.url, media.filename);
            window.setTimeout(() => URL.revokeObjectURL(media.url), 30_000);
          }
        }
        onClose();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Could not open media.");
      }
      return;
    }
    if (action.id === "delete_for_me") {
      const ok = await confirm("Delete this message for you? It will be removed from this inbox history.", {
        title: "Delete message",
        confirmLabel: "Delete",
        danger: true,
      });
      if (!ok) return;
      setBusy(true);
      setError("");
      try {
        const response = await authedFetch(`/api/conversations/${conversationId}/messages/${encodeURIComponent(message.id)}`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scope: "me" }),
        });
        const data = (await response.json()) as {
          conversation?: ConversationDetail;
          summary?: ConversationSummary;
          detail?: string;
        };
        if (!response.ok || !data.conversation || !data.summary) throw new Error(data.detail || "delete_failed");
        onUpdated(data.conversation, data.summary);
        onClose();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Could not delete the message.");
      } finally {
        setBusy(false);
      }
      return;
    }
    if (action.id === "delete_for_everyone") {
      setError(DELETE_FOR_EVERYONE_REASON);
    }
  }

  function onMenuKey(event: ReactKeyboardEvent<HTMLDivElement>) {
    const buttons = [...(menuRef.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      buttons[(index + 1 + buttons.length) % buttons.length]?.focus();
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      buttons[(index - 1 + buttons.length) % buttons.length]?.focus();
    }
  }

  const left = Math.min(x, typeof window !== "undefined" ? window.innerWidth - 240 : x);
  const top = Math.min(y, typeof window !== "undefined" ? window.innerHeight - 280 : y);

  return (
    <div className="fixed inset-0 z-40" onMouseDown={onClose} role="presentation">
      <div
        ref={menuRef}
        role="menu"
        aria-label="Message actions"
        style={{ left, top }}
        className="absolute w-56 rounded-lg border border-black/10 bg-white p-1 shadow-lg"
        onMouseDown={(event: ReactMouseEvent) => event.stopPropagation()}
        onKeyDown={onMenuKey}
      >
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            role="menuitem"
            disabled={!action.enabled || busy}
            title={action.detail}
            onClick={() => void run(action)}
            className="flex w-full flex-col rounded-md px-2 py-1.5 text-left text-sm hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:cursor-not-allowed disabled:opacity-45"
          >
            <span>{action.label}</span>
            {action.id === "delete_for_everyone" || action.id === "forward" ? (
              <span className="text-[11px] text-wa-muted">
                {action.id === "forward" ? "Copies content (no Cloud API forward)" : "Not supported by Cloud API"}
              </span>
            ) : null}
          </button>
        ))}
        {error ? <p className="px-2 py-1 text-[11px] text-red-700">{error}</p> : null}
      </div>
    </div>
  );
}

function MediaViewer({ viewer, onClose }: { viewer: MediaViewerState; onClose: () => void }) {
  const [maximized, setMaximized] = useState(false);
  const isImage = viewer.mimeType.startsWith("image/");
  const isPdf = viewer.mimeType.includes("pdf") || /\.pdf$/i.test(viewer.filename);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      URL.revokeObjectURL(viewer.url);
    };
  }, [onClose, viewer.url]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3 md:p-6" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={viewer.filename}
        className={cn(
          "flex flex-col overflow-hidden rounded-lg border border-wa-line bg-white shadow-xl",
          maximized ? "h-[96dvh] w-[96vw]" : "h-[min(80dvh,720px)] w-[min(92vw,860px)]",
        )}
      >
        <header className="flex shrink-0 items-center gap-2 border-b border-wa-line bg-wa-app px-2 py-1.5">
          <p className="min-w-0 flex-1 truncate text-sm font-medium" title={viewer.filename}>
            {viewer.filename}
          </p>
          {!maximized ? (
            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
              aria-label="Maximize"
              title="Maximize"
              onClick={() => setMaximized(true)}
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          ) : (
            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
              aria-label="Restore"
              title="Restore"
              onClick={() => setMaximized(false)}
            >
              <Minimize2 className="h-4 w-4" />
            </button>
          )}
          <button
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
            aria-label="Close"
            title="Close"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="min-h-0 flex-1 bg-[#111]/80">
          {isImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={viewer.url} alt={viewer.filename} className="h-full w-full object-contain" />
          ) : isPdf || viewer.mimeType.startsWith("text/") || viewer.mimeType.startsWith("video/") || viewer.mimeType.startsWith("audio/") ? (
            <iframe title={viewer.filename} src={viewer.url} className="h-full w-full border-0 bg-white" />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 px-4 text-center text-white">
              <FileText className="h-10 w-10" />
              <p className="text-sm">Preview is not available for this file type in the popup.</p>
              <button
                type="button"
                className="rounded-md bg-wa-green px-3 py-1.5 text-sm font-medium text-white"
                onClick={() => downloadMediaUrl(viewer.url, viewer.filename)}
              >
                Download file
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

type TemplateOption = {
  id: string;
  name: string;
  language: string;
  status: string;
  category: string;
  headerText?: string;
  bodyText?: string;
  footerText?: string;
  buttonLabels?: string[];
  preview?: string;
};

function Composer({
  conversationId,
  live,
  blocked = false,
  replyTo,
  onClearReply,
  onSent,
  focusComposer = false,
}: {
  conversationId: string;
  live: boolean;
  blocked?: boolean;
  replyTo: Message | null;
  onClearReply: () => void;
  onSent: (detail: ConversationDetail, summary: ConversationSummary) => void;
  focusComposer?: boolean;
}) {
  const { authedFetch } = useAuth();
  const { alert } = useAppDialog();
  const [body, setBody] = useState("");
  const [drafts, setDrafts] = useState<DraftFile[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [templates, setTemplates] = useState<TemplateOption[] | null>(null);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [fontFamily, setFontFamily] = useState<ComposerFontFamily>("default");
  const [fontSize, setFontSize] = useState<ComposerFontSize>("default");
  const [textColor, setTextColor] = useState<ComposerTextColor>("default");
  const [composerMenu, setComposerMenu] = useState<{ x: number; y: number } | null>(null);
  const [attachOpen, setAttachOpen] = useState(false);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [contactFormOpen, setContactFormOpen] = useState(false);
  const [contactDraft, setContactDraft] = useState({ name: "", phone: "" });
  /** Desktop (fine pointer + hover): Enter sends. Mobile/touch: Enter inserts a new line. */
  const [enterSends, setEnterSends] = useState(true);
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const photosRef = useRef<HTMLInputElement>(null);
  const formatId = useId();

  useEffect(() => {
    if (replyTo || focusComposer) fieldRef.current?.focus();
  }, [replyTo, focusComposer]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia("(hover: hover) and (pointer: fine)");
    const sync = () => setEnterSends(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    return () => {
      for (const draft of drafts) {
        if (draft.previewUrl) URL.revokeObjectURL(draft.previewUrl);
      }
    };
  }, [drafts]);

  function resize(element: HTMLTextAreaElement) {
    element.style.height = "40px";
    element.style.height = `${Math.min(element.scrollHeight, 120)}px`;
  }

  function applyStyle(style: WaTextStyle) {
    const field = fieldRef.current;
    if (!field) return;
    const start = field.selectionStart ?? body.length;
    const end = field.selectionEnd ?? body.length;
    const next = wrapWaTextStyle(body, start, end, style);
    setBody(next.body);
    window.requestAnimationFrame(() => {
      field.focus();
      field.setSelectionRange(next.selectionStart, next.selectionEnd);
      resize(field);
    });
  }

  function addFiles(fileList: FileList | File[] | null) {
    if (!fileList || (Array.isArray(fileList) ? fileList.length === 0 : fileList.length === 0)) return;
    if (!live) {
      setError("Attachments need a connected WhatsApp Business account.");
      return;
    }
    const built = buildAttachmentDrafts(fileList, drafts.length);
    if (built.error) {
      setError(built.error);
      return;
    }
    setError("");
    setDrafts((current) => [
      ...current,
      ...built.drafts.map((item) => ({
        ...item,
        previewUrl: item.mimeType.startsWith("image/") ? URL.createObjectURL(item.file) : null,
      })),
    ]);
    if (fileRef.current) fileRef.current.value = "";
    if (cameraRef.current) cameraRef.current.value = "";
    if (photosRef.current) photosRef.current.value = "";
  }

  function insertEmoji(emoji: string) {
    const field = fieldRef.current;
    const start = field?.selectionStart ?? body.length;
    const end = field?.selectionEnd ?? body.length;
    const next = `${body.slice(0, start)}${emoji}${body.slice(end)}`;
    setBody(next);
    window.requestAnimationFrame(() => {
      if (!field) return;
      const cursor = start + emoji.length;
      field.focus();
      field.setSelectionRange(cursor, cursor);
      resize(field);
    });
  }

  async function sendLocationShare() {
    if (blocked || !live || sending) return;
    if (!navigator.geolocation) {
      await alert("Location is not available on this device/browser.", { title: "Location" });
      return;
    }
    setSending(true);
    setError("");
    setAttachOpen(false);
    try {
      const position = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 15000,
          maximumAge: 0,
        });
      });
      const response = await authedFetch(`/api/conversations/${conversationId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "location",
          location: {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            name: "Current location",
          },
        }),
      });
      await applySendResponse(response);
    } catch (reason) {
      const detail =
        reason && typeof reason === "object" && "code" in reason
          ? "Location permission denied or unavailable."
          : "Could not share location.";
      setError(detail);
    } finally {
      setSending(false);
    }
  }

  async function sendContactShare(name: string, phone: string) {
    if (blocked || !live || sending) return;
    setSending(true);
    setError("");
    setAttachOpen(false);
    setContactFormOpen(false);
    try {
      const response = await authedFetch(`/api/conversations/${conversationId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "contact", contact: { name, phone } }),
      });
      await applySendResponse(response);
    } catch {
      setError("Could not send contact.");
    } finally {
      setSending(false);
    }
  }

  async function pickDeviceContact() {
    setAttachOpen(false);
    const nav = navigator as Navigator & {
      contacts?: { select: (props: string[], options: { multiple: boolean }) => Promise<Array<{ name?: string[]; tel?: string[] }>> };
    };
    if (nav.contacts?.select) {
      try {
        const picked = await nav.contacts.select(["name", "tel"], { multiple: false });
        const first = picked[0];
        const name = first?.name?.[0]?.trim() || "Contact";
        const phone = first?.tel?.[0]?.trim() || "";
        if (phone) {
          await sendContactShare(name, phone);
          return;
        }
      } catch {
        // Fall through to manual form when picker is cancelled/unsupported.
      }
    }
    setContactDraft({ name: "", phone: "" });
    setContactFormOpen(true);
  }

  function handlePaste(event: ReactClipboardEvent) {
    const files = filesFromClipboardData(event.clipboardData);
    if (files.length === 0) return;
    event.preventDefault();
    addFiles(files);
  }

  async function pasteFromClipboardMenu() {
    setComposerMenu(null);
    const files = await filesFromClipboardRead();
    if (files.length > 0) {
      addFiles(files);
      return;
    }
    try {
      const text = await navigator.clipboard.readText();
      if (!text) {
        setError("Clipboard has no file or text to paste.");
        return;
      }
      const field = fieldRef.current;
      if (!field) {
        setBody((current) => `${current}${text}`);
        return;
      }
      const start = field.selectionStart ?? body.length;
      const end = field.selectionEnd ?? body.length;
      const next = `${body.slice(0, start)}${text}${body.slice(end)}`;
      setBody(next);
      window.requestAnimationFrame(() => {
        field.focus();
        const cursor = start + text.length;
        field.setSelectionRange(cursor, cursor);
        resize(field);
      });
    } catch {
      setError("Could not read clipboard. Use Ctrl+V, or allow clipboard permission.");
    }
  }

  function removeDraft(id: string) {
    setDrafts((current) => {
      const target = current.find((item) => item.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return current.filter((item) => item.id !== id);
    });
  }

  async function applySendResponse(response: Response) {
    const data = (await response.json()) as {
      conversation?: ConversationDetail;
      summary?: ConversationSummary;
      delivery?: string;
      detail?: string;
    };
    if (!response.ok || !data.conversation || !data.summary) {
      throw new Error(data.detail || "send_failed");
    }
    onSent(data.conversation, data.summary);
    if (data.delivery === "failed") setError(data.detail || "Meta did not accept the message.");
  }

  async function send() {
    if (blocked) {
      setError("This contact is blocked. Unblock to send messages.");
      return;
    }
    if (!canSendComposer(body, drafts.length, sending)) return;
    const text = body.trim();
    if (text.length > MESSAGE_LIMIT) return;
    setSending(true);
    setError("");
    setTemplatesOpen(false);
    try {
      if (drafts.length > 0) {
        if (!live) throw new Error("Attachments need a connected WhatsApp Business account.");
        const form = new FormData();
        for (const draft of drafts) form.append("file", draft.file, draft.name);
        if (text) form.append("caption", text);
        const response = await authedFetch(`/api/conversations/${conversationId}/media`, {
          method: "POST",
          body: form,
        });
        await applySendResponse(response);
        for (const draft of drafts) {
          if (draft.previewUrl) URL.revokeObjectURL(draft.previewUrl);
        }
        setDrafts([]);
        setBody("");
        if (fieldRef.current) fieldRef.current.style.height = "40px";
        return;
      }
      if (!text) return;
      const response = await authedFetch(`/api/conversations/${conversationId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          body: text,
          replyToMessageId: replyTo?.id?.startsWith("wamid.") ? replyTo.id : undefined,
        }),
      });
      await applySendResponse(response);
      setBody("");
      onClearReply();
      if (fieldRef.current) fieldRef.current.style.height = "40px";
    } catch (reason) {
      setError(
        reason instanceof Error && reason.message !== "send_failed"
          ? reason.message
          : live
            ? "Could not send the WhatsApp message."
            : "Could not save the demo message.",
      );
    } finally {
      setSending(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function openTemplates() {
    if (!live || sending) return;
    if (templatesOpen) {
      setTemplatesOpen(false);
      return;
    }
    setTemplatesOpen(true);
    if (templates) return;
    setTemplatesLoading(true);
    setError("");
    try {
      const response = await authedFetch("/api/whatsapp/templates");
      const data = (await response.json()) as { templates?: TemplateOption[]; detail?: string };
      if (!response.ok || !data.templates) throw new Error(data.detail || "Could not load templates.");
      setTemplates(data.templates);
    } catch (reason) {
      setTemplates([]);
      setError(reason instanceof Error ? reason.message : "Could not load templates.");
    } finally {
      setTemplatesLoading(false);
    }
  }

  async function sendTemplate(template: TemplateOption) {
    if (!live || sending) return;
    setSending(true);
    setError("");
    setTemplatesOpen(false);
    try {
      const preview =
        template.preview?.trim() ||
        [
          `Template: ${template.name}`,
          template.headerText,
          template.bodyText,
          template.footerText,
          (template.buttonLabels || []).map((label) => `[${label}]`).join(" · "),
        ]
          .filter(Boolean)
          .join("\n\n");
      const response = await authedFetch(`/api/conversations/${conversationId}/templates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: template.name, language: template.language, preview }),
      });
      await applySendResponse(response);
    } catch (reason) {
      setError(reason instanceof Error && reason.message !== "send_failed" ? reason.message : "Could not send the template.");
    } finally {
      setSending(false);
    }
  }

  const canSend = !blocked && canSendComposer(body, drafts.length, sending);

  return (
    <form
      className="relative shrink-0 bg-wa-app px-2 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]"
      onSubmit={(event) => {
        // Never send via implicit form submit — only the Send button or desktop Enter.
        event.preventDefault();
      }}
      onPaste={handlePaste}
      onContextMenu={(event) => {
        // Custom menu so Paste works for files copied from Explorer (browser file paste).
        if (!live || sending) return;
        event.preventDefault();
        setComposerMenu({ x: event.clientX, y: event.clientY });
      }}
    >
      {composerMenu ? (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setComposerMenu(null)}
          onContextMenu={(event) => {
            event.preventDefault();
            setComposerMenu(null);
          }}
        >
          <div
            role="menu"
            className="absolute z-50 min-w-[10rem] rounded-lg border border-wa-line bg-white py-1 shadow-lg"
            style={{ left: Math.min(composerMenu.x, window.innerWidth - 180), top: Math.min(composerMenu.y, window.innerHeight - 120) }}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              role="menuitem"
              className="flex w-full px-3 py-2 text-left text-sm hover:bg-wa-app"
              onClick={() => void pasteFromClipboardMenu()}
            >
              Paste
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full px-3 py-2 text-left text-sm hover:bg-wa-app"
              onClick={() => {
                setComposerMenu(null);
                setAttachOpen(true);
              }}
            >
              Attach…
            </button>
          </div>
        </div>
      ) : null}
      <input
        ref={fileRef}
        type="file"
        multiple
        className="hidden"
        accept={ACCEPT}
        onChange={(event) => addFiles(event.target.files)}
      />
      <input
        ref={cameraRef}
        type="file"
        accept={ACCEPT_CAMERA}
        capture="environment"
        className="hidden"
        onChange={(event) => addFiles(event.target.files)}
      />
      <input
        ref={photosRef}
        type="file"
        multiple
        accept={ACCEPT_PHOTOS}
        className="hidden"
        onChange={(event) => addFiles(event.target.files)}
      />
      {attachOpen ? (
        <div className="fixed inset-0 z-40 bg-black/30" role="presentation" onClick={() => setAttachOpen(false)}>
          <div
            role="dialog"
            aria-label="Attach"
            className="absolute bottom-0 left-0 right-0 rounded-t-2xl bg-white p-4 shadow-lg md:bottom-20 md:left-4 md:right-auto md:w-80 md:rounded-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <p className="font-display text-sm font-bold tracking-tight">Attach</p>
              <button type="button" className="text-sm text-wa-muted" onClick={() => setAttachOpen(false)}>
                Close
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  ["camera", "Camera", Camera],
                  ["photos", "Photos", ImageIcon],
                  ["documents", "Documents", FileText],
                  ["location", "Location", MapPin],
                  ["contact", "Contact", ContactRound],
                  ["emoji", "Emoji", Smile],
                ] as const
              ).map(([id, label, Icon]) => (
                <button
                  key={id}
                  type="button"
                  disabled={sending || (!live && id !== "emoji")}
                  className="flex flex-col items-center gap-1.5 rounded-xl bg-wa-app px-2 py-3 text-xs font-medium text-wa-ink hover:bg-wa-leaf disabled:opacity-40"
                  onClick={() => {
                    if (id === "camera") {
                      setAttachOpen(false);
                      cameraRef.current?.click();
                    } else if (id === "photos") {
                      setAttachOpen(false);
                      photosRef.current?.click();
                    } else if (id === "documents") {
                      setAttachOpen(false);
                      fileRef.current?.click();
                    } else if (id === "location") {
                      void sendLocationShare();
                    } else if (id === "contact") {
                      void pickDeviceContact();
                    } else {
                      setAttachOpen(false);
                      setEmojiOpen(true);
                    }
                  }}
                >
                  <Icon className="h-5 w-5 text-wa-green-dark" />
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}
      {emojiOpen ? (
        <div className="absolute bottom-full left-2 right-2 z-30 mb-2 max-h-56 overflow-y-auto rounded-xl border border-wa-line bg-white p-2 shadow-lg md:left-auto md:right-auto md:w-80">
          <div className="mb-1 flex items-center justify-between px-1">
            <p className="text-[11px] font-medium text-wa-muted">Emoji</p>
            <button type="button" className="text-[11px] text-wa-muted" onClick={() => setEmojiOpen(false)}>
              Close
            </button>
          </div>
          <div className="grid grid-cols-8 gap-1">
            {EMOJIS.map((emoji) => (
              <button
                key={emoji}
                type="button"
                className="grid h-8 place-items-center rounded-md text-lg hover:bg-wa-app"
                onClick={() => insertEmoji(emoji)}
              >
                {emoji}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {contactFormOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation" onClick={() => setContactFormOpen(false)}>
          <form
            className="w-full max-w-sm rounded-xl bg-white p-4 shadow-lg"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => {
              event.preventDefault();
              void sendContactShare(contactDraft.name.trim(), contactDraft.phone.trim());
            }}
          >
            <h3 className="font-display text-base font-bold tracking-tight">Send contact</h3>
            <label className="mt-3 block text-sm font-medium" htmlFor="share-contact-name">
              Name
            </label>
            <input
              id="share-contact-name"
              required
              value={contactDraft.name}
              onChange={(event) => setContactDraft((current) => ({ ...current, name: event.target.value }))}
              className="mt-1 h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus:ring-2 focus:ring-wa-green"
            />
            <label className="mt-3 block text-sm font-medium" htmlFor="share-contact-phone">
              Mobile
            </label>
            <input
              id="share-contact-phone"
              required
              inputMode="tel"
              value={contactDraft.phone}
              onChange={(event) => setContactDraft((current) => ({ ...current, phone: event.target.value }))}
              className="mt-1 h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus:ring-2 focus:ring-wa-green"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="h-9 rounded-lg border border-wa-line px-3 text-sm" onClick={() => setContactFormOpen(false)}>
                Cancel
              </button>
              <button type="submit" disabled={sending} className="h-9 rounded-lg bg-wa-green px-3 text-sm font-medium text-white disabled:opacity-40">
                Send
              </button>
            </div>
          </form>
        </div>
      ) : null}
      {templatesOpen ? (
        <div className="absolute bottom-full left-2 right-2 z-20 mb-2 max-h-56 overflow-y-auto rounded-lg border border-black/10 bg-white p-2 shadow-lg md:left-auto md:right-auto md:w-80">
          <p className="px-2 pb-1 text-[11px] font-medium text-wa-muted">Approved templates</p>
          {templatesLoading ? (
            <p className="px-2 py-3 text-sm text-wa-muted">Loading templates…</p>
          ) : templates && templates.length > 0 ? (
            <ul className="flex flex-col gap-1">
              {templates.map((template) => (
                <li key={template.id}>
                  <button
                    type="button"
                    disabled={sending}
                    onClick={() => void sendTemplate(template)}
                    className="flex w-full flex-col rounded-md px-2 py-1.5 text-left hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:opacity-50"
                  >
                    <span className="truncate text-sm font-medium">{template.name}</span>
                    <span className="truncate text-[11px] text-wa-muted">
                      {template.language}
                      {template.category ? ` · ${template.category}` : ""}
                    </span>
                    {template.bodyText ? (
                      <span className="mt-0.5 line-clamp-2 text-[11px] text-wa-ink/70">{template.bodyText}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-2 py-3 text-sm text-wa-muted">No approved templates on this WhatsApp Business account.</p>
          )}
        </div>
      ) : null}

      {replyTo ? (
        <div className="mb-2 flex items-start gap-2 rounded-lg border border-wa-line bg-white px-2 py-1.5">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium text-wa-green-dark">Replying</p>
            <p className="truncate text-sm text-wa-muted">{copyTextForMessage(replyTo)}</p>
          </div>
          <button
            type="button"
            aria-label="Cancel reply"
            onClick={onClearReply}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-black/5"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : null}

      {drafts.length > 0 ? (
        <ul className="mb-2 flex max-h-28 flex-wrap gap-2 overflow-y-auto rounded-lg border border-black/10 bg-white p-2" aria-label="Attachment draft">
          {drafts.map((draft) => (
            <li key={draft.id} className="relative flex w-[7.5rem] flex-col overflow-hidden rounded-md border border-wa-line bg-wa-app">
              {draft.previewUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={draft.previewUrl} alt="" className="h-16 w-full object-cover" />
              ) : (
                <div className="flex h-16 items-center justify-center bg-white">
                  <FileText className="h-6 w-6 text-wa-icon" aria-hidden="true" />
                </div>
              )}
              <p className="truncate px-1.5 py-1 text-[11px]" title={draft.name}>
                {draft.name}
              </p>
              <button
                type="button"
                aria-label={`Remove ${draft.name}`}
                disabled={sending}
                onClick={() => removeDraft(draft.id)}
                className="absolute right-1 top-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-black/70 text-white hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mb-1 flex flex-wrap items-center gap-1 px-1" role="toolbar" aria-label="Message formatting">
        {(
          [
            ["bold", "Bold"],
            ["italic", "Italic"],
            ["strike", "Strike"],
            ["mono", "Mono"],
          ] as const
        ).map(([style, label]) => (
          <button
            key={style}
            type="button"
            disabled={sending}
            onClick={() => applyStyle(style)}
            className="h-7 rounded-md border border-wa-line bg-white px-2 text-[11px] font-medium hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:opacity-40"
          >
            {label}
          </button>
        ))}
        <label className="sr-only" htmlFor={`${formatId}-font`}>
          {COMPOSER_APPEARANCE.fontFamily.label}
        </label>
        <select
          id={`${formatId}-font`}
          value={fontFamily}
          disabled={sending}
          aria-describedby={`${formatId}-appearance-help`}
          title={COMPOSER_APPEARANCE.fontFamily.reason}
          onChange={(event) => setFontFamily(event.target.value as ComposerFontFamily)}
          className="h-7 max-w-[8rem] rounded-md border border-wa-line bg-white px-1 text-[11px]"
        >
          {COMPOSER_APPEARANCE.fontFamily.options.map((option) => (
            <option key={option.value} value={option.value}>
              Font: {option.label}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor={`${formatId}-size`}>
          {COMPOSER_APPEARANCE.fontSize.label}
        </label>
        <select
          id={`${formatId}-size`}
          value={fontSize}
          disabled={sending}
          aria-describedby={`${formatId}-appearance-help`}
          title={COMPOSER_APPEARANCE.fontSize.reason}
          onChange={(event) => setFontSize(event.target.value as ComposerFontSize)}
          className="h-7 max-w-[7.5rem] rounded-md border border-wa-line bg-white px-1 text-[11px]"
        >
          {COMPOSER_APPEARANCE.fontSize.options.map((option) => (
            <option key={option.value} value={option.value}>
              Size: {option.label}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor={`${formatId}-color`}>
          {COMPOSER_APPEARANCE.textColor.label}
        </label>
        <select
          id={`${formatId}-color`}
          value={textColor}
          disabled={sending}
          aria-describedby={`${formatId}-appearance-help`}
          title={COMPOSER_APPEARANCE.textColor.reason}
          onChange={(event) => setTextColor(event.target.value as ComposerTextColor)}
          className="h-7 max-w-[7.5rem] rounded-md border border-wa-line bg-white px-1 text-[11px]"
        >
          {COMPOSER_APPEARANCE.textColor.options.map((option) => (
            <option key={option.value} value={option.value}>
              Color: {option.label}
            </option>
          ))}
        </select>
      </div>
      <p id={`${formatId}-appearance-help`} className="mb-1 px-1 text-[11px] text-wa-muted">
        Bold/Italic/Strike/Mono are sent to WhatsApp. Font/size/color are only for your typing box (Cloud API cannot deliver them).
      </p>
      {body.trim() ? (
        <p className="mb-1 max-h-16 overflow-y-auto px-1 text-[12px] leading-5 text-wa-ink" aria-live="polite">
          <span className="text-[11px] text-wa-muted">Send preview: </span>
          <FormattedBody text={body} />
        </p>
      ) : null}

      <div className="flex items-end gap-1">
        <IconButton
          label={
            blocked
              ? "Contact is blocked"
              : live
                ? "Attach"
                : "Attachments need a connected WhatsApp Business account"
          }
          disabled={blocked || !live || sending}
          side="top"
          aria-expanded={attachOpen}
          onClick={() => {
            setTemplatesOpen(false);
            setEmojiOpen(false);
            setAttachOpen(true);
          }}
        >
          <Paperclip className="h-5 w-5" />
        </IconButton>
        <IconButton
          label={
            blocked
              ? "Contact is blocked"
              : live
                ? "Send template"
                : "Template messages need a connected WhatsApp Business account"
          }
          disabled={blocked || !live || sending}
          side="top"
          aria-expanded={templatesOpen}
          onClick={() => void openTemplates()}
        >
          <FileText className="h-5 w-5" />
        </IconButton>
        <label htmlFor="composer" className="sr-only">
          Message
        </label>
        <textarea
          id="composer"
          ref={fieldRef}
          rows={1}
          value={body}
          maxLength={MESSAGE_LIMIT}
          disabled={blocked}
          placeholder={
            blocked
              ? "Contact is blocked"
              : drafts.length > 0
                ? "Add a caption (optional)"
                : "Type a message"
          }
          onChange={(event) => {
            setBody(event.target.value);
            resize(event.target);
          }}
          onPaste={handlePaste}
          onKeyDown={(event) => {
            if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
            // Desktop: Enter sends, Shift+Enter = new line. Mobile: Enter always = new line.
            if (enterSends && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          style={{
            fontFamily: composerAppearanceCss("fontFamily", fontFamily),
            fontSize: composerAppearanceCss("fontSize", fontSize),
            color: composerAppearanceCss("textColor", textColor),
          }}
          className="max-h-32 min-h-10 min-w-0 flex-1 resize-none rounded-lg bg-white px-3 py-2 leading-5 outline-none focus:ring-2 focus:ring-wa-green disabled:bg-wa-app disabled:text-wa-muted"
        />
        <button
          type="button"
          aria-label="Send message"
          disabled={!canSend}
          onClick={() => void send()}
          className="mb-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-wa-green text-white hover:bg-wa-green-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green focus-visible:ring-offset-2 disabled:bg-wa-line disabled:text-wa-muted"
        >
          {sending ? <LoaderCircle className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
        </button>
      </div>
      <p className="px-2 pt-1 text-center text-[11px] text-wa-muted" aria-live="polite">
        {error ||
          (blocked
            ? "Contact blocked. Open contact details to unblock."
            : drafts.length > 0
              ? `${drafts.length} file${drafts.length === 1 ? "" : "s"} ready. Send to upload.`
              : live
                ? enterSends
                  ? "Enter to send · Shift+Enter for a new line. Bold/Italic/Strike/Mono are WhatsApp markers."
                  : "Tap Send to send · Enter for a new line. Bold/Italic/Strike/Mono are WhatsApp markers."
                : "Demo only. This does not send a WhatsApp message.")}
        {body.length > 3000 ? ` ${body.length}/${MESSAGE_LIMIT}` : ""}
      </p>
    </form>
  );
}
