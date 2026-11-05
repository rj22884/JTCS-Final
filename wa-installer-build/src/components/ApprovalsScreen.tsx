"use client";

import { useAppDialog } from "@/components/AppDialog";
import { useAuth } from "@/components/AuthProvider";
import { cn } from "@/lib/cn";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

type UserRole = "admin" | "member";

type PendingUser = {
  id: string;
  name: string;
  email: string;
  mobile: string | null;
  role: UserRole;
  createdAt: string;
  notifyFailure: { detail: string; failedAt: string; attempts: number } | null;
};

type ListedUser = {
  id: string;
  name: string;
  email: string;
  mobile: string | null;
  role?: UserRole;
  deletedAt?: string | null;
};

export function ApprovalsScreen() {
  const { session, csrfToken, ready } = useAuth();
  const { confirm } = useAppDialog();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const admin = Boolean(session?.authenticated && session.role === "admin");
  const [pending, setPending] = useState<PendingUser[]>([]);
  const [deleted, setDeleted] = useState<ListedUser[]>([]);
  const [rejected, setRejected] = useState<ListedUser[]>([]);
  const [approveRoles, setApproveRoles] = useState<Record<string, UserRole>>({});
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    const response = await fetch("/api/auth/approvals", { cache: "no-store" });
    if (!response.ok) throw new Error("load_failed");
    const data = (await response.json()) as {
      pending?: PendingUser[];
      deleted?: ListedUser[];
      rejected?: ListedUser[];
    };
    const nextPending = data.pending ?? [];
    setPending(nextPending);
    setDeleted(data.deleted ?? []);
    setRejected(data.rejected ?? []);
    setApproveRoles((current) => {
      const next: Record<string, UserRole> = {};
      for (const user of nextPending) {
        next[user.id] = current[user.id] ?? (user.role === "admin" ? "admin" : "member");
      }
      return next;
    });
  }, []);

  useEffect(() => {
    if (!ready || !admin) return;
    void load().catch(() => setMessage({ ok: false, text: "Could not load pending approvals." }));
  }, [ready, admin, load]);

  useEffect(() => {
    if (!ready || !admin || !token || !csrfToken) return;
    let cancelled = false;
    setBusy("token");
    void (async () => {
      try {
        const response = await fetch("/api/auth/approvals", {
          method: "POST",
          headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken },
          body: JSON.stringify({ token }),
        });
        const data = (await response.json().catch(() => ({}))) as { detail?: string; error?: string; action?: string };
        if (cancelled) return;
        if (!response.ok) throw new Error(data.detail || data.error || "token_failed");
        setMessage({
          ok: true,
          text: data.action === "reject" ? "Registration rejected." : "Registration approved.",
        });
        await load();
      } catch (reason) {
        if (!cancelled) {
          setMessage({ ok: false, text: reason instanceof Error ? reason.message : "Approval link failed." });
        }
      } finally {
        if (!cancelled) setBusy("");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, admin, token, csrfToken, load]);

  async function act(action: "approve" | "reject" | "retry_notify" | "purge", userId: string) {
    if (!admin || !csrfToken) return;
    if (
      action === "purge" &&
      !(await confirm("Permanently delete this account row? Customer/chat data will not be deleted.", {
        title: "Permanent delete",
        confirmLabel: "Delete",
        danger: true,
      }))
    ) {
      return;
    }
    setBusy(`${action}-${userId}`);
    setMessage(null);
    try {
      const url = action === "purge" ? `/api/admin/users/${encodeURIComponent(userId)}/purge` : "/api/auth/approvals";
      const body =
        action === "purge"
          ? "{}"
          : JSON.stringify({
              action,
              userId,
              ...(action === "approve" ? { role: approveRoles[userId] ?? "member" } : {}),
            });
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken },
        body,
      });
      const data = (await response.json().catch(() => ({}))) as { detail?: string; error?: string };
      if (!response.ok) throw new Error(data.detail || data.error || "request_failed");
      setMessage({ ok: true, text: data.detail || "Done." });
      await load();
    } catch (reason) {
      setMessage({ ok: false, text: reason instanceof Error ? reason.message : "Request failed." });
    } finally {
      setBusy("");
    }
  }

  if (!ready) {
    return <p className="p-6 text-sm text-wa-muted">Checking sign-in…</p>;
  }
  if (!session?.authenticated) {
    return (
      <main className="mx-auto max-w-lg p-6">
        <h1 className="font-display text-xl font-bold">Approvals</h1>
        <p className="mt-2 text-sm text-wa-muted">Sign in as an admin to approve registrations.</p>
        <Link className="mt-4 inline-block text-sm text-wa-green-dark hover:underline" href={`/login?next=${encodeURIComponent(`/approvals${token ? `?token=${token}` : ""}`)}`}>
          Sign in
        </Link>
      </main>
    );
  }
  if (!admin) {
    return (
      <main className="mx-auto max-w-lg p-6">
        <h1 className="font-display text-xl font-bold">Approvals</h1>
        <p className="mt-2 text-sm text-red-700">Only admins can approve or reject registrations.</p>
      </main>
    );
  }

  return (
    <main className="min-h-0 flex-1 overflow-y-auto bg-white">
      <header className="border-b border-wa-line px-4 py-3 md:px-6">
        <h1 className="font-display text-xl font-bold tracking-tight">Account approvals</h1>
        <p className="text-sm text-wa-muted">
          Pending users verified their mobile by WhatsApp OTP. Choose their role, then approve or reject (admin only).
        </p>
      </header>
      {message ? (
        <p className={cn("px-4 py-2 text-sm md:px-6", message.ok ? "text-wa-green-dark" : "text-red-700")} aria-live="polite">
          {message.text}
        </p>
      ) : null}

      <section className="px-4 py-4 md:px-6" aria-label="Pending approvals">
        <h2 className="text-sm font-medium">Pending approval</h2>
        {pending.length === 0 ? <p className="mt-2 text-sm text-wa-muted">No pending registrations.</p> : null}
        <ul className="mt-2 divide-y divide-wa-line">
          {pending.map((user) => (
            <li key={user.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 text-sm">
                <p className="font-medium">{user.name}</p>
                <p className="text-wa-muted">
                  +{user.mobile} · {user.email} · requested {user.role}
                </p>
                {user.notifyFailure ? (
                  <p className="text-[11px] text-red-700">
                    WhatsApp notify failed ({user.notifyFailure.attempts}×): {user.notifyFailure.detail}
                  </p>
                ) : null}
                <label className="mt-2 flex items-center gap-2 text-xs font-medium text-wa-muted" htmlFor={`approve-role-${user.id}`}>
                  Role on approve
                  <select
                    id={`approve-role-${user.id}`}
                    value={approveRoles[user.id] ?? user.role}
                    onChange={(event) =>
                      setApproveRoles((current) => ({
                        ...current,
                        [user.id]: event.target.value === "admin" ? "admin" : "member",
                      }))
                    }
                    className="h-8 rounded-md border border-wa-line bg-white px-2 text-sm text-wa-ink"
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={Boolean(busy)}
                  onClick={() => void act("approve", user.id)}
                  className="h-9 rounded-lg bg-wa-green px-3 text-sm font-medium text-white disabled:opacity-40"
                >
                  Approve
                </button>
                <button
                  type="button"
                  disabled={Boolean(busy)}
                  onClick={() => void act("reject", user.id)}
                  className="h-9 rounded-lg border border-wa-line px-3 text-sm text-red-700 disabled:opacity-40"
                >
                  Reject
                </button>
                <button
                  type="button"
                  disabled={Boolean(busy)}
                  onClick={() => void act("retry_notify", user.id)}
                  className="h-9 rounded-lg border border-wa-line px-3 text-sm disabled:opacity-40"
                >
                  Retry WhatsApp notify
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="border-t border-wa-line px-4 py-4 md:px-6" aria-label="Deleted accounts">
        <h2 className="text-sm font-medium">Deleted accounts (permanent purge)</h2>
        <p className="mt-1 text-xs text-wa-muted">
          Re-registration with the same mobile/email requires permanent deletion first. Does not delete chats or ERP contacts.
        </p>
        {deleted.length === 0 && rejected.length === 0 ? (
          <p className="mt-2 text-sm text-wa-muted">None.</p>
        ) : null}
        <ul className="mt-2 divide-y divide-wa-line">
          {[...deleted.map((u) => ({ ...u, kind: "deleted" as const })), ...rejected.map((u) => ({ ...u, kind: "rejected" as const }))].map(
            (user) => (
              <li key={`${user.kind}-${user.id}`} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-sm">
                  <p className="font-medium">{user.name || user.email}</p>
                  <p className="text-wa-muted">
                    {user.kind} · {user.role || "member"} · +{user.mobile || "—"} · {user.email}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={Boolean(busy)}
                  onClick={() => void act("purge", user.id)}
                  className="h-9 rounded-lg border border-red-200 px-3 text-sm text-red-700 disabled:opacity-40"
                >
                  Permanently delete
                </button>
              </li>
            ),
          )}
        </ul>
      </section>
    </main>
  );
}
