import "server-only";

import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import {
  isSessionToken,
  LOGIN_MAX_ATTEMPTS,
  LOGIN_WINDOW_MS,
  sessionTtlMs,
} from "@/lib/auth-policy";
import { getDb } from "@/lib/db";
import { json } from "@/lib/http";
import { verifyPassword } from "@/lib/passwords";
import { canLogin, findUserByLogin, hasVerifiedAdmin, type UserRole } from "@/lib/users";
import type { NextRequest, NextResponse } from "next/server";

type SessionRow = {
  id: string;
  csrf: string;
  expires_at: number | bigint;
  user_id: string | null;
  role: UserRole | null;
  email: string | null;
  name: string | null;
  avatar_path: string | null;
  verified: number | bigint | null;
  status: string | null;
};

function cookieBase(httpOnly: boolean, maxAgeSeconds: number) {
  return {
    httpOnly,
    sameSite: "strict" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: maxAgeSeconds,
  };
}

export function isAdminConfigured() {
  return hasVerifiedAdmin();
}

function clientHash(request: NextRequest) {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "";
  return createHash("sha256")
    .update(forwarded || "local")
    .digest("hex");
}

function headerHost(request: NextRequest) {
  const raw = request.headers.get("x-forwarded-host") || request.headers.get("host") || "";
  return raw.split(",")[0]?.trim().toLowerCase() ?? "";
}

function publicHttpsHosts() {
  const hosts = new Set<string>(["wa.ukdscwala.com"]);
  const webhook = process.env.WHATSAPP_WEBHOOK_URL?.trim();
  if (!webhook) return hosts;
  try {
    hosts.add(new URL(webhook).hostname.toLowerCase());
  } catch {
    return hosts;
  }
  return hosts;
}

export function sameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  if (origin === request.nextUrl.origin) return true;
  let originUrl: URL;
  try {
    originUrl = new URL(origin);
  } catch {
    return false;
  }
  const host = headerHost(request);
  const hostName = host.replace(/:\d+$/, "");
  const originHost = originUrl.host.toLowerCase();
  const originName = originUrl.hostname.toLowerCase();
  const hostMatches =
    originHost === host || originName === hostName || originHost === request.nextUrl.host.toLowerCase();
  if (!hostMatches) return false;
  const forwarded = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim().toLowerCase();
  if (forwarded === "https" && originUrl.protocol === "https:") return true;
  return originUrl.protocol === "https:" && publicHttpsHosts().has(originName);
}

export function readSession(request: NextRequest) {
  const id = request.cookies.get("wa_admin")?.value ?? "";
  if (!isSessionToken(id)) return null;
  const row = getDb()
    .prepare(
      `SELECT s.id, s.csrf, s.expires_at, s.user_id, u.role, u.email, IFNULL(u.name, '') AS name,
              u.avatar_path, u.verified, IFNULL(u.status, 'active') AS status
       FROM admin_sessions s
       LEFT JOIN users u ON u.id = s.user_id
       WHERE s.id = ?`,
    )
    .get(id) as SessionRow | undefined;
  if (!row || !isSessionToken(row.csrf)) return null;
  if (
    Number(row.expires_at) <= Date.now() ||
    Number(row.verified ?? 0) !== 1 ||
    String(row.status ?? "") !== "active"
  ) {
    getDb().prepare("DELETE FROM admin_sessions WHERE id = ?").run(id);
    return null;
  }
  return {
    id: row.id,
    csrf: row.csrf,
    userId: row.user_id,
    role: row.role,
    email: row.email,
    name: row.name || "",
    avatarUrl: row.avatar_path
      ? `/api/auth/profile/avatar?v=${encodeURIComponent(row.avatar_path)}`
      : null,
  };
}

export function hasAdminSession(request: NextRequest) {
  return readSession(request)?.role === "admin";
}

function tooManyAttempts(ipHash: string) {
  const row = getDb()
    .prepare("SELECT COUNT(*) AS count FROM login_attempts WHERE ip_hash = ? AND at > ?")
    .get(ipHash, Date.now() - LOGIN_WINDOW_MS) as { count: number | bigint } | undefined;
  return Number(row?.count ?? 0) >= LOGIN_MAX_ATTEMPTS;
}

function recordFailure(ipHash: string) {
  const db = getDb();
  db.prepare("INSERT INTO login_attempts (ip_hash, at) VALUES (?, ?)").run(ipHash, Date.now());
  db.prepare("DELETE FROM login_attempts WHERE at < ?").run(Date.now() - 60 * 60 * 1000);
}

function tokensMatch(left: string, right: string) {
  if (!isSessionToken(left) || !isSessionToken(right)) return false;
  return timingSafeEqual(Buffer.from(left, "hex"), Buffer.from(right, "hex"));
}

export function attachCsrf(response: NextResponse, token: string) {
  response.cookies.set("wa_csrf", token, cookieBase(true, sessionTtlMs(false) / 1000));
  return response;
}

export function sessionPayload(request: NextRequest) {
  const rawSession = request.cookies.get("wa_admin")?.value ?? "";
  const session = readSession(request);
  const existing = request.cookies.get("wa_csrf")?.value ?? "";
  if (session) {
    return {
      authenticated: true,
      adminConfigured: isAdminConfigured(),
      csrfToken: session.csrf,
      email: session.email,
      name: session.name || "",
      role: session.role,
      avatarUrl: session.avatarUrl,
      setCookie: existing !== session.csrf,
      clearSessionCookie: false,
    };
  }
  const csrfToken = isSessionToken(existing) ? existing : randomBytes(32).toString("hex");
  return {
    authenticated: false,
    adminConfigured: isAdminConfigured(),
    csrfToken,
    email: null,
    name: null,
    role: null,
    avatarUrl: null,
    setCookie: csrfToken !== existing,
    /** Stale wa_admin cookie present but session row missing/expired. */
    clearSessionCookie: isSessionToken(rawSession),
  };
}

export function assertCsrf(request: NextRequest, token: string) {
  if (!sameOrigin(request)) return json({ ok: false, error: "invalid_origin" }, 403);
  const cookie = request.cookies.get("wa_csrf")?.value ?? "";
  const header = request.headers.get("x-csrf-token") ?? "";
  if (!tokensMatch(header, token) || !tokensMatch(header, cookie)) {
    return json({ ok: false, error: "invalid_csrf" }, 403);
  }
  return null;
}

export function requireFormCsrf(request: NextRequest) {
  if (!sameOrigin(request)) return json({ ok: false, error: "invalid_origin" }, 403);
  const csrf = request.cookies.get("wa_csrf")?.value ?? "";
  const header = request.headers.get("x-csrf-token") ?? "";
  if (!tokensMatch(header, csrf)) return json({ ok: false, error: "invalid_csrf" }, 403);
  return null;
}

/** Authenticated read (GET). Cookie session only — no CSRF. */
export function requireSession(request: NextRequest) {
  const session = readSession(request);
  if (!session?.userId) return { session: null, error: json({ ok: false, error: "unauthorized" }, 401) };
  return { session, error: null };
}

export function requireAdmin(request: NextRequest) {
  const session = readSession(request);
  if (!session) return { session: null, error: json({ ok: false, error: "unauthorized" }, 401) };
  const rejected = assertCsrf(request, session.csrf);
  if (rejected) return { session: null, error: rejected };
  if (session.role !== "admin") return { session: null, error: json({ ok: false, error: "forbidden" }, 403) };
  return { session, error: null };
}

/** Admin read (GET) without CSRF mutation check. */
export function requireAdminSession(request: NextRequest) {
  const session = readSession(request);
  if (!session?.userId) return { session: null, error: json({ ok: false, error: "unauthorized" }, 401) };
  if (session.role !== "admin") return { session: null, error: json({ ok: false, error: "forbidden" }, 403) };
  return { session, error: null };
}

export function requireUser(request: NextRequest) {
  const session = readSession(request);
  if (!session?.userId) return { session: null, error: json({ ok: false, error: "unauthorized" }, 401) };
  const rejected = assertCsrf(request, session.csrf);
  if (rejected) return { session: null, error: rejected };
  return { session, error: null };
}

export function login(request: NextRequest, email: string, password: string, rememberMe = false) {
  const rejected = requireFormCsrf(request);
  if (rejected) return rejected;
  if (password.length < 8 || password.length > 200) return json({ ok: false, error: "sign_in_failed" }, 401);

  const ipHash = clientHash(request);
  if (tooManyAttempts(ipHash)) return json({ ok: false, error: "sign_in_unavailable" }, 429);
  const user = findUserByLogin(email);
  if (!user || !verifyPassword(password, user.password_hash)) {
    recordFailure(ipHash);
    return json({ ok: false, error: "sign_in_failed" }, 401);
  }
  const gate = canLogin(user);
  if (!gate.ok) return json({ ok: false, error: gate.error }, 403);

  const ttl = sessionTtlMs(rememberMe);
  const id = randomBytes(32).toString("hex");
  const nextCsrf = randomBytes(32).toString("hex");
  const expiresAt = Date.now() + ttl;
  const db = getDb();
  db.prepare("DELETE FROM admin_sessions WHERE expires_at <= ?").run(Date.now());
  db.prepare("INSERT INTO admin_sessions (id, csrf, expires_at, user_id) VALUES (?, ?, ?, ?)").run(
    id,
    nextCsrf,
    expiresAt,
    user.id,
  );
  const maxAge = Math.floor(ttl / 1000);
  const response = json({
    ok: true,
    authenticated: true,
    adminConfigured: true,
    csrfToken: nextCsrf,
    email: user.email,
    name: user.name || "",
    role: user.role,
    avatarUrl: user.avatar_path
      ? `/api/auth/profile/avatar?v=${encodeURIComponent(user.avatar_path)}`
      : null,
    rememberMe: Boolean(rememberMe),
  });
  response.cookies.set("wa_admin", id, cookieBase(true, maxAge));
  response.cookies.set("wa_csrf", nextCsrf, cookieBase(true, maxAge));
  return response;
}

export function logout(request: NextRequest) {
  const session = readSession(request);
  if (session) {
    const rejected = assertCsrf(request, session.csrf);
    if (rejected) return rejected;
    getDb().prepare("DELETE FROM admin_sessions WHERE id = ?").run(session.id);
  }
  // Always clear cookies so a stale wa_admin cannot bounce login ↔ home.
  const response = json({ ok: true, authenticated: false });
  response.cookies.set("wa_admin", "", { ...cookieBase(true, 0), maxAge: 0 });
  response.cookies.set("wa_csrf", "", { ...cookieBase(true, 0), maxAge: 0 });
  return response;
}
