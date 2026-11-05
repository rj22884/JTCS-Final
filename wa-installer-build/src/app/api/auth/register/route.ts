import { requireFormCsrf } from "@/lib/admin";
import { registrationPublicOk } from "@/lib/auth-policy";
import { ensureRequestTime, json } from "@/lib/http";
import { clearMobileOtp, deliverMobileOtp, issueMobileOtp } from "@/lib/mobile-otp";
import { hashPassword, isAcceptablePassword, isEmail, normalizeEmail } from "@/lib/passwords";
import { normalizeMobile } from "@/lib/phone";
import { findDeletedConflict, findLiveConflict, parseUserRole } from "@/lib/users";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const rejected = requireFormCsrf(request);
  if (rejected) return rejected;
  const raw = await request.text();
  if (raw.length > 4000) return json({ ok: false, error: "invalid_value" }, 400);

  let name = "";
  let email = "";
  let mobileRaw = "";
  let password = "";
  let roleRaw: unknown;
  try {
    const body = JSON.parse(raw) as {
      name?: unknown;
      email?: unknown;
      mobile?: unknown;
      password?: unknown;
      role?: unknown;
    };
    name = typeof body.name === "string" ? body.name.trim() : "";
    email = typeof body.email === "string" ? normalizeEmail(body.email) : "";
    mobileRaw = typeof body.mobile === "string" ? body.mobile : "";
    password = typeof body.password === "string" ? body.password : "";
    roleRaw = body.role;
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }
  const role = parseUserRole(roleRaw) ?? "member";

  if (!name || name.length > 200) return json({ ok: false, error: "invalid_value", detail: "Name is required." }, 400);
  if (!isEmail(email) || !isAcceptablePassword(password)) {
    return json({ ok: false, error: "invalid_value", detail: "Check email and use a password of at least 8 characters." }, 400);
  }
  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid) return json({ ok: false, error: "invalid_mobile", detail: mobile.reason }, 400);

  const deleted = findDeletedConflict(email, mobile.phoneKey);
  if (deleted) {
    return json(
      {
        ok: false,
        error: "deleted_account_exists",
        detail:
          "A deleted account already uses this mobile or email. An admin must permanently remove that account before you can register again.",
      },
      409,
    );
  }

  const live = findLiveConflict(email, mobile.phoneKey);
  // Non-enumerating success when an active/pending account already exists.
  if (live) return json({ ...registrationPublicOk(), next: "verify" });

  const payload = JSON.stringify({
    name,
    email,
    mobile: mobile.digits,
    mobileKey: mobile.phoneKey,
    passwordHash: hashPassword(password),
    role,
  });

  const issued = issueMobileOtp(mobile.digits, "register", payload);
  if (!issued.ok) {
    if (issued.error === "resend_cooldown") {
      return json({ ok: false, error: "resend_cooldown", retryAfterMs: issued.retryAfterMs }, 429);
    }
    if (issued.error === "invalid_mobile") {
      return json({ ok: false, error: "invalid_mobile", detail: issued.detail }, 400);
    }
    return json({ ok: false, error: "sign_in_unavailable" }, 429);
  }

  const delivered = await deliverMobileOtp(mobile.digits, issued.code, "register");
  if (!delivered.ok) {
    clearMobileOtp(mobile.digits, "register");
    return json({ ok: false, error: delivered.error, detail: delivered.detail }, 502);
  }

  return json({ ...registrationPublicOk(), next: "verify", mobile: mobile.display });
}
