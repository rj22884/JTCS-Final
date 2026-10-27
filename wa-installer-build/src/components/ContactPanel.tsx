"use client";

import { useAppDialog } from "@/components/AppDialog";
import { useAuth } from "@/components/AuthProvider";
import { Avatar } from "@/components/Avatar";
import { IconButton } from "@/components/IconButton";
import { cn } from "@/lib/cn";
import { CUSTOMER_MASTER_LOGIN_URL } from "@/lib/customer-master";
import { formatActivityTime } from "@/lib/format";
import { toggleLabel } from "@/lib/labels";
import {
  CONVERSATION_STATUSES,
  LABELS,
  type ConversationDetail,
  type ConversationStatus,
  type ConversationSummary,
  type Label,
} from "@/lib/types";
import { coerceContactNameMobile, CONTACT_COUNTRY_CODES, DEFAULT_COUNTRY_CODE } from "@/lib/phone";
import { ArrowLeft, Ban, Camera, Check, Copy, PanelRightClose, Pencil, Phone, Trash2, UserPlus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

type SaveState = "idle" | "saving" | "saved" | "error";

type SavedContact = {
  id: string;
  name: string;
  mobile: string;
  countryCode: string;
  notes: string;
  labels: Label[];
};

export function ContactPanel({
  conversation,
  onBack,
  onClose,
  onUpdated,
}: {
  conversation: ConversationDetail;
  onBack: () => void;
  onClose: () => void;
  onUpdated: (summary: ConversationSummary, detail: ConversationDetail) => void;
}) {
  return (
    <ContactEditor
      key={conversation.id}
      conversation={conversation}
      onBack={onBack}
      onClose={onClose}
      onUpdated={onUpdated}
    />
  );
}

function ContactEditor({
  conversation,
  onBack,
  onClose,
  onUpdated,
}: {
  conversation: ConversationDetail;
  onBack: () => void;
  onClose: () => void;
  onUpdated: (summary: ConversationSummary, detail: ConversationDetail) => void;
}) {
  const { authedFetch } = useAuth();
  const { confirm } = useAppDialog();
  const [notes, setNotes] = useState(conversation.notes);
  const [labels, setLabels] = useState<Label[]>(conversation.labels);
  const [status, setStatus] = useState<ConversationStatus>(conversation.status);
  const [avatarUrl, setAvatarUrl] = useState(conversation.avatarUrl ?? null);
  const [noteState, setNoteState] = useState<SaveState>("idle");
  const [formError, setFormError] = useState("");
  const [labelError, setLabelError] = useState("");
  const [copied, setCopied] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [savedContact, setSavedContact] = useState<SavedContact | null>(null);
  const [contactLookupDone, setContactLookupDone] = useState(false);
  const [saveContactBusy, setSaveContactBusy] = useState(false);
  const [saveContactMessage, setSaveContactMessage] = useState("");
  const [blockBusy, setBlockBusy] = useState(false);
  const [blocked, setBlocked] = useState(Boolean(conversation.blocked));
  const [contactEditorOpen, setContactEditorOpen] = useState(false);
  const [contactDraft, setContactDraft] = useState({
    name: conversation.name,
    countryCode: DEFAULT_COUNTRY_CODE,
    mobile: "",
    notes: conversation.notes,
    labels: conversation.labels as Label[],
  });
  const notesRef = useRef(conversation.notes);
  const pendingNotes = useRef<string | null>(null);
  const timer = useRef<number | null>(null);
  const photoRef = useRef<HTMLInputElement>(null);
  const conversationId = conversation.id;
  const contactSaved = savedContact !== null;

  const refreshContactSaved = useCallback(async () => {
    if (conversation.sample) {
      setSavedContact(null);
      setContactLookupDone(true);
      return;
    }
    try {
      const response = await fetch(
        `/api/contacts?phone=${encodeURIComponent(conversation.phone)}`,
        { cache: "no-store" },
      );
      if (!response.ok) {
        setSavedContact(null);
        setContactLookupDone(true);
        return;
      }
      const data = (await response.json()) as { saved?: boolean; contact?: SavedContact | null };
      setSavedContact(data.saved && data.contact ? data.contact : null);
      if (data.contact?.labels?.length) setLabels(data.contact.labels);
    } catch {
      setSavedContact(null);
    } finally {
      setContactLookupDone(true);
    }
  }, [conversation.phone, conversation.sample]);

  function openContactEditor() {
    const digits = conversation.phone.replace(/\D/g, "");
    const national = digits.length > 10 ? digits.slice(-10) : digits;
    const cc =
      digits.length > 10 ? digits.slice(0, digits.length - national.length) || DEFAULT_COUNTRY_CODE : DEFAULT_COUNTRY_CODE;
    setContactDraft({
      name: savedContact?.name || conversation.name,
      countryCode: savedContact?.countryCode || cc || DEFAULT_COUNTRY_CODE,
      mobile: savedContact?.mobile || national,
      notes: savedContact?.notes || notes,
      labels: savedContact?.labels?.length ? savedContact.labels : labels,
    });
    setContactEditorOpen(true);
    setSaveContactMessage("");
  }

  useEffect(() => {
    setAvatarUrl(conversation.avatarUrl ?? null);
    setLabels(conversation.labels);
    setBlocked(Boolean(conversation.blocked));
  }, [conversation.avatarUrl, conversation.blocked, conversation.id, conversation.labels]);

  useEffect(() => {
    void refreshContactSaved();
  }, [refreshContactSaved]);

  useEffect(() => {
    notesRef.current = notes;
  }, [notes]);

  useEffect(() => {
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
      if (pendingNotes.current !== null) {
        void patch({ notes: pendingNotes.current });
      }
    };
    // Flush the note draft for this contact when the panel closes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  async function patch(body: {
    notes?: string;
    labels?: Label[];
    status?: ConversationStatus;
    blocked?: boolean;
  }): Promise<boolean> {
    setFormError("");
    if (body.notes !== undefined) setNoteState("saving");
    try {
      const response = await authedFetch(`/api/conversations/${conversationId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error("save_failed");
      const data = (await response.json()) as { conversation: ConversationDetail; summary: ConversationSummary };
      if (body.notes !== undefined && pendingNotes.current === body.notes) pendingNotes.current = null;
      if (body.notes !== undefined) setNoteState("saved");
      if (body.blocked !== undefined) setBlocked(Boolean(data.conversation.blocked));
      onUpdated(data.summary, data.conversation);
      return true;
    } catch {
      if (body.notes !== undefined) setNoteState("error");
      setFormError("Could not save this change.");
      return false;
    }
  }

  function scheduleNotes(value: string) {
    pendingNotes.current = value;
    setNoteState("saving");
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const next = pendingNotes.current;
      if (next !== null) void patch({ notes: next });
    }, 400);
  }

  async function copyPhone() {
    try {
      await navigator.clipboard.writeText(conversation.phone.replace(/\s/g, ""));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setFormError("Could not copy the phone number.");
    }
  }

  async function uploadPhoto(file: File | null) {
    if (!file) return;
    setPhotoBusy(true);
    setFormError("");
    try {
      const form = new FormData();
      form.set("photo", file);
      const response = await authedFetch(`/api/conversations/${conversationId}/avatar`, {
        method: "POST",
        body: form,
      });
      const data = (await response.json().catch(() => ({}))) as {
        conversation?: ConversationDetail;
        detail?: string;
      };
      if (!response.ok || !data.conversation) throw new Error(data.detail || "upload_failed");
      setAvatarUrl(data.conversation.avatarUrl ?? null);
      onUpdated(
        {
          id: data.conversation.id,
          name: data.conversation.name,
          phone: data.conversation.phone,
          status: data.conversation.status,
          labels: data.conversation.labels,
          assignee: data.conversation.assignee,
          unreadCount: data.conversation.unreadCount,
          lastMessage: data.conversation.lastMessage,
          lastMessageAt: data.conversation.lastMessageAt,
          lastDirection: data.conversation.lastDirection,
          avatarUrl: data.conversation.avatarUrl,
          sample: data.conversation.sample,
        },
        data.conversation,
      );
    } catch {
      setFormError("Could not save contact photo.");
    } finally {
      setPhotoBusy(false);
      if (photoRef.current) photoRef.current.value = "";
    }
  }

  async function removePhoto() {
    if (!avatarUrl) return;
    if (!(await confirm("Remove this contact photo?", { title: "Remove photo", confirmLabel: "Remove", danger: true }))) {
      return;
    }
    setPhotoBusy(true);
    setFormError("");
    try {
      const response = await authedFetch(`/api/conversations/${conversationId}/avatar`, { method: "DELETE" });
      const data = (await response.json().catch(() => ({}))) as { conversation?: ConversationDetail; detail?: string };
      if (!response.ok || !data.conversation) throw new Error(data.detail || "remove_failed");
      setAvatarUrl(null);
      onUpdated(
        {
          id: data.conversation.id,
          name: data.conversation.name,
          phone: data.conversation.phone,
          status: data.conversation.status,
          labels: data.conversation.labels,
          assignee: data.conversation.assignee,
          unreadCount: data.conversation.unreadCount,
          lastMessage: data.conversation.lastMessage,
          lastMessageAt: data.conversation.lastMessageAt,
          lastDirection: data.conversation.lastDirection,
          avatarUrl: null,
          sample: data.conversation.sample,
        },
        data.conversation,
      );
    } catch {
      setFormError("Could not remove contact photo.");
    } finally {
      setPhotoBusy(false);
    }
  }

  async function saveContactEditor() {
    setSaveContactBusy(true);
    setSaveContactMessage("");
    try {
      const coerced = coerceContactNameMobile(contactDraft.name, contactDraft.mobile);
      const payload = {
        name: coerced.name,
        countryCode: contactDraft.countryCode || DEFAULT_COUNTRY_CODE,
        mobile: coerced.mobile,
        notes: contactDraft.notes.trim(),
        labels: contactDraft.labels,
      };
      const creating = !savedContact;
      const response = await authedFetch(creating ? "/api/contacts" : `/api/contacts/${savedContact.id}`, {
        method: creating ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await response.json().catch(() => ({}))) as {
        detail?: string;
        error?: string;
        contact?: SavedContact;
      };
      if (!response.ok) {
        setSaveContactMessage(data.detail || data.error || "Could not save contact.");
        return;
      }
      const next = data.contact ?? null;
      if (next) {
        setSavedContact(next);
        setLabels(next.labels ?? []);
        void patch({ labels: next.labels ?? [], notes: next.notes || notes });
        setNotes(next.notes || notes);
      }
      setContactEditorOpen(false);
      setSaveContactMessage(creating ? "Contact saved." : "Contact updated.");
    } catch {
      setSaveContactMessage("Could not save contact.");
    } finally {
      setSaveContactBusy(false);
    }
  }

  return (
    <aside className="flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden bg-white" aria-label="Contact details">
      <header className="flex h-14 shrink-0 items-center gap-1 border-b border-wa-line px-1">
        <IconButton label="Back to conversation" onClick={onBack} className="xl:hidden">
          <ArrowLeft className="h-5 w-5" />
        </IconButton>
        <h2 className="font-display min-w-0 flex-1 truncate px-2 text-[15px] font-bold tracking-tight">Contact details</h2>
        <span className="hidden xl:inline-flex">
          <IconButton label="Close contact details" onClick={onClose}>
            <PanelRightClose className="h-5 w-5" />
          </IconButton>
        </span>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain overscroll-x-none px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="relative shrink-0">
            <Avatar name={conversation.name} size={56} src={avatarUrl} />
            <button
              type="button"
              disabled={photoBusy}
              onClick={() => photoRef.current?.click()}
              className="absolute -bottom-1 -right-1 grid h-7 w-7 place-items-center rounded-full border border-wa-line bg-white text-wa-ink shadow-sm hover:bg-wa-app disabled:opacity-40"
              aria-label="Change contact photo"
            >
              <Camera className="h-3.5 w-3.5" />
            </button>
            <input
              ref={photoRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(event) => void uploadPhoto(event.target.files?.[0] ?? null)}
            />
          </div>
          <div className="min-w-0">
            <p className="truncate text-base font-semibold">{conversation.name}</p>
            <p className="text-xs text-wa-muted">
              {conversation.sample ? "Sample conversation. This is not live customer data." : "WhatsApp contact"}
            </p>
            <div className="mt-1 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={photoBusy}
                onClick={() => photoRef.current?.click()}
                className="text-[11px] font-medium text-wa-green-dark hover:underline disabled:opacity-40"
              >
                {photoBusy ? "Saving…" : "Upload photo"}
              </button>
              {avatarUrl ? (
                <button
                  type="button"
                  disabled={photoBusy}
                  onClick={() => void removePhoto()}
                  className="text-[11px] font-medium text-red-700 hover:underline disabled:opacity-40"
                >
                  Remove
                </button>
              ) : null}
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 rounded-lg bg-wa-app px-3 py-2">
          <Phone aria-hidden="true" className="h-4 w-4 shrink-0 text-wa-icon" />
          <a href={`tel:${conversation.phone.replace(/\s/g, "")}`} className="min-w-0 flex-1 truncate text-sm hover:underline">
            {conversation.phone}
          </a>
          <IconButton label={copied ? "Phone number copied" : "Copy phone number"} onClick={() => void copyPhone()}>
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </IconButton>
        </div>

        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <a
            href={CUSTOMER_MASTER_LOGIN_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-9 items-center justify-center rounded-lg border border-wa-line bg-white px-3 text-sm font-medium hover:bg-wa-app"
          >
            ERP Login
          </a>
          <Link
            href="/contacts"
            className="inline-flex h-9 items-center justify-center rounded-lg border border-wa-line bg-white px-3 text-sm font-medium hover:bg-wa-app"
          >
            Contacts
          </Link>
          {!conversation.sample && contactLookupDone && !contactSaved ? (
            <button
              type="button"
              disabled={saveContactBusy}
              onClick={() => {
                void (async () => {
                  setSaveContactBusy(true);
                  setSaveContactMessage("");
                  try {
                    const response = await authedFetch("/api/contacts", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        name: conversation.name,
                        mobile: conversation.phone,
                        notes: notes.trim(),
                        labels,
                      }),
                    });
                    const data = (await response.json().catch(() => ({}))) as {
                      detail?: string;
                      error?: string;
                      contact?: SavedContact;
                    };
                    if (!response.ok) {
                      if (response.status === 409) {
                        await refreshContactSaved();
                        setSaveContactMessage("Already saved in Contacts.");
                        return;
                      }
                      setSaveContactMessage(data.detail || data.error || "Could not save contact.");
                      return;
                    }
                    if (data.contact) setSavedContact(data.contact);
                    setSaveContactMessage("Contact saved.");
                  } catch {
                    setSaveContactMessage("Could not save contact.");
                  } finally {
                    setSaveContactBusy(false);
                  }
                })();
              }}
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-wa-green px-3 text-sm font-medium text-white hover:bg-wa-green-dark disabled:opacity-50"
            >
              <UserPlus className="h-4 w-4" />
              {saveContactBusy ? "Saving…" : "Save contact"}
            </button>
          ) : null}
          {!conversation.sample && contactLookupDone ? (
            <button
              type="button"
              onClick={() => openContactEditor()}
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-wa-line bg-white px-3 text-sm font-medium hover:bg-wa-app"
            >
              <Pencil className="h-4 w-4" />
              Edit contact
            </button>
          ) : null}
          {!conversation.sample && contactLookupDone ? (
            <button
              type="button"
              disabled={saveContactBusy || !contactSaved}
              title={!contactSaved ? "Save the contact first, then you can delete it." : "Delete from Contacts"}
              onClick={() => {
                if (!savedContact) {
                  setSaveContactMessage("Save the contact first, then Delete works.");
                  return;
                }
                void (async () => {
                  const ok = await confirm(
                    `Delete contact “${savedContact.name}” from Contacts? Chat history stays.`,
                    { title: "Delete contact", confirmLabel: "Delete", danger: true },
                  );
                  if (!ok) return;
                  setSaveContactBusy(true);
                  setSaveContactMessage("");
                  try {
                    const response = await authedFetch(`/api/contacts/${savedContact.id}`, { method: "DELETE" });
                    if (!response.ok) {
                      const data = (await response.json().catch(() => ({}))) as { detail?: string };
                      setSaveContactMessage(data.detail || "Could not delete contact.");
                      return;
                    }
                    setSavedContact(null);
                    setSaveContactMessage("Contact deleted from Contacts.");
                  } catch {
                    setSaveContactMessage("Could not delete contact.");
                  } finally {
                    setSaveContactBusy(false);
                  }
                })();
              }}
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              Delete contact
            </button>
          ) : null}
          {!conversation.sample ? (
            <button
              type="button"
              disabled={blockBusy}
              onClick={() => {
                void (async () => {
                  const next = !blocked;
                  if (next) {
                    const ok = await confirm(
                      `Block ${conversation.name}? You won’t be able to send messages until you unblock.`,
                      { title: "Block contact", confirmLabel: "Block", danger: true },
                    );
                    if (!ok) return;
                  }
                  setBlockBusy(true);
                  setSaveContactMessage("");
                  const ok = await patch({ blocked: next });
                  setBlockBusy(false);
                  if (ok) {
                    setSaveContactMessage(next ? "Contact blocked." : "Contact unblocked.");
                  } else {
                    setSaveContactMessage(next ? "Could not block contact." : "Could not unblock contact.");
                  }
                })();
              }}
              className={cn(
                "inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border px-3 text-sm font-medium disabled:opacity-50",
                blocked
                  ? "border-wa-line bg-white text-wa-ink hover:bg-wa-app"
                  : "border-red-200 text-red-700 hover:bg-red-50",
              )}
            >
              <Ban className="h-4 w-4" />
              {blockBusy ? (blocked ? "Unblocking…" : "Blocking…") : blocked ? "Unblock contact" : "Block contact"}
            </button>
          ) : null}
          {!conversation.sample && contactSaved ? (
            <span className="inline-flex h-9 items-center rounded-lg bg-wa-leaf px-3 text-xs font-medium text-wa-green-dark">
              Saved in Contacts
            </span>
          ) : null}
          {!conversation.sample && blocked ? (
            <span className="inline-flex h-9 items-center rounded-lg bg-red-50 px-3 text-xs font-medium text-red-700">
              Blocked
            </span>
          ) : null}
        </div>
        {saveContactMessage ? <p className="mt-1 text-xs text-wa-muted">{saveContactMessage}</p> : null}
        <p className="mt-1 text-xs text-wa-muted">
          Save / Edit / Delete / Block. Blocked: no send, and new inbound messages are ignored.
        </p>

        {conversation.sample ? (
          <p className="mt-4 rounded-lg bg-wa-app px-3 py-2 text-sm text-wa-muted">Demo sample. This chat is not a live WhatsApp customer.</p>
        ) : null}

        <label className="mt-4 block text-xs font-medium uppercase tracking-wide text-wa-muted" htmlFor="conversation-status">
          Status
        </label>
        <select
          id="conversation-status"
          value={status}
          onChange={(event) => {
            const next = event.target.value as ConversationStatus;
            setStatus(next);
            void patch({ status: next });
          }}
          className="mt-1 h-10 w-full rounded-lg border border-wa-line bg-white px-2 text-sm outline-none focus:ring-2 focus:ring-wa-green"
        >
          {CONVERSATION_STATUSES.map((item) => (
            <option key={item} value={item}>
              {item[0].toUpperCase() + item.slice(1)}
            </option>
          ))}
        </select>

        <p className="mt-4 text-xs font-medium uppercase tracking-wide text-wa-muted">Assigned to</p>
        <p className="mt-1 text-sm">{conversation.assignee}</p>

        <div className="mt-4" role="group" aria-label="Contact groups">
          <p className="text-xs font-medium uppercase tracking-wide text-wa-muted">Groups</p>
          <p className="mt-0.5 text-[11px] text-wa-muted">
            Multiple OK for GST/TDS/DSC/ITR. Misc alone only — cannot mix with the others.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {LABELS.map((label) => {
              const selected = labels.includes(label);
              return (
                <button
                  key={label}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => {
                    const result = toggleLabel(labels, label);
                    if (!result.ok) {
                      setLabelError(result.error);
                      return;
                    }
                    setLabels(result.labels);
                    void patch({ labels: result.labels });
                  }}
                  className={cn(
                    "inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green",
                    selected ? "bg-wa-leaf font-medium text-wa-green-dark" : "bg-wa-app text-wa-icon",
                  )}
                >
                  <span
                    className={cn(
                      "grid h-3.5 w-3.5 place-items-center rounded border",
                      selected ? "border-wa-green-dark bg-wa-green text-white" : "border-wa-line bg-white",
                    )}
                    aria-hidden="true"
                  >
                    {selected ? <Check className="h-2.5 w-2.5" /> : null}
                  </span>
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {labelError ? (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
            role="presentation"
            onClick={() => setLabelError("")}
          >
            <div
              role="alertdialog"
              aria-modal="true"
              aria-labelledby="label-error-title"
              className="w-full max-w-sm rounded-xl bg-white p-4 shadow-lg"
              onClick={(event) => event.stopPropagation()}
            >
              <h3 id="label-error-title" className="text-base font-semibold text-wa-ink">
                Grouping nahi ho payi
              </h3>
              <p className="mt-2 whitespace-pre-line text-sm text-wa-muted">{labelError}</p>
              <button
                type="button"
                className="mt-4 h-9 w-full rounded-lg bg-wa-green text-sm font-medium text-white hover:bg-wa-green-dark"
                onClick={() => setLabelError("")}
              >
                OK
              </button>
            </div>
          </div>
        ) : null}

        <label htmlFor="contact-notes" className="mt-4 block text-xs font-medium uppercase tracking-wide text-wa-muted">
          Notes
        </label>
        <textarea
          id="contact-notes"
          value={notes}
          maxLength={4000}
          onChange={(event) => {
            setNotes(event.target.value);
            scheduleNotes(event.target.value);
          }}
          className="mt-1 min-h-24 w-full resize-y rounded-lg border border-wa-line px-3 py-2 text-sm leading-5 outline-none focus:ring-2 focus:ring-wa-green"
        />
        <p className="mt-1 text-xs text-wa-muted" aria-live="polite">
          {noteState === "saving"
            ? "Saving note in demo…"
            : noteState === "saved"
              ? "Note saved in demo."
              : noteState === "error"
                ? "Could not save the note."
                : conversation.sample
                  ? "This sample is not live customer data and is not sent to WhatsApp."
                  : "Notes stay on this server and are not sent to WhatsApp."}
        </p>
        {formError ? <p className="mt-2 text-sm text-red-700">{formError}</p> : null}

        <h3 className="mt-5 text-xs font-medium uppercase tracking-wide text-wa-muted">Activity</h3>
        {conversation.activity.length === 0 ? (
          <p className="mt-2 text-sm text-wa-muted">No activity yet.</p>
        ) : (
          <ol className="mt-3 space-y-3">
            {conversation.activity.map((entry) => (
              <li key={entry.id} className="flex gap-2">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-wa-green" />
                <div className="min-w-0">
                  <p className="text-sm">{entry.label}</p>
                  <time dateTime={entry.at} className="text-xs text-wa-muted">
                    {formatActivityTime(entry.at)}
                  </time>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      {contactEditorOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onClick={() => !saveContactBusy && setContactEditorOpen(false)}
        >
          <form
            className="w-full max-w-md rounded-xl bg-white p-4 shadow-lg"
            aria-label={contactSaved ? "Edit contact" : "Save contact"}
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => {
              event.preventDefault();
              void saveContactEditor();
            }}
          >
            <h3 className="font-display text-base font-bold tracking-tight">
              {contactSaved ? "Edit contact" : "Save contact"}
            </h3>
            <label className="mt-3 block text-sm font-medium" htmlFor="panel-contact-name">
              Name
            </label>
            <input
              id="panel-contact-name"
              required
              value={contactDraft.name}
              onChange={(event) => setContactDraft((current) => ({ ...current, name: event.target.value }))}
              className="mt-1 h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus:ring-2 focus:ring-wa-green"
            />
            <div className="mt-3 grid grid-cols-[minmax(0,1.1fr)_minmax(0,1.4fr)] gap-2">
              <div>
                <label className="block text-sm font-medium" htmlFor="panel-contact-country">
                  Country code
                </label>
                <select
                  id="panel-contact-country"
                  value={contactDraft.countryCode || DEFAULT_COUNTRY_CODE}
                  onChange={(event) => setContactDraft((current) => ({ ...current, countryCode: event.target.value }))}
                  className="mt-1 h-10 w-full rounded-lg border border-wa-line bg-white px-2 text-sm outline-none focus:ring-2 focus:ring-wa-green"
                >
                  {CONTACT_COUNTRY_CODES.map((item) => (
                    <option key={`${item.code}-${item.label}`} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium" htmlFor="panel-contact-mobile">
                  Mobile
                </label>
                <input
                  id="panel-contact-mobile"
                  required
                  inputMode="tel"
                  value={contactDraft.mobile}
                  onChange={(event) => setContactDraft((current) => ({ ...current, mobile: event.target.value }))}
                  className="mt-1 h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus:ring-2 focus:ring-wa-green"
                />
              </div>
            </div>
            <p className="mt-1 text-xs text-wa-muted">
              Full number: +{contactDraft.countryCode || DEFAULT_COUNTRY_CODE}
              {contactDraft.mobile.replace(/\D/g, "") ? ` ${contactDraft.mobile.replace(/\D/g, "")}` : ""}
            </p>
            <div className="mt-3" role="group" aria-label="Contact groups">
              <p className="text-sm font-medium">Groups</p>
              <p className="mt-0.5 text-[11px] text-wa-muted">Multiple OK for GST/TDS/DSC/ITR. Misc alone only.</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {LABELS.map((label) => {
                  const selected = contactDraft.labels.includes(label);
                  return (
                    <button
                      key={label}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => {
                        const result = toggleLabel(contactDraft.labels, label);
                        if (!result.ok) {
                          setLabelError(result.error);
                          return;
                        }
                        setContactDraft((current) => ({ ...current, labels: result.labels }));
                      }}
                      className={cn(
                        "inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm",
                        selected ? "bg-wa-leaf font-medium text-wa-green-dark" : "bg-wa-app text-wa-icon",
                      )}
                    >
                      <span
                        className={cn(
                          "grid h-3.5 w-3.5 place-items-center rounded border",
                          selected ? "border-wa-green-dark bg-wa-green text-white" : "border-wa-line bg-white",
                        )}
                        aria-hidden="true"
                      >
                        {selected ? <Check className="h-2.5 w-2.5" /> : null}
                      </span>
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
            <label className="mt-3 block text-sm font-medium" htmlFor="panel-contact-notes">
              Notes
            </label>
            <textarea
              id="panel-contact-notes"
              value={contactDraft.notes}
              onChange={(event) => setContactDraft((current) => ({ ...current, notes: event.target.value }))}
              className="mt-1 min-h-20 w-full rounded-lg border border-wa-line px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-wa-green"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                disabled={saveContactBusy}
                onClick={() => setContactEditorOpen(false)}
                className="h-9 rounded-lg border border-wa-line px-3 text-sm"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saveContactBusy}
                className="inline-flex h-9 items-center rounded-lg bg-wa-green px-3 text-sm font-medium text-white disabled:opacity-40"
              >
                {saveContactBusy ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </aside>
  );
}
