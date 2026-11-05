import { requireFormCsrf } from "@/lib/admin";
import { recoveryPublicOk } from "@/lib/auth-policy";
import { ensureRequestTime, json } from "@/lib/http";
import { clearMobileOtp, deliverMobileOtp, issueMobileOtp } from "@/lib/mobile-otp";
import { normalizeMobile } from "@/lib/phone";
import { findUserByMobileKey } from "@/lib/users";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const rejected = requireFormCsrf(request);
  if (rejected) return rejected;
  const raw = await request.text();
  if (raw.length > 1000) return json({ ok: false, error: "invalid_value" }, 400);

  let mobileRaw = "";
  try {
    const body = JSON.parse(raw) as { mobile?: unknown; email?: unknown };
    mobileRaw = typeof body.mobile === "string" ? body.mobile : typeof body.email === "string" ? body.email : "";
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid) return json({ ok: false, error: "invalid_mobile" }, 400);

  const user = findUserByMobileKey(mobile.phoneKey);
  // Always generic unless OTP can be issued for an active account.
  if (!user || user.status !== "active" || Number(user.verified) !== 1) {
    return json(recoveryPublicOk());
  }

  const issued = issueMobileOtp(mobile.digits, "reset", user.id);
  if (!issued.ok) {
    if (issued.error === "resend_cooldown") {
      return json({ ok: false, error: "resend_cooldown", retryAfterMs: issued.retryAfterMs }, 429);
    }
    return json({ ok: false, error: "sign_in_unavailable" }, 429);
  }

  const delivered = await deliverMobileOtp(mobile.digits, issued.code, "reset");
  if (!delivered.ok) {
    clearMobileOtp(mobile.digits, "reset");
    return json({ ok: false, error: delivered.error, detail: delivered.detail }, 502);
  }
  return json(recoveryPublicOk());
}
