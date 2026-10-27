"use client";

import { useAppDialog } from "@/components/AppDialog";
import { useAuth } from "@/components/AuthProvider";
import { cn } from "@/lib/cn";
import { sortContacts, type ContactSort } from "@/lib/contact-sort";
import { toggleLabel } from "@/lib/labels";
import { coerceContactNameMobile, CONTACT_COUNTRY_CODES, DEFAULT_COUNTRY_CODE } from "@/lib/phone";
import { LABELS, type Label } from "@/lib/types";
import { Check, LoaderCircle, Megaphone, MessageSquare, Pencil, Plus, RotateCcw, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

type ContactStatusFilter = "all" | "active" | "deleted";

type TemplateOption = { id: string; name: string; language: string; status: string; category: string };

type BulkRow = {
  contactId: string;
  name: string;
  mobile: string;
  conversationId: string | null;
  ok: boolean;
  detail: string;
};

const BULK_MAX = 40;

type Contact = {
  id: string;
  name: string;
  mobile: string;
  countryCode: string;
  fullMobile: string;
  displayMobile: string;
  phoneKey: string;
  source: "erp" | "manual";
  notes: string;
  labels: Label[];
  deletedAt: string | null;
};

type Draft = { name: string; countryCode: string; mobile: string; notes: string; labels: Label[] };

const emptyDraft: Draft = { name: "", countryCode: DEFAULT_COUNTRY_CODE, mobile: "", notes: "", labels: [] };

export function ContactsScreen() {
  const { session, ready: authReady, csrfToken, authedFetch } = useAuth();
  const { confirm } = useAppDialog();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState<ContactSort>("name");
  const [statusFilter, setStatusFilter] = useState<ContactStatusFilter>("all");
  const [phase, setPhase] = useState<"loading" | "error" | "ready">("loading");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [editor, setEditor] = useState<"create" | Contact | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [labelError, setLabelError] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [bulkOpen, setBulkOpen] = useState(false);
  const [templates, setTemplates] = useState<TemplateOption[] | null>(null);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateKey, setTemplateKey] = useState("");
  const [bulkPhase, setBulkPhase] = useState<"pick" | "sending" | "done">("pick");
  const [bulkReport, setBulkReport] = useState<{
    sent: number;
    failed: number;
    skipped: number;
    detail: string;
    results: BulkRow[];
  } | null>(null);

  const canManage = Boolean(session?.authenticated);

  const load = useCallback(async (q = query) => {
    const listResponse = await fetch(`/api/contacts?q=${encodeURIComponent(q)}`, { cache: "no-store" });
    if (!listResponse.ok) throw new Error("load_failed");
    const data = (await listResponse.json()) as { contacts: Contact[] };
    setContacts(data.contacts);
    setPhase("ready");
  }, [query]);

  useEffect(() => {
    if (!authReady) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      load().catch(() => {
        if (!cancelled) setPhase("error");
      });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [authReady, load]);

  function openCreate() {
    setDraft(emptyDraft);
    setEditor("create");
    setMessage(null);
  }

  function openEdit(contact: Contact) {
    if (contact.deletedAt) return;
    setDraft({
      name: contact.name,
      countryCode: contact.countryCode || DEFAULT_COUNTRY_CODE,
      mobile: contact.mobile,
      notes: contact.notes,
      labels: contact.labels ?? [],
    });
    setEditor(contact);
    setMessage(null);
    setLabelError("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!canManage || !session || !editor) return;
    setBusy("save");
    setMessage(null);
    try {
      const creating = editor === "create";
      const coerced = coerceContactNameMobile(draft.name, draft.mobile);
      const payload = {
        ...draft,
        name: coerced.name,
        mobile: coerced.mobile,
      };
      if (coerced.swapped) {
        setDraft((current) => ({ ...current, name: coerced.name, mobile: coerced.mobile }));
      }
      const response = await fetch(creating ? "/api/contacts" : `/api/contacts/${editor.id}`, {
        method: creating ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json", "x-csrf-token": session.csrfToken },
        body: JSON.stringify(payload),
      });
      const data = (await response.json().catch(() => ({}))) as { detail?: string; error?: string };
      if (!response.ok) throw new Error(data.detail || data.error || "save_failed");
      setEditor(null);
      setMessage({
        ok: true,
        text: creating
          ? coerced.swapped
            ? "Contact created. Name and mobile were swapped automatically."
            : "Contact created."
          : "Contact updated.",
      });
      await load();
    } catch (reason) {
      setMessage({ ok: false, text: reason instanceof Error ? reason.message : "Could not save contact." });
    } finally {
      setBusy("");
    }
  }

  async function remove(contact: Contact) {
    if (!canManage || !session || contact.deletedAt) return;
    const erpNote =
      contact.source === "erp"
        ? " This only archives the contact in WhatsApp CRM. The ERP CustomerMaster record is not deleted."
        : " You can restore it later with Undelete.";
    if (
      !(await confirm(`Delete contact “${contact.name}”?${erpNote}`, {
        title: "Delete contact",
        confirmLabel: "Delete",
        danger: true,
      }))
    ) {
      return;
    }
    setBusy(`delete-${contact.id}`);
    setMessage(null);
    try {
      const response = await fetch(`/api/contacts/${contact.id}`, {
        method: "DELETE",
        headers: { "x-csrf-token": session.csrfToken },
      });
      const data = (await response.json().catch(() => ({}))) as { detail?: string; error?: string };
      if (!response.ok) throw new Error(data.detail || data.error || "delete_failed");
      setMessage({ ok: true, text: "Contact deleted in this app. Chats and messages are kept." });
      await load();
    } catch (reason) {
      setMessage({ ok: false, text: reason instanceof Error ? reason.message : "Could not delete contact." });
    } finally {
      setBusy("");
    }
  }

  async function restore(contact: Contact) {
    if (!canManage || !session || !contact.deletedAt) return;
    if (
      !(await confirm(`Restore contact “${contact.name}” to the active list?`, {
        title: "Restore contact",
        confirmLabel: "Restore",
      }))
    ) {
      return;
    }
    setBusy(`undelete-${contact.id}`);
    setMessage(null);
    try {
      const response = await fetch(`/api/contacts/${contact.id}/undelete`, {
        method: "POST",
        headers: { "x-csrf-token": session.csrfToken },
      });
      const data = (await response.json().catch(() => ({}))) as { detail?: string; error?: string };
      if (!response.ok) throw new Error(data.detail || data.error || "undelete_failed");
      setMessage({ ok: true, text: "Contact restored." });
      await load();
    } catch (reason) {
      setMessage({ ok: false, text: reason instanceof Error ? reason.message : "Could not restore contact." });
    } finally {
      setBusy("");
    }
  }

  async function sendMessage(contact: Contact) {
    if (!session?.authenticated || contact.deletedAt) return;
    if (busy.startsWith("message-")) return;
    setBusy(`message-${contact.id}`);
    setMessage(null);
    try {
      const phone = (
        contact.fullMobile || `${contact.countryCode || DEFAULT_COUNTRY_CODE}${contact.mobile}`
      ).replace(/\D/g, "");
      if (phone.length < 8) {
        throw new Error("This contact has no valid mobile number.");
      }
      const response = await authedFetch("/api/conversations/open", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken || session.csrfToken },
        body: JSON.stringify({ phone, name: contact.name }),
        signal: AbortSignal.timeout(15_000),
      });
      const data = (await response.json().catch(() => ({}))) as {
        conversationId?: string;
        detail?: string;
        error?: string;
      };
      if (!response.ok || !data.conversationId) {
        throw new Error(data.detail || data.error || "Could not open chat.");
      }
      // Clear waiting state before leave — soft nav can leave this page mounted briefly.
      setBusy("");
      window.location.assign(`/?c=${encodeURIComponent(data.conversationId)}&focus=composer`);
    } catch (reason) {
      const timedOut =
        reason instanceof DOMException && (reason.name === "TimeoutError" || reason.name === "AbortError");
      setMessage({
        ok: false,
        text: timedOut
          ? "Opening chat timed out. Try again."
          : reason instanceof Error
            ? reason.message
            : "Could not open chat.",
      });
      setBusy("");
    }
  }

  const draftCountry = draft.countryCode || DEFAULT_COUNTRY_CODE;
  const countryOptions: Array<{ code: string; label: string }> = [...CONTACT_COUNTRY_CODES];
  if (!countryOptions.some((item) => item.code === draftCountry)) {
    countryOptions.unshift({ code: draftCountry, label: `+${draftCountry}` });
  }

  const visibleContacts = useMemo(() => {
    const filtered = contacts.filter((contact) => {
      if (statusFilter === "active") return !contact.deletedAt;
      if (statusFilter === "deleted") return Boolean(contact.deletedAt);
      return true;
    });
    return sortContacts(filtered, sortBy);
  }, [contacts, sortBy, statusFilter]);

  const selectableVisible = useMemo(
    () => visibleContacts.filter((contact) => !contact.deletedAt),
    [visibleContacts],
  );
  const selectedCount = selectedIds.size;
  const allVisibleSelected =
    selectableVisible.length > 0 && selectableVisible.every((contact) => selectedIds.has(contact.id));

  function toggleSelect(contactId: string, enabled: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (enabled) next.add(contactId);
      else next.delete(contactId);
      return next;
    });
  }

  function toggleSelectAllVisible() {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) {
        for (const contact of selectableVisible) next.delete(contact.id);
      } else {
        for (const contact of selectableVisible.slice(0, BULK_MAX)) next.add(contact.id);
      }
      return next;
    });
  }

  async function openBulk() {
    if (!canManage || selectedCount === 0) return;
    if (selectedCount > BULK_MAX) {
      setMessage({ ok: false, text: `Select at most ${BULK_MAX} contacts for one bulk send.` });
      return;
    }
    setBulkOpen(true);
    setBulkPhase("pick");
    setBulkReport(null);
    setTemplateKey("");
    setMessage(null);
    if (templates) return;
    setTemplatesLoading(true);
    try {
      const response = await fetch("/api/whatsapp/templates", { cache: "no-store" });
      const data = (await response.json().catch(() => ({}))) as {
        templates?: TemplateOption[];
        detail?: string;
        error?: string;
      };
      if (!response.ok || !data.templates) {
        throw new Error(data.detail || data.error || "Could not load templates.");
      }
      setTemplates(data.templates);
    } catch (reason) {
      setTemplates([]);
      setMessage({
        ok: false,
        text: reason instanceof Error ? reason.message : "Could not load approved templates.",
      });
    } finally {
      setTemplatesLoading(false);
    }
  }

  async function runBulkSend() {
    if (!session || !templateKey) return;
    const [name, language] = templateKey.split("||");
    if (!name || !language) return;
    setBulkPhase("sending");
    setBusy("bulk");
    try {
      const response = await fetch("/api/contacts/bulk-template", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": session.csrfToken },
        body: JSON.stringify({
          contactIds: [...selectedIds],
          name,
          language,
        }),
      });
      const data = (await response.json().catch(() => ({}))) as {
        detail?: string;
        error?: string;
        sent?: number;
        failed?: number;
        skipped?: number;
        results?: BulkRow[];
      };
      if (!response.ok || !data.results) {
        throw new Error(data.detail || data.error || "Bulk send failed.");
      }
      setBulkReport({
        sent: data.sent ?? 0,
        failed: data.failed ?? 0,
        skipped: data.skipped ?? 0,
        detail: data.detail || "",
        results: data.results,
      });
      setBulkPhase("done");
      setMessage({
        ok: (data.failed ?? 0) === 0,
        text: data.detail || `Sent ${data.sent ?? 0}, failed ${data.failed ?? 0}.`,
      });
    } catch (reason) {
      setBulkPhase("pick");
      setMessage({ ok: false, text: reason instanceof Error ? reason.message : "Bulk send failed." });
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="min-h-0 flex-1 overflow-y-auto bg-white">
      <header className="border-b border-wa-line px-4 py-3 md:px-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-display text-xl font-bold tracking-tight">Contacts</h1>
            <p className="text-sm text-wa-muted">
              ERP sync + manual contacts. Full number = country code + mobile (default India +91).
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void openBulk()}
              disabled={!canManage || selectedCount === 0 || Boolean(busy)}
              className="inline-flex h-9 items-center justify-center gap-1 rounded-lg border border-wa-line px-3 text-sm font-medium hover:bg-wa-app disabled:opacity-40"
            >
              <Megaphone className="h-4 w-4" />
              Bulk template{selectedCount ? ` (${selectedCount})` : ""}
            </button>
            <button
              type="button"
              onClick={openCreate}
              disabled={!canManage || Boolean(busy)}
              className="inline-flex h-9 items-center justify-center gap-1 rounded-lg bg-wa-green px-3 text-sm font-medium text-white hover:bg-wa-green-dark disabled:opacity-40"
            >
              <Plus className="h-4 w-4" />
              Add contact
            </button>
          </div>
        </div>
        <label className="relative mt-3 block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-wa-muted" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search name or mobile"
            className="h-10 w-full rounded-lg border border-wa-line bg-wa-app pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
          />
        </label>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Contact status filter">
            {(
              [
                ["all", "All"],
                ["active", "Active"],
                ["deleted", "Deleted"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setStatusFilter(id)}
                className={cn(
                  "h-8 rounded-lg border px-2.5 text-xs font-medium",
                  statusFilter === id
                    ? "border-wa-green bg-wa-green/10 text-wa-green-dark"
                    : "border-wa-line text-wa-muted hover:bg-wa-app",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs text-wa-muted">
            <span className="shrink-0">Sort by</span>
            <select
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value as ContactSort)}
              className="h-8 min-w-[9.5rem] rounded-lg border border-wa-line bg-white px-2 text-sm text-wa-ink outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
            >
              <option value="name">Name</option>
              <option value="mobile">Mobile</option>
              <option value="deleted">Deleted first</option>
            </select>
          </label>
        </div>
      </header>

      {!canManage ? (
        <p className="px-4 py-3 text-sm text-wa-muted md:px-6">Sign in to add, edit, or delete contacts.</p>
      ) : null}
      {message ? (
        <p className={cn("px-4 py-2 text-sm md:px-6", message.ok ? "text-wa-green-dark" : "text-red-700")} aria-live="polite">
          {message.text}
        </p>
      ) : null}

      {phase === "loading" ? <p className="px-4 py-6 text-sm text-wa-muted md:px-6">Loading contacts…</p> : null}
      {phase === "error" ? <p className="px-4 py-6 text-sm text-red-700 md:px-6">Could not load contacts.</p> : null}
      {phase === "ready" && contacts.length === 0 ? (
        <p className="px-4 py-6 text-sm text-wa-muted md:px-6">No contacts yet. Sync from ERP or add a contact.</p>
      ) : null}
      {phase === "ready" && contacts.length > 0 && visibleContacts.length === 0 ? (
        <p className="px-4 py-6 text-sm text-wa-muted md:px-6">No contacts match this filter.</p>
      ) : null}

      {phase === "ready" && selectableVisible.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 border-b border-wa-line px-4 py-2 text-xs text-wa-muted md:px-6">
          <label className="inline-flex items-center gap-2 font-medium text-wa-ink">
            <input
              type="checkbox"
              checked={allVisibleSelected}
              onChange={toggleSelectAllVisible}
              className="h-4 w-4 rounded border-wa-line"
            />
            Select all visible active ({Math.min(selectableVisible.length, BULK_MAX)}
            {selectableVisible.length > BULK_MAX ? ` of ${selectableVisible.length}` : ""})
          </label>
          {selectedCount > 0 ? (
            <button type="button" className="underline hover:text-wa-ink" onClick={() => setSelectedIds(new Set())}>
              Clear selection
            </button>
          ) : null}
          <span>Bulk max {BULK_MAX} · approved WhatsApp templates only</span>
        </div>
      ) : null}

      {phase === "ready" && visibleContacts.length > 0 ? (
        <ul className="divide-y divide-wa-line">
          {visibleContacts.map((contact) => {
            const deleted = Boolean(contact.deletedAt);
            const checked = selectedIds.has(contact.id);
            return (
              <li
                key={contact.id}
                className={cn(
                  "flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between md:px-6",
                  deleted && "bg-wa-app/70",
                  checked && !deleted && "bg-wa-green/5",
                )}
              >
                <div className="flex min-w-0 items-start gap-3">
                  <input
                    type="checkbox"
                    disabled={deleted || (!checked && selectedCount >= BULK_MAX)}
                    checked={checked}
                    onChange={(event) => toggleSelect(contact.id, event.target.checked)}
                    className="mt-1 h-4 w-4 shrink-0 rounded border-wa-line disabled:opacity-40"
                    aria-label={`Select ${contact.name}`}
                  />
                  <div className="min-w-0">
                  <p className="flex min-w-0 flex-wrap items-center gap-1">
                    <span className={cn("truncate text-sm font-medium", deleted && "text-wa-muted")}>{contact.name}</span>
                    {(contact.labels ?? []).map((label) => (
                      <span
                        key={label}
                        className="shrink-0 rounded bg-wa-app px-1 py-px text-[10px] font-medium uppercase leading-4 text-wa-icon"
                      >
                        {label}
                      </span>
                    ))}
                  </p>
                  <p className="truncate text-sm text-wa-muted">
                    {contact.displayMobile || `+${contact.countryCode || DEFAULT_COUNTRY_CODE} ${contact.mobile}`}
                  </p>
                  <p className="flex flex-wrap items-center gap-2 text-[11px] text-wa-muted">
                    <span>{contact.source === "erp" ? "ERP" : "Manual"}</span>
                    {deleted ? (
                      <span className="rounded bg-red-50 px-1.5 py-0.5 font-medium uppercase tracking-wide text-red-700">
                        Deleted
                      </span>
                    ) : null}
                  </p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 pl-7 sm:pl-0">
                  {!deleted ? (
                    <button
                      type="button"
                      disabled={!canManage || busy === `message-${contact.id}`}
                      onClick={() => void sendMessage(contact)}
                      className="inline-flex h-9 items-center gap-1 rounded-lg border border-wa-line px-3 text-sm text-wa-ink hover:bg-wa-app disabled:opacity-40"
                    >
                      {busy === `message-${contact.id}` ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <MessageSquare className="h-4 w-4" />
                      )}
                      Send message
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={!canManage || deleted || busy === "save"}
                    onClick={() => openEdit(contact)}
                    className="inline-flex h-9 items-center gap-1 rounded-lg border border-wa-line px-3 text-sm text-wa-ink hover:bg-wa-app disabled:opacity-40"
                  >
                    <Pencil className="h-4 w-4" />
                    Edit
                  </button>
                  {deleted ? (
                    <button
                      type="button"
                      disabled={!canManage || busy === `undelete-${contact.id}`}
                      onClick={() => void restore(contact)}
                      className="inline-flex h-9 items-center gap-1 rounded-lg border border-wa-line px-3 text-sm text-wa-green-dark hover:bg-wa-app disabled:opacity-40"
                    >
                      {busy === `undelete-${contact.id}` ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <RotateCcw className="h-4 w-4" />
                      )}
                      Undelete
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={!canManage || busy === `delete-${contact.id}`}
                      onClick={() => void remove(contact)}
                      className="inline-flex h-9 items-center gap-1 rounded-lg border border-wa-line px-3 text-sm text-red-700 hover:bg-red-50 disabled:opacity-40"
                    >
                      {busy === `delete-${contact.id}` ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                      Delete
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}

      {bulkOpen ? (
        <div
          className="fixed inset-0 z-40 flex items-end justify-center bg-black/30 p-4 sm:items-center"
          role="presentation"
          onMouseDown={() => {
            if (bulkPhase !== "sending") setBulkOpen(false);
          }}
        >
          <div
            onMouseDown={(event) => event.stopPropagation()}
            className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-xl bg-white shadow-lg"
            role="dialog"
            aria-label="Bulk template send"
          >
            <div className="border-b border-wa-line px-4 py-3">
              <h2 className="font-display text-base font-bold tracking-tight">Bulk template send</h2>
              <p className="mt-0.5 text-xs text-wa-muted">
                {selectedCount} contact{selectedCount === 1 ? "" : "s"} · sender +918477005566 · Meta approved
                templates only
              </p>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              {bulkPhase === "sending" ? (
                <p className="inline-flex items-center gap-2 text-sm text-wa-muted">
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                  Sending templates one by one… keep this window open.
                </p>
              ) : null}
              {bulkPhase === "pick" ? (
                <div className="space-y-3">
                  {templatesLoading ? <p className="text-sm text-wa-muted">Loading templates…</p> : null}
                  {!templatesLoading && templates && templates.length === 0 ? (
                    <p className="text-sm text-red-700">
                      No approved templates found. Create and approve a template in Meta WhatsApp Manager first.
                    </p>
                  ) : null}
                  {!templatesLoading && templates && templates.length > 0 ? (
                    <label className="block text-sm font-medium">
                      Template
                      <select
                        value={templateKey}
                        onChange={(event) => setTemplateKey(event.target.value)}
                        className="mt-1 h-10 w-full rounded-lg border border-wa-line bg-white px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
                      >
                        <option value="">Select approved template…</option>
                        {templates.map((item) => (
                          <option key={`${item.name}||${item.language}`} value={`${item.name}||${item.language}`}>
                            {item.name} · {item.language}
                            {item.category ? ` · ${item.category}` : ""}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  <p className="text-xs text-wa-muted">
                    Free-form text cannot be bulk-sent to cold numbers. Only approved templates are used. Max {BULK_MAX}{" "}
                    per run.
                  </p>
                </div>
              ) : null}
              {bulkPhase === "done" && bulkReport ? (
                <div className="space-y-3">
                  <p className="text-sm font-medium text-wa-ink">{bulkReport.detail}</p>
                  <ul className="max-h-64 divide-y divide-wa-line overflow-y-auto rounded-lg border border-wa-line text-sm">
                    {bulkReport.results.map((row) => (
                      <li key={row.contactId} className="px-3 py-2">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate font-medium">{row.name || row.contactId}</p>
                            <p className="truncate text-xs text-wa-muted">{row.mobile}</p>
                          </div>
                          <span className={cn("shrink-0 text-xs font-medium", row.ok ? "text-wa-green-dark" : "text-red-700")}>
                            {row.ok ? "Sent" : "Failed"}
                          </span>
                        </div>
                        {!row.ok ? <p className="mt-0.5 text-xs text-red-700">{row.detail}</p> : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
            <div className="flex justify-end gap-2 border-t border-wa-line px-4 py-3">
              <button
                type="button"
                disabled={bulkPhase === "sending"}
                onClick={() => setBulkOpen(false)}
                className="h-9 rounded-lg border border-wa-line px-3 text-sm disabled:opacity-40"
              >
                {bulkPhase === "done" ? "Close" : "Cancel"}
              </button>
              {bulkPhase === "pick" ? (
                <button
                  type="button"
                  disabled={!templateKey || templatesLoading || Boolean(busy)}
                  onClick={() => void runBulkSend()}
                  className="inline-flex h-9 items-center rounded-lg bg-wa-green px-3 text-sm font-medium text-white disabled:opacity-40"
                >
                  Send to {selectedCount}
                </button>
              ) : null}
              {bulkPhase === "done" ? (
                <button
                  type="button"
                  onClick={() => {
                    setSelectedIds(new Set());
                    setBulkOpen(false);
                  }}
                  className="h-9 rounded-lg bg-wa-green px-3 text-sm font-medium text-white"
                >
                  Done
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {editor ? (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/30 p-4 sm:items-center" role="presentation" onMouseDown={() => setEditor(null)}>
          <form
            onSubmit={(event) => void save(event)}
            onMouseDown={(event) => event.stopPropagation()}
            className="w-full max-w-md rounded-xl bg-white p-4 shadow-lg"
            aria-label={editor === "create" ? "Add contact" : "Edit contact"}
          >
            <h2 className="font-display text-base font-bold tracking-tight">{editor === "create" ? "Add contact" : "Edit contact"}</h2>
            <label className="mt-3 block text-sm font-medium" htmlFor="contact-name">
              Name
            </label>
            <input
              id="contact-name"
              required
              value={draft.name}
              onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
              placeholder="e.g. Chandra Joshi"
              autoComplete="name"
              className="mt-1 h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
            />
            <div className="mt-3 grid grid-cols-[minmax(0,1.1fr)_minmax(0,1.4fr)] gap-2">
              <div>
                <label className="block text-sm font-medium" htmlFor="contact-country">
                  Country code
                </label>
                <select
                  id="contact-country"
                  required
                  value={draftCountry}
                  onChange={(event) => setDraft((current) => ({ ...current, countryCode: event.target.value }))}
                  className="mt-1 h-10 w-full rounded-lg border border-wa-line bg-white px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
                >
                  {countryOptions.map((item) => (
                    <option key={`${item.code}-${item.label}`} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium" htmlFor="contact-mobile">
                  Mobile
                </label>
                <input
                  id="contact-mobile"
                  required
                  inputMode="tel"
                  value={draft.mobile}
                  onChange={(event) => setDraft((current) => ({ ...current, mobile: event.target.value }))}
                  placeholder="e.g. 7817840614"
                  autoComplete="tel-national"
                  className="mt-1 h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
                />
              </div>
            </div>
            <p className="mt-1 text-xs text-wa-muted">
              Full number: +{draft.countryCode || DEFAULT_COUNTRY_CODE}
              {draft.mobile.replace(/\D/g, "") ? ` ${draft.mobile.replace(/\D/g, "")}` : ""}
              {" · "}Name = person, Mobile = digits only
            </p>
            <div className="mt-3" role="group" aria-label="Contact groups">
              <p className="text-sm font-medium">Groups</p>
              <p className="mt-0.5 text-[11px] text-wa-muted">
                Multiple OK for GST/TDS/DSC/ITR. Misc alone only.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {LABELS.map((label) => {
                  const selected = draft.labels.includes(label);
                  return (
                    <button
                      key={label}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => {
                        const result = toggleLabel(draft.labels, label);
                        if (!result.ok) {
                          setLabelError(result.error);
                          return;
                        }
                        setDraft((current) => ({ ...current, labels: result.labels }));
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
            <label className="mt-3 block text-sm font-medium" htmlFor="contact-notes">
              Notes
            </label>
            <textarea
              id="contact-notes"
              value={draft.notes}
              onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
              className="mt-1 min-h-20 w-full rounded-lg border border-wa-line px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setEditor(null)} className="h-9 rounded-lg border border-wa-line px-3 text-sm">
                Cancel
              </button>
              <button type="submit" disabled={busy === "save"} className="inline-flex h-9 items-center rounded-lg bg-wa-green px-3 text-sm font-medium text-white disabled:opacity-40">
                {busy === "save" ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {labelError ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onClick={() => setLabelError("")}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            className="w-full max-w-sm rounded-xl bg-white p-4 shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 className="text-base font-semibold">Grouping nahi ho payi</h3>
            <p className="mt-2 whitespace-pre-line text-sm text-wa-muted">{labelError}</p>
            <button
              type="button"
              className="mt-4 h-9 w-full rounded-lg bg-wa-green text-sm font-medium text-white"
              onClick={() => setLabelError("")}
            >
              OK
            </button>
          </div>
        </div>
      ) : null}
    </main>
  );
}
