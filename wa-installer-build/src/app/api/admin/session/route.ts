import { attachCsrf, login, logout, sessionPayload } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  try {
    const payload = sessionPayload(request);
    const response = json({
      authenticated: payload.authenticated,
      adminConfigured: payload.adminConfigured,
      csrfToken: payload.csrfToken,
      email: payload.email,
      role: payload.role,
    });
    if (payload.setCookie) attachCsrf(response, payload.csrfToken);
    if (payload.clearSessionCookie) {
      response.cookies.set("wa_admin", "", {
        httpOnly: true,
        sameSite: "strict",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        maxAge: 0,
      });
    }
    return response;
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const raw = await request.text();
  if (raw.length > 2000) return json({ ok: false, error: "sign_in_failed" }, 401);
  let email = "";
  let password = "";
  let rememberMe = false;
  try {
    const body = JSON.parse(raw) as { email?: unknown; password?: unknown; rememberMe?: unknown };
    email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
    password = typeof body.password === "string" ? body.password : "";
    rememberMe = body.rememberMe === true;
  } catch {
    return json({ ok: false, error: "sign_in_failed" }, 401);
  }
  try {
    return login(request, email, password, rememberMe);
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}

export async function DELETE(request: NextRequest) {
  await ensureRequestTime();
  try {
    return logout(request);
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}
