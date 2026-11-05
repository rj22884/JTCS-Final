"use client";

import { useAuth } from "@/components/AuthProvider";
import type { AdminSessionState } from "@/lib/types";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

const ERROR_TEXT: Record<string, string> = {
  invalid_csrf: "The form expired. Reload and try again.",
  invalid_origin: "The form was rejected.",
  invalid_value: "Check the form fields and try again.",
  invalid_mobile: "Enter a valid mobile number.",
  invalid_code: "That code is not valid or has expired.",
  whatsapp_not_configured: "WhatsApp is not connected on the server, so an OTP cannot be sent.",
  otp_delivery_failed: "The OTP could not be sent by WhatsApp. Try again later.",
  deleted_account_exists:
    "A deleted account already uses this mobile or email. Ask an admin to permanently remove it before registering again.",
  sign_in_failed: "Sign-in failed. Check your email/mobile and password.",
  sign_in_unavailable: "Too many attempts. Try again later.",
  resend_cooldown: "Please wait before requesting another code.",
  pending_approval: "Your account is pending admin approval. You cannot sign in yet.",
  rejected: "This registration was rejected. Contact an admin.",
  verify_required: "Complete mobile verification and admin approval before signing in.",
  storage_unavailable: "Local storage is unavailable.",
  session_expired: "Your session expired. Sign in again.",
};

function errorText(error: unknown) {
  const code = error instanceof Error ? error.message : "";
  return ERROR_TEXT[code] ?? "The request failed.";
}

async function readError(response: Response) {
  try {
    const body = (await response.json()) as { error?: unknown; detail?: unknown };
    if (typeof body.error === "string") return body.error;
  } catch {
    return "request_failed";
  }
  return "request_failed";
}

function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <label className="mt-3 block text-sm font-medium" htmlFor={id}>
      {label}
      <span className="mt-1 flex gap-2">
        <input
          id={id}
          type={show ? "text" : "password"}
          autoComplete={autoComplete}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-10 min-w-0 flex-1 rounded-lg border border-wa-line px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
        />
        <button
          type="button"
          onClick={() => setShow((current) => !current)}
          className="h-10 shrink-0 rounded-lg border border-wa-line px-3 text-xs font-medium hover:bg-wa-app focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
          aria-pressed={show}
        >
          {show ? "Hide" : "Show"}
        </button>
      </span>
    </label>
  );
}

export function AuthScreen({
  mode,
}: {
  mode: "login" | "register" | "verify" | "forgot-password" | "forgot-user-id" | "reset" | "account";
}) {
  const router = useRouter();
  const params = useSearchParams();
  const { session, ready, refresh, applySession } = useAuth();
  const nextPath = params.get("next")?.startsWith("/") ? params.get("next")! : "/";
  const [name, setName] = useState("");
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [mobile, setMobile] = useState(params.get("mobile") ?? "");
  const [role, setRole] = useState<"member" | "admin">("member");
  const [password, setPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [code, setCode] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [recoveredEmail, setRecoveredEmail] = useState("");

  useEffect(() => {
    if (!ready) return;
    if (!session) setError("Could not start the form.");
  }, [ready, session]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  async function post(url: string, body: object) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-csrf-token": session?.csrfToken ?? "" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) throw new Error(await readError(response));
    return response;
  }

  async function resendCode(purpose: "register" | "reset" | "recover_id") {
    if (!session || cooldown > 0) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await post("/api/auth/resend", { mobile, purpose });
      setNotice("If a code can be sent, it is on its way by WhatsApp.");
      setCooldown(60);
    } catch (reason) {
      setError(errorText(reason));
      if (reason instanceof Error && reason.message === "resend_cooldown") setCooldown(60);
    } finally {
      setBusy(false);
    }
  }

  async function logout(nextHref = "/login") {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/session", {
        method: "DELETE",
        headers: { "x-csrf-token": session.csrfToken },
        cache: "no-store",
      });
      if (!response.ok) throw new Error(await readError(response));
      const next = await refresh();
      if (!next) {
        applySession({
          authenticated: false,
          adminConfigured: true,
          csrfToken: "",
          email: null,
          role: null,
        });
      }
      router.replace(nextHref.startsWith("/") ? nextHref : "/login");
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!session) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "login") {
        const response = await post("/api/admin/session", { email: email || mobile, password, rememberMe });
        const next = (await response.json()) as AdminSessionState;
        applySession(next);
        router.replace(nextPath || "/");
        return;
      }
      if (mode === "register") {
        await post("/api/auth/register", { name, email, mobile, password, role });
        setNotice("If registration can continue, a WhatsApp OTP was sent to your mobile.");
        router.push(`/verify?mobile=${encodeURIComponent(mobile)}`);
        return;
      }
      if (mode === "verify") {
        const response = await post("/api/auth/verify", { mobile, code });
        const data = (await response.json()) as { detail?: string };
        setNotice(data.detail || "Mobile verified. Your account is pending admin approval.");
        return;
      }
      if (mode === "forgot-password") {
        await post("/api/auth/forgot-password", { mobile });
        setNotice("If an account exists for that mobile, a reset code was sent by WhatsApp.");
        router.push(`/reset-password?mobile=${encodeURIComponent(mobile)}`);
        return;
      }
      if (mode === "forgot-user-id") {
        if (code) {
          const response = await post("/api/auth/forgot-user-id", { mobile, code });
          const data = (await response.json()) as { email?: string };
          if (data.email) {
            setRecoveredEmail(data.email);
            setNotice("Your sign-in email is shown below.");
          } else {
            setNotice("If an account exists, continue with the next step.");
          }
          return;
        }
        await post("/api/auth/forgot-user-id", { mobile });
        setNotice("If an account exists for that mobile, a WhatsApp OTP was sent.");
        return;
      }
      if (mode === "reset") {
        await post("/api/auth/reset-password", { mobile, code, password });
        setNotice("Password updated. You can sign in.");
        return;
      }
      await post("/api/auth/change-password", { current: password, next: nextPassword });
      setPassword("");
      setNextPassword("");
      setNotice("Password updated.");
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  const title = {
    login: "Sign in",
    register: "Create account",
    verify: "Mobile verification",
    "forgot-password": "Forgot password",
    "forgot-user-id": "Forgot user id",
    reset: "Reset password",
    account: "Account",
  }[mode];

  const inputClass =
    "mt-1 h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green";

  return (
    <main className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto bg-wa-app px-4 py-8">
      <form onSubmit={(event) => void submit(event)} className="w-full max-w-md rounded-lg border border-wa-line bg-white p-4">
        <h1 className="font-display text-xl font-bold tracking-tight">{title}</h1>
        <p className="mt-1 text-[13px] font-medium leading-5 text-wa-muted">
          {mode === "register"
            ? "Register with name, mobile, email, and role. A WhatsApp OTP verifies your mobile. An admin must approve before you can sign in (even if you request Admin)."
            : mode === "verify"
              ? "Enter the 6-digit code sent to your mobile on WhatsApp."
              : mode === "forgot-user-id"
                ? "Enter the mobile on the account. After OTP verification, your sign-in email is shown here (not emailed)."
                : mode === "forgot-password" || mode === "reset"
                  ? "Password recovery uses a WhatsApp OTP on your registered mobile."
                  : mode === "login"
                    ? "Sign in with email or mobile, and your password."
                    : mode === "account"
                      ? "Manage your password or sign out."
                      : "WhatsApp CRM account"}
        </p>

        {mode === "register" ? (
          <label className="mt-4 block text-sm font-medium" htmlFor="auth-name">
            Name
            <input id="auth-name" required value={name} onChange={(event) => setName(event.target.value)} className={inputClass} />
          </label>
        ) : null}

        {mode === "register" ? (
          <label className="mt-3 block text-sm font-medium" htmlFor="auth-role">
            Role type
            <select
              id="auth-role"
              required
              value={role}
              onChange={(event) => setRole(event.target.value === "admin" ? "admin" : "member")}
              className={inputClass}
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          </label>
        ) : null}

        {mode === "login" ? (
          <label className="mt-4 block text-sm font-medium" htmlFor="auth-login">
            Email or mobile
            <input
              id="auth-login"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className={inputClass}
              required
            />
          </label>
        ) : null}

        {mode === "register" ? (
          <label className="mt-3 block text-sm font-medium" htmlFor="auth-email">
            Email address
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className={inputClass}
              required
            />
          </label>
        ) : null}

        {(mode === "register" ||
          mode === "verify" ||
          mode === "forgot-password" ||
          mode === "forgot-user-id" ||
          mode === "reset") && (
          <label className="mt-3 block text-sm font-medium" htmlFor="auth-mobile">
            Mobile number
            <input
              id="auth-mobile"
              inputMode="tel"
              autoComplete="tel"
              value={mobile}
              onChange={(event) => setMobile(event.target.value)}
              className={inputClass}
              required
            />
          </label>
        )}

        {mode === "account" ? (
          <p className="mt-3 text-sm">
            Signed in as {session?.email}
            {session?.role ? (
              <>
                {" "}
                · Role: <span className="font-medium capitalize">{session.role}</span>
              </>
            ) : null}
          </p>
        ) : null}

        {(mode === "verify" || mode === "reset" || (mode === "forgot-user-id" && !recoveredEmail)) && (
          <label className="mt-3 block text-sm font-medium" htmlFor="auth-code">
            6-digit WhatsApp code
            <input
              id="auth-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className={inputClass}
              required={mode !== "forgot-user-id"}
            />
          </label>
        )}

        {(mode === "login" || mode === "register" || mode === "reset" || mode === "account") && (
          <PasswordField
            id="auth-password"
            label={mode === "account" ? "Current password" : "Password"}
            value={password}
            onChange={setPassword}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        )}
        {mode === "account" ? (
          <PasswordField
            id="auth-next"
            label="New password"
            value={nextPassword}
            onChange={setNextPassword}
            autoComplete="new-password"
          />
        ) : null}
        {mode === "login" ? (
          <label className="mt-3 flex items-center gap-2 text-sm" htmlFor="auth-remember">
            <input
              id="auth-remember"
              type="checkbox"
              checked={rememberMe}
              onChange={(event) => setRememberMe(event.target.checked)}
              className="h-4 w-4 rounded border-wa-line text-wa-green focus-visible:ring-2 focus-visible:ring-wa-green"
            />
            Remember me (keeps you signed in longer on this device)
          </label>
        ) : null}

        {recoveredEmail ? (
          <p className="mt-3 rounded-lg bg-wa-leaf/40 px-3 py-2 text-sm text-wa-green-dark">
            Sign-in email: <strong>{recoveredEmail}</strong>
          </p>
        ) : null}

        <button
          type="submit"
          disabled={busy || !ready || !session}
          className="mt-4 inline-flex h-10 w-full items-center justify-center rounded-lg bg-wa-green text-sm font-medium text-white hover:bg-wa-green-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:opacity-40"
        >
          {busy || !ready
            ? "Please wait…"
            : mode === "forgot-user-id" && code
              ? "Reveal sign-in email"
              : mode === "forgot-user-id"
                ? "Send WhatsApp code"
                : mode === "account"
                  ? "Update password"
                  : title}
        </button>
        {(mode === "verify" || mode === "reset" || mode === "forgot-user-id") && (
          <button
            type="button"
            disabled={busy || !session || cooldown > 0 || !mobile}
            onClick={() =>
              void resendCode(mode === "reset" ? "reset" : mode === "forgot-user-id" ? "recover_id" : "register")
            }
            className="mt-2 inline-flex h-10 w-full items-center justify-center rounded-lg border border-wa-line text-sm font-medium hover:bg-wa-app focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:opacity-40"
          >
            {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend WhatsApp code"}
          </button>
        )}
        {mode === "account" ? (
          <button
            type="button"
            disabled={busy || !session}
            onClick={() => void logout()}
            className="mt-2 inline-flex h-10 w-full items-center justify-center rounded-lg border border-wa-line text-sm font-medium hover:bg-wa-app focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:opacity-40"
          >
            Sign out
          </button>
        ) : null}
        {error ? (
          <p className="mt-3 text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="mt-3 text-sm text-wa-green-dark" role="status">
            {notice}
          </p>
        ) : null}
        <div className="mt-4 flex flex-col gap-1 text-sm">
          {mode !== "login" && mode !== "account" ? (
            <Link className="text-wa-green-dark hover:underline" href="/login">
              Sign in
            </Link>
          ) : null}
          {mode === "account" && session?.authenticated ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void logout("/register")}
              className="text-left text-wa-green-dark hover:underline disabled:opacity-40"
            >
              Create account
            </button>
          ) : null}
          {mode !== "register" && mode !== "account" ? (
            <Link className="text-wa-green-dark hover:underline" href="/register">
              Create account
            </Link>
          ) : null}
          {mode === "login" ? (
            <>
              <Link className="text-wa-green-dark hover:underline" href="/forgot-password">
                Forgot password
              </Link>
              <Link className="text-wa-green-dark hover:underline" href="/forgot-user-id">
                Forgot user id
              </Link>
            </>
          ) : null}
        </div>
      </form>
    </main>
  );
}
