"use client";

import { useAppDialog } from "@/components/AppDialog";
import { cn } from "@/lib/cn";
import { CUSTOMER_MASTER_LOGIN_URL } from "@/lib/customer-master";
import type { AdminSessionState, IntegrationCheck, PublicWhatsAppStatus } from "@/lib/types";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type Dispatch, type FormEvent, type SetStateAction } from "react";

type CloudState = {
  field_values: {
    app_id: string;
    phone_number: string;
    phone_number_id: string;
    waba_id: string;
    business_id: string;
    graph_api_version: string;
  };
  secret_configured: {
    app_secret: boolean;
    access_token: boolean;
    webhook_verify_token: boolean;
  };
  missing_labels: string[];
  has_saved: boolean;
  webhook_url: string | null;
};

type FormValues = {
  app_id: string;
  app_secret: string;
  phone_number: string;
  phone_number_id: string;
  waba_id: string;
  business_id: string;
  graph_api_version: string;
  access_token: string;
  webhook_verify_token: string;
};

const EMPTY_FORM: FormValues = {
  app_id: "",
  app_secret: "",
  phone_number: "",
  phone_number_id: "",
  waba_id: "",
  business_id: "",
  graph_api_version: "v21.0",
  access_token: "",
  webhook_verify_token: "",
};

const ERROR_TEXT: Record<string, string> = {
  invalid_csrf: "The form expired. Reload this page and try again.",
  unauthorized: "Sign in again to change credentials.",
  invalid_value: "That value was not saved.",
  forbidden: "This account cannot change credentials.",
  invalid_origin: "The form was rejected.",
  storage_unavailable: "Local storage is unavailable.",
};

function errorText(error: unknown) {
  const code = error instanceof Error ? error.message : typeof error === "string" ? error : "";
  if (ERROR_TEXT[code]) return ERROR_TEXT[code];
  if (code && code !== "request_failed" && !/^[a-z0-9_]+$/.test(code)) return code;
  return "The request did not complete.";
}

async function readError(response: Response) {
  try {
    const body = (await response.json()) as { error?: unknown; detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
    if (typeof body.error === "string") return body.error;
  } catch {
    return "request_failed";
  }
  return "request_failed";
}

export function CloudApiScreen() {
  const [status, setStatus] = useState<PublicWhatsAppStatus | null>(null);
  const [session, setSession] = useState<AdminSessionState | null>(null);
  const [cloud, setCloud] = useState<CloudState | null>(null);
  const [phase, setPhase] = useState<"loading" | "error" | "ready">("loading");

  const load = useCallback(async () => {
    const [statusResponse, sessionResponse] = await Promise.all([
      fetch("/api/whatsapp/status", { cache: "no-store" }),
      fetch("/api/admin/session", { cache: "no-store" }),
    ]);
    if (!statusResponse.ok || !sessionResponse.ok) throw new Error("status_failed");
    const nextSession = (await sessionResponse.json()) as AdminSessionState;
    setStatus((await statusResponse.json()) as PublicWhatsAppStatus);
    setSession(nextSession);
    if (nextSession.authenticated && nextSession.role === "admin") {
      const cloudResponse = await fetch("/api/whatsapp/cloud", { cache: "no-store" });
      if (!cloudResponse.ok) throw new Error("status_failed");
      setCloud((await cloudResponse.json()) as CloudState);
    } else {
      setCloud(null);
    }
    setPhase("ready");
  }, []);

  useEffect(() => {
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
  }, [load]);

  return (
    <main className="min-h-0 flex-1 overflow-y-auto bg-white">
      <header className="border-b border-wa-line px-4 py-3 md:px-6">
        <h1 className="font-display text-xl font-bold tracking-tight">WhatsApp Cloud API</h1>
        <p className="text-sm text-wa-muted">Access token, Phone Number ID, aur webhook yahin save hote hain.</p>
      </header>
      {phase === "loading" ? <p className="px-4 py-6 text-sm text-wa-muted md:px-6">Loading connection status…</p> : null}
      {phase === "error" ? <p className="px-4 py-6 text-sm text-red-700 md:px-6">The server did not return the connection status.</p> : null}
      {phase === "ready" && status && session ? (
        <CloudForm status={status} session={session} cloud={cloud} onChanged={load} onSession={setSession} />
      ) : null}
    </main>
  );
}

function CloudForm({
  status,
  session,
  cloud,
  onChanged,
  onSession,
}: {
  status: PublicWhatsAppStatus;
  session: AdminSessionState;
  cloud: CloudState | null;
  onChanged: () => Promise<void>;
  onSession: (session: AdminSessionState) => void;
}) {
  const { confirm } = useAppDialog();
  const admin = session.authenticated && session.role === "admin";
  const [editing, setEditing] = useState(true);
  const [values, setValues] = useState<FormValues>(EMPTY_FORM);
  const [secrets, setSecrets] = useState({ app_secret: false, access_token: false, webhook_verify_token: false });
  const [missing, setMissing] = useState<string[]>([]);
  const [hasSaved, setHasSaved] = useState(false);
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [sendTest, setSendTest] = useState(false);
  const [testMobile, setTestMobile] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [seenCloud, setSeenCloud] = useState(cloud);
  if (cloud !== seenCloud) {
    setSeenCloud(cloud);
    if (cloud) {
      setValues((current) => ({
        ...current,
        app_id: cloud.field_values.app_id,
        phone_number: cloud.field_values.phone_number,
        phone_number_id: cloud.field_values.phone_number_id,
        waba_id: cloud.field_values.waba_id,
        business_id: cloud.field_values.business_id,
        graph_api_version: cloud.field_values.graph_api_version || "v21.0",
        app_secret: "",
        access_token: "",
        webhook_verify_token: "",
      }));
      setSecrets(cloud.secret_configured);
      setMissing(cloud.missing_labels);
      setHasSaved(cloud.has_saved);
    }
  }

  const webhookUrl = cloud?.webhook_url || status.productionWebhookUrl || "";
  const verified = (id: IntegrationCheck["id"]) => status.checks.some((item) => item.id === id && item.state === "verified");
  const alreadySubscribed = verified("webhookSubscribed");
  const canSubscribe =
    admin &&
    !busy &&
    !alreadySubscribed &&
    status.idsDistinct !== false &&
    verified("phoneVerified") &&
    verified("businessVerified") &&
    verified("wabaAccessible") &&
    verified("phoneOnWaba") &&
    Boolean(status.credentials.appId.configured && status.credentials.accessToken.configured);
  const subscribeTitle = alreadySubscribed
    ? "Already subscribed. No second subscribe request is needed."
    : canSubscribe
      ? "Subscribe this app"
      : "Test must verify the IDs before subscribe";

  async function postJson(url: string, body: unknown) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-csrf-token": session.csrfToken },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    if (!response.ok || payload.ok === false) {
      throw new Error(typeof payload.detail === "string" ? payload.detail : typeof payload.error === "string" ? payload.error : "request_failed");
    }
    return payload;
  }

  function applyCloud(payload: Record<string, unknown>) {
    const next = payload as unknown as CloudState;
    if (next.field_values) {
      setValues((current) => ({
        ...current,
        app_id: next.field_values.app_id || "",
        phone_number: next.field_values.phone_number || "",
        phone_number_id: next.field_values.phone_number_id || "",
        waba_id: next.field_values.waba_id || "",
        business_id: next.field_values.business_id || "",
        graph_api_version: next.field_values.graph_api_version || "v21.0",
        app_secret: "",
        access_token: "",
        webhook_verify_token: current.webhook_verify_token,
      }));
    }
    if (next.secret_configured) setSecrets(next.secret_configured);
    if (Array.isArray(next.missing_labels)) setMissing(next.missing_labels);
    if (typeof next.has_saved === "boolean") setHasSaved(next.has_saved);
  }

  async function save(event?: FormEvent) {
    event?.preventDefault();
    if (!admin || !editing) return;
    setBusy("save");
    try {
      const data = await postJson("/api/whatsapp/cloud", { values });
      applyCloud(data);
      setValues((current) => ({ ...current, app_secret: "", access_token: "", webhook_verify_token: "" }));
      setResult({ ok: true, text: typeof data.message === "string" ? data.message : "Credentials saved." });
      await onChanged();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  });
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveRef.current();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function removeCredentials() {
    if (
      !(await confirm("Saved WhatsApp token, App Secret, aur Phone Number ID is app se delete ho jayenge. Continue?", {
        title: "Delete credentials",
        confirmLabel: "Delete",
        danger: true,
      }))
    ) {
      return;
    }
    setBusy("delete");
    try {
      const data = await postJson("/api/whatsapp/cloud/delete", {});
      applyCloud(data);
      setValues(EMPTY_FORM);
      setResult({ ok: true, text: typeof data.message === "string" ? data.message : "Credentials deleted." });
      await onChanged();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  async function generateToken() {
    setBusy("generate");
    try {
      const data = await postJson("/api/whatsapp/cloud/generate", {});
      applyCloud(data);
      if (typeof data.webhook_verify_token_plain === "string") {
        setValues((current) => ({ ...current, webhook_verify_token: data.webhook_verify_token_plain as string }));
      }
      setResult({ ok: true, text: typeof data.message === "string" ? data.message : "Verify token generated." });
      await onChanged();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  async function testConnection() {
    const send = sendTest;
    if (send) {
      if (!testMobile.trim()) {
        setResult({ ok: false, text: "Test mobile is not valid. No message was sent." });
        return;
      }
      if (
        !(await confirm("Ek WhatsApp message is test mobile par jayega. Continue?", {
          title: "Send test message",
          confirmLabel: "Send",
        }))
      ) {
        return;
      }
    }
    setBusy("test");
    try {
      const response = await fetch("/api/whatsapp/test", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": session.csrfToken },
        body: JSON.stringify({
          send_test_message: send,
          confirm_send: send,
          test_to_number: testMobile,
        }),
        cache: "no-store",
      });
      const data = (await response.json()) as {
        ok?: boolean;
        detail?: string;
        error?: string;
        checks?: { label?: string; state?: string; detail?: string; badge?: string }[];
      };
      const lines = (data.checks ?? []).map((item) => {
        const mark = item.state === "verified" ? "OK" : item.state === "not_checked" ? "SKIP" : "FAIL";
        return `${mark} — ${item.label || "Check"}${item.detail ? `: ${item.detail}` : ""}`;
      });
      setResult({
        ok: Boolean(data.ok),
        text: [data.detail || errorText(data.error || "request_failed"), ...lines].join("\n"),
      });
      await onChanged();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  async function subscribeApp() {
    if (
      !(await confirm(
        "Subscribe app will add this app to the WhatsApp Business Account webhook list. One request will be sent. Continue?",
        { title: "Subscribe app", confirmLabel: "Subscribe" },
      ))
    ) {
      return;
    }
    setBusy("subscribe");
    try {
      const response = await fetch("/api/whatsapp/subscribe", {
        method: "POST",
        headers: { "x-csrf-token": session.csrfToken },
        cache: "no-store",
      });
      const data = (await response.json().catch(() => ({}))) as {
        ok?: boolean;
        posted?: boolean;
        detail?: string;
        error?: string;
        httpStatus?: number | null;
        code?: number | null;
        subcode?: number | null;
        traceId?: string | null;
        cause?: string | null;
      };
      const lines = [
        typeof data.detail === "string" && data.detail.trim() ? data.detail : errorText(data.error || "request_failed"),
        `Subscribe request sent: ${data.posted ? "yes" : "no"}`,
      ];
      if (typeof data.httpStatus === "number") lines.push(`Meta HTTP ${data.httpStatus}`);
      if (typeof data.code === "number" || typeof data.subcode === "number") {
        lines.push(`Meta code ${data.code ?? "unknown"}, subcode ${data.subcode ?? "none"}`);
      }
      if (data.cause) lines.push(`Cause: ${data.cause}`);
      if (data.traceId) lines.push(`Trace ${data.traceId}`);
      setResult({ ok: response.ok && data.ok === true, text: lines.join("\n") });
      await onChanged();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  async function copyWebhook() {
    if (!webhookUrl) return;
    try {
      await navigator.clipboard.writeText(webhookUrl);
      setResult({ ok: true, text: "Webhook URL copy ho gaya." });
    } catch {
      setResult({ ok: true, text: webhookUrl });
    }
  }

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setBusy("signin");
    try {
      const response = await fetch("/api/admin/session", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": session.csrfToken },
        body: JSON.stringify({ email, password }),
        cache: "no-store",
      });
      if (!response.ok) throw new Error(await readError(response));
      setPassword("");
      onSession((await response.json()) as AdminSessionState);
      await onChanged();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  function setField(key: keyof FormValues, value: string) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  const locked = !admin || !editing;
  const secretPlaceholder = (saved: boolean) => (saved ? "Saved. Blank chhodo to purana secret rahega." : "");

  return (
    <form onSubmit={(event) => void save(event)} className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-4 md:px-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-wa-muted">Public website par token mat rakho. Meta is URL ko call karta hai.</p>
        <span className={cn("rounded-full px-2 py-1 text-[11px] font-semibold", status.connection === "connected" ? "bg-wa-leaf text-wa-green-dark" : "bg-wa-app text-wa-icon")}>
          {status.connection === "connected" ? "Connected" : "Not connected"}
        </span>
      </div>
      {status.demoMode ? (
        <p className="rounded-lg bg-wa-app px-3 py-2 text-sm text-wa-muted">Demo mode. Sample conversations are not live WhatsApp data.</p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => setEditing(true)} disabled={!admin || editing || Boolean(busy)} className={buttonClass}>
          Edit
        </button>
        <button type="submit" disabled={!admin || !editing || Boolean(busy)} className={primaryClass}>
          {busy === "save" ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={() => void removeCredentials()} disabled={!admin || !hasSaved || Boolean(busy)} className={buttonClass}>
          {busy === "delete" ? "Deleting…" : "Delete"}
        </button>
        <button type="button" onClick={() => void testConnection()} disabled={!admin || Boolean(busy)} className={buttonClass}>
          {busy === "test" ? "Testing…" : "Test"}
        </button>
        <button type="button" onClick={() => void subscribeApp()} disabled={!canSubscribe} title={subscribeTitle} className={buttonClass}>
          {busy === "subscribe" ? "Subscribing…" : alreadySubscribed ? "Subscribed" : "Subscribe app"}
        </button>
        <Link href="/" className={buttonClass} title="Open the team WhatsApp inbox for live chats and replies">
          Staff inbox
        </Link>
      </div>

      <CustomerMasterSync admin={admin} csrfToken={session.csrfToken} busy={busy} setBusy={setBusy} setResult={setResult} />

      {admin ? <SmtpConnectionCard csrfToken={session.csrfToken} busy={busy} setBusy={setBusy} setResult={setResult} /> : null}

      {!admin ? (
        <div className="rounded-lg border border-wa-line px-3 py-3">
          <h2 className="text-sm font-medium">Admin required</h2>
          <p className="mt-1 text-sm text-wa-muted">
            Signed in as {session.email || "member"}. Cloud credentials and ERP token need an admin account.{" "}
            <Link href="/account" className="text-wa-green-dark hover:underline">
              Profile
            </Link>
          </p>
          <div className="mt-2 flex flex-col gap-2 sm:flex-row">
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Admin email" autoComplete="username" className={inputClass} />
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" autoComplete="current-password" className={inputClass} />
            <button type="button" onClick={(event) => void signIn(event)} disabled={Boolean(busy)} className={primaryClass}>
              Switch to admin
            </button>
          </div>
        </div>
      ) : null}

      <div>
        <label className="text-sm font-medium" htmlFor="waWebhookUrl">
          Webhook URL
        </label>
        <div className="mt-1 flex flex-col gap-2 sm:flex-row">
          <input id="waWebhookUrl" readOnly value={webhookUrl || "Not configured"} className={inputClass} />
          <button type="button" onClick={() => void copyWebhook()} disabled={!webhookUrl} className={buttonClass}>
            Copy
          </button>
        </div>
        <p className="mt-1 text-xs text-wa-muted">Meta Developer → WhatsApp → Configuration → Callback URL.</p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="Facebook App ID *" id="app_id" value={values.app_id} disabled={locked} onChange={(value) => setField("app_id", value)} />
        <Field label="Facebook App Secret *" id="app_secret" value={values.app_secret} disabled={locked} secret placeholder={secretPlaceholder(secrets.app_secret)} onChange={(value) => setField("app_secret", value)} />
        <Field label="WhatsApp phone number" id="phone_number" value={values.phone_number} disabled={locked} onChange={(value) => setField("phone_number", value)} />
        <Field label="Phone Number ID *" id="phone_number_id" value={values.phone_number_id} disabled={locked} onChange={(value) => setField("phone_number_id", value)} />
        <Field label="WhatsApp Business Account ID" id="waba_id" value={values.waba_id} disabled={locked} onChange={(value) => setField("waba_id", value)} />
        <Field label="Business ID" id="business_id" value={values.business_id} disabled={locked} onChange={(value) => setField("business_id", value)} />
        <Field label="Graph API version" id="graph_api_version" value={values.graph_api_version} disabled={locked} onChange={(value) => setField("graph_api_version", value)} />
        <Field label="Access token *" id="access_token" value={values.access_token} disabled={locked} secret placeholder={secretPlaceholder(secrets.access_token)} onChange={(value) => setField("access_token", value)} />
        <div>
          <label className="text-sm font-medium" htmlFor="webhook_verify_token">
            Webhook verify token
          </label>
          <div className="mt-1 flex flex-col gap-2 sm:flex-row">
            <input
              id="webhook_verify_token"
              type="password"
              autoComplete="new-password"
              value={values.webhook_verify_token}
              disabled={locked}
              placeholder={secretPlaceholder(secrets.webhook_verify_token)}
              onChange={(event) => setField("webhook_verify_token", event.target.value)}
              className={inputClass}
            />
            <button type="button" onClick={() => void generateToken()} disabled={!admin || Boolean(busy)} className={buttonClass}>
              Generate
            </button>
          </div>
        </div>
        <Field label="Test mobile (optional)" id="test_to_number" value={testMobile} disabled={!admin} placeholder="91XXXXXXXXXX" onChange={setTestMobile} />
        <label className="flex items-center gap-2 text-sm md:col-span-2">
          <input type="checkbox" checked={sendTest} onChange={(event) => setSendTest(event.target.checked)} disabled={!admin} />
          Test par ek message bhi bhejo
        </label>
      </div>

      <p className="text-sm text-wa-muted">Khali secret Save par purana token rehta hai. Poora hataane ke liye Delete. Test last saved credentials use karta hai.</p>
      {missing.length > 0 ? <p className="text-sm text-amber-800">Abhi baaki: {missing.join(", ")}</p> : null}
      <ul className="divide-y divide-wa-line rounded-lg border border-wa-line">
        {status.checks
          .filter((item) => ["phoneVerified", "businessVerified", "wabaAccessible", "phoneOnWaba", "webhookSubscribed", "messageSending"].includes(item.id))
          .map((item) => (
            <li key={item.id} className="flex items-start justify-between gap-3 px-3 py-2">
              <div>
                <p className="text-sm font-medium">{item.label}</p>
                <p className="text-sm text-wa-muted">{item.detail}</p>
              </div>
              <span className="shrink-0 rounded-full bg-wa-app px-2 py-1 text-[11px] font-semibold">{item.badge}</span>
            </li>
          ))}
      </ul>
      {result ? (
        <div
          className={cn(
            "overflow-x-auto whitespace-pre-wrap rounded-lg border px-3 py-2 font-mono text-sm",
            result.ok ? "border-wa-green" : "border-red-200",
          )}
        >
          {result.text.split("\n").map((line, index) => {
            const tone = line.startsWith("OK")
              ? "text-wa-green-dark"
              : line.startsWith("FAIL")
                ? "text-red-800"
                : line.startsWith("SKIP")
                  ? "text-wa-muted"
                  : result.ok
                    ? "text-wa-green-dark"
                    : "text-red-800";
            return (
              <div key={`${index}-${line.slice(0, 24)}`} className={tone}>
                {line || "\u00a0"}
              </div>
            );
          })}
        </div>
      ) : null}
    </form>
  );
}

function ConnectionBadge({ connection }: { connection: "connected" | "disconnected" }) {
  const connected = connection === "connected";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
        connected ? "bg-wa-leaf text-wa-green-dark" : "bg-red-50 text-red-700",
      )}
      aria-live="polite"
    >
      {connected ? "Connected" : "Disconnected"}
    </span>
  );
}

function SmtpConnectionCard({
  csrfToken,
  busy,
  setBusy,
  setResult,
}: {
  csrfToken: string;
  busy: string;
  setBusy: Dispatch<SetStateAction<string>>;
  setResult: Dispatch<SetStateAction<{ ok: boolean; text: string } | null>>;
}) {
  const [connection, setConnection] = useState<"connected" | "disconnected">("disconnected");
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [detail, setDetail] = useState("");

  const refresh = useCallback(async () => {
    const response = await fetch("/api/admin/mail", { cache: "no-store" });
    if (!response.ok) return;
    const data = (await response.json()) as {
      connection?: string;
      checkedAt?: string | null;
      detail?: string;
    };
    setConnection(data.connection === "connected" ? "connected" : "disconnected");
    setCheckedAt(typeof data.checkedAt === "string" ? data.checkedAt : null);
    setDetail(typeof data.detail === "string" ? data.detail : "");
  }, []);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  async function verify() {
    setBusy("mail");
    setResult(null);
    try {
      const response = await fetch("/api/admin/mail", {
        method: "POST",
        headers: { "x-csrf-token": csrfToken },
      });
      const data = (await response.json()) as {
        ok?: boolean;
        connection?: string;
        checkedAt?: string;
        detail?: string;
      };
      setConnection(data.connection === "connected" ? "connected" : "disconnected");
      setCheckedAt(typeof data.checkedAt === "string" ? data.checkedAt : new Date().toISOString());
      setDetail(typeof data.detail === "string" ? data.detail : data.ok ? "SMTP verified." : "SMTP verify failed.");
      setResult({
        ok: Boolean(data.ok),
        text: typeof data.detail === "string" ? data.detail : data.ok ? "SMTP verified." : "SMTP verify failed.",
      });
    } catch (reason) {
      setConnection("disconnected");
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="rounded-lg border border-wa-line px-3 py-3" aria-label="Outbound email">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-medium">Titan / SMTP email</h2>
        <ConnectionBadge connection={connection} />
      </div>
      <p className="mt-1 text-sm text-wa-muted">
        OTP and recovery mail use server env SMTP_* (see docs/AUTH.md). Password is never shown here.
      </p>
      <button type="button" disabled={Boolean(busy)} className={`${buttonClass} mt-2`} onClick={() => void verify()}>
        {busy === "mail" ? "Checking…" : "Verify SMTP connection"}
      </button>
      <p className="mt-2 text-xs text-wa-muted" aria-live="polite">
        {detail || "Run Verify SMTP connection to confirm Titan/SMTP auth."}
        {checkedAt ? ` · Last checked ${new Date(checkedAt).toLocaleString()}` : ""}
      </p>
    </section>
  );
}

function CustomerMasterSync({
  admin,
  csrfToken,
  busy,
  setBusy,
  setResult,
}: {
  admin: boolean;
  csrfToken: string;
  busy: string;
  setBusy: Dispatch<SetStateAction<string>>;
  setResult: Dispatch<SetStateAction<{ ok: boolean; text: string } | null>>;
}) {
  const { confirm } = useAppDialog();
  const [pasteToken, setPasteToken] = useState("");
  const [revealedToken, setRevealedToken] = useState("");
  const [tokenConfigured, setTokenConfigured] = useState(false);
  const [tokenPreview, setTokenPreview] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);
  const [detail, setDetail] = useState("");
  const [connection, setConnection] = useState<"connected" | "disconnected">("disconnected");
  const [connectionCheckedAt, setConnectionCheckedAt] = useState<string | null>(null);
  const [connectionDetail, setConnectionDetail] = useState("");

  const refresh = useCallback(async () => {
    const response = await fetch("/api/customers/status", { cache: "no-store" });
    if (!response.ok) return;
    const data = (await response.json()) as {
      count?: number;
      lastSyncAt?: string | null;
      tokenConfigured?: boolean;
      tokenPreview?: string | null;
      detail?: string;
      connection?: string;
      connectionCheckedAt?: string | null;
      connectionDetail?: string;
    };
    setCount(typeof data.count === "number" ? data.count : 0);
    setLastSyncAt(typeof data.lastSyncAt === "string" ? data.lastSyncAt : null);
    setTokenConfigured(Boolean(data.tokenConfigured));
    setTokenPreview(typeof data.tokenPreview === "string" ? data.tokenPreview : null);
    setDetail(typeof data.detail === "string" ? data.detail : "");
    setConnection(data.connection === "connected" ? "connected" : "disconnected");
    setConnectionCheckedAt(typeof data.connectionCheckedAt === "string" ? data.connectionCheckedAt : null);
    setConnectionDetail(typeof data.connectionDetail === "string" ? data.connectionDetail : "");
  }, []);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  async function generateToken() {
    if (!admin) return;
    if (
      tokenConfigured &&
      !(await confirm("Generate a new token? The previous local token will stop working until ERP is updated.", {
        title: "Generate token",
        confirmLabel: "Generate",
        danger: true,
      }))
    ) {
      return;
    }
    setBusy("erp-token");
    try {
      const response = await fetch("/api/customers/token", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken },
        body: JSON.stringify({ action: "generate" }),
        cache: "no-store",
      });
      const data = (await response.json().catch(() => ({}))) as { detail?: string; error?: string; token?: string };
      if (!response.ok || !data.token) throw new Error(data.detail || data.error || "request_failed");
      setRevealedToken(data.token);
      setResult({
        ok: true,
        text: `${data.detail || "Token generated."}\n\n${data.token}\n\nCopy now — it will not be shown again.`,
      });
      await refresh();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  async function revokeToken() {
    if (!admin) return;
    if (!(await confirm("Revoke the local ERP sync token?", { title: "Revoke token", confirmLabel: "Revoke", danger: true }))) {
      return;
    }
    setBusy("erp-token");
    try {
      const response = await fetch("/api/customers/token", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken },
        body: JSON.stringify({ action: "revoke" }),
        cache: "no-store",
      });
      const data = (await response.json().catch(() => ({}))) as { detail?: string; error?: string };
      if (!response.ok) throw new Error(data.detail || data.error || "request_failed");
      setRevealedToken("");
      setResult({ ok: true, text: typeof data.detail === "string" ? data.detail : "Token revoked." });
      await refresh();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  async function savePastedToken() {
    if (!admin || !pasteToken.trim()) return;
    setBusy("erp-token");
    try {
      const response = await fetch("/api/customers/credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken },
        body: JSON.stringify({ syncToken: pasteToken }),
        cache: "no-store",
      });
      const data = (await response.json().catch(() => ({}))) as { detail?: string; error?: string };
      if (!response.ok) throw new Error(data.detail || data.error || "request_failed");
      setPasteToken("");
      setRevealedToken("");
      setResult({ ok: true, text: typeof data.detail === "string" ? data.detail : "ERP sync token saved." });
      await refresh();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  async function syncCustomers() {
    if (!admin) return;
    setBusy("erp-sync");
    try {
      const response = await fetch("/api/customers/sync", {
        method: "POST",
        headers: { "x-csrf-token": csrfToken },
        cache: "no-store",
      });
      const data = (await response.json().catch(() => ({}))) as {
        detail?: string;
        error?: string;
        created?: number;
        updated?: number;
        skippedInvalidMobile?: number;
        duplicateInFeed?: number;
        conflicts?: unknown[];
      };
      if (!response.ok) throw new Error(data.detail || data.error || "request_failed");
      setResult({
        ok: true,
        text:
          typeof data.detail === "string"
            ? data.detail
            : `Created ${data.created ?? 0}, updated ${data.updated ?? 0}, skipped invalid ${data.skippedInvalidMobile ?? 0}.`,
      });
      await refresh();
    } catch (reason) {
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  async function testConnection() {
    if (!admin) return;
    setBusy("erp-test");
    try {
      const response = await fetch("/api/customers/test", {
        method: "POST",
        headers: { "x-csrf-token": csrfToken },
        cache: "no-store",
      });
      const data = (await response.json().catch(() => ({}))) as {
        ok?: boolean;
        connection?: string;
        checkedAt?: string;
        detail?: string;
        error?: string;
      };
      setConnection(data.connection === "connected" ? "connected" : "disconnected");
      setConnectionCheckedAt(typeof data.checkedAt === "string" ? data.checkedAt : null);
      setConnectionDetail(typeof data.detail === "string" ? data.detail : "");
      setResult({
        ok: Boolean(data.ok),
        text: typeof data.detail === "string" ? data.detail : data.ok ? "ERP connection verified." : "ERP connection failed.",
      });
      await refresh();
    } catch (reason) {
      setConnection("disconnected");
      setResult({ ok: false, text: errorText(reason) });
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="rounded-lg border border-wa-line px-3 py-3" aria-label="Customer Master sync">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-medium">Customer Master sync</h2>
            <ConnectionBadge connection={connection} />
          </div>
          <p className="text-sm text-wa-muted">
            Syncs only ERP customers with a valid mobile. Duplicate normalized mobiles are not merged.
          </p>
        </div>
        <p className="shrink-0 text-[11px] text-wa-muted">
          {count > 0 ? `${count} contacts` : "No contacts yet"}
          {lastSyncAt ? ` · ${new Date(lastSyncAt).toLocaleString()}` : ""}
        </p>
      </div>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <a
          href={CUSTOMER_MASTER_LOGIN_URL}
          target="_blank"
          rel="noopener noreferrer"
          className={buttonClass}
          title="Open ERP login on app.jtcsxpert.com"
        >
          ERP Login
        </a>
        <button type="button" onClick={() => void syncCustomers()} disabled={!admin || Boolean(busy)} className={primaryClass}>
          {busy === "erp-sync" ? "Syncing…" : "Sync customers"}
        </button>
        <button type="button" onClick={() => void generateToken()} disabled={!admin || Boolean(busy)} className={buttonClass}>
          {busy === "erp-token" ? "Working…" : "Generate token"}
        </button>
        <button type="button" onClick={() => void revokeToken()} disabled={!admin || !tokenConfigured || Boolean(busy)} className={buttonClass}>
          Revoke token
        </button>
        <button
          type="button"
          onClick={() => void testConnection()}
          disabled={!admin || !tokenConfigured || Boolean(busy)}
          className={buttonClass}
        >
          {busy === "erp-test" ? "Testing…" : "Test connection"}
        </button>
      </div>
      <p className="mt-2 text-xs text-wa-muted" aria-live="polite">
        {connectionDetail ||
          (tokenConfigured
            ? `Token configured${tokenPreview ? ` (${tokenPreview})` : ""}. Run Test connection to verify ERP.`
            : "Token not configured.")}
        {connectionCheckedAt ? ` · Last checked ${new Date(connectionCheckedAt).toLocaleString()}` : ""}
      </p>
      <p className="mt-1 text-xs text-wa-muted">
        Outbound to ERP as <code className="rounded bg-wa-app px-1">X-WhatsApp-Sync-Token</code>. Value is never listed again after
        generate/save.
      </p>
      {revealedToken ? (
        <div className="mt-2 rounded-lg border border-wa-green bg-wa-leaf/40 px-3 py-2">
          <p className="text-xs font-medium text-wa-green-dark">Copy once — not shown again</p>
          <code className="mt-1 block break-all text-xs">{revealedToken}</code>
        </div>
      ) : null}
      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-[1fr_auto]">
        <input
          type="password"
          autoComplete="new-password"
          value={pasteToken}
          disabled={!admin || Boolean(busy)}
          placeholder="Or paste ERP token (min 16 chars)"
          onChange={(event) => setPasteToken(event.target.value)}
          className={inputClass}
        />
        <button type="button" onClick={() => void savePastedToken()} disabled={!admin || !pasteToken.trim() || Boolean(busy)} className={buttonClass}>
          Save token
        </button>
      </div>
      <p className="mt-2 text-xs text-wa-muted">
        {detail || "Set the same token on app.jtcsxpert.com as WHATSAPP_CUSTOMER_SYNC_TOKEN. See docs/ERP_SYNC.md."}
      </p>
    </section>
  );
}

function Field({
  label,
  id,
  value,
  onChange,
  disabled,
  secret,
  placeholder,
}: {
  label: string;
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  secret?: boolean;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="text-sm font-medium" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type={secret ? "password" : "text"}
        autoComplete={secret ? "new-password" : "off"}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className={inputClass}
      />
    </div>
  );
}

const inputClass = "mt-1 h-10 w-full min-w-0 rounded-lg border border-wa-line px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:bg-wa-app";
const buttonClass =
  "inline-flex h-9 items-center justify-center rounded-lg border border-wa-line bg-white px-3 text-sm font-medium hover:bg-wa-app focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:opacity-40";
const primaryClass =
  "inline-flex h-9 items-center justify-center rounded-lg bg-wa-green px-3 text-sm font-medium text-white hover:bg-wa-green-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:opacity-40";
