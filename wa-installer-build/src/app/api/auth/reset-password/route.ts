import { requireFormCsrf } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { consumeMobileOtp } from "@/lib/mobile-otp";
import { hashPassword, isAcceptablePassword } from "@/lib/passwords";
import { normalizeMobile } from "@/lib/phone";
import { findUserById, updatePassword } from "@/lib/users";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const rejected = requireFormCsrf(request);
  if (rejected) return rejected;
  const raw = await request.text();
  if (raw.length > 2000) return json({ ok: false, error: "invalid_value" }, 400);

  let mobileRaw = "";
  let code = "";
  let password = "";
  try {
    const body = JSON.parse(raw) as { mobile?: unknown; email?: unknown; code?: unknown; password?: unknown };
    mobileRaw = typeof body.mobile === "string" ? body.mobile : typeof body.email === "string" ? body.email : "";
    code = typeof body.code === "string" ? body.code.trim() : "";
    password = typeof body.password === "string" ? body.password : "";
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid || !/^\d{6}$/.test(code) || !isAcceptablePassword(password)) {
    return json({ ok: false, error: "invalid_value" }, 400);
  }

  try {
    const match = consumeMobileOtp(mobile.digits, "reset", code);
    if (!match?.payload) return json({ ok: false, error: "invalid_code" }, 400);
    const user = findUserById(match.payload);
    if (!user || user.status !== "active") return json({ ok: false, error: "invalid_code" }, 400);
    updatePassword(user.id, hashPassword(password));
    return json({ ok: true });
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}