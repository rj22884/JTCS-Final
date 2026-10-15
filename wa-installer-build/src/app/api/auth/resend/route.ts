import { requireFormCsrf } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { clearMobileOtp, deliverMobileOtp, issueMobileOtp, peekMobileOtpPayload, type MobileOtpPurpose } from "@/lib/mobile-otp";
import { normalizeMobile } from "@/lib/phone";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const rejected = requireFormCsrf(request);
  if (rejected) return rejected;
  const raw = await request.text();
  if (raw.length > 2000) return json({ ok: false, error: "invalid_value" }, 400);

  let mobileRaw = "";
  let purpose: MobileOtpPurpose = "register";
  try {
    const body = JSON.parse(raw) as { mobile?: unknown; email?: unknown; purpose?: unknown };
    mobileRaw = typeof body.mobile === "string" ? body.mobile : typeof body.email === "string" ? body.email : "";
    purpose = body.purpose === "reset" || body.purpose === "recover_id" ? body.purpose : "register";
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid) return json({ ok: false, error: "invalid_mobile" }, 400);

  const payload = peekMobileOtpPayload(mobile.digits, purpose);
  // Generic success when nothing is pending (non-enumerating).
  if (!payload && purpose !== "reset" && purpose !== "recover_id") return json({ ok: true });

  const issued = issueMobileOtp(mobile.digits, purpose, payload);
  if (!issued.ok) {
    if (issued.error === "resend_cooldown") {
      return json({ ok: false, error: "resend_cooldown", retryAfterMs: issued.retryAfterMs }, 429);
    }
    return json({ ok: false, error: "sign_in_unavailable" }, 429);
  }

  const delivered = await deliverMobileOtp(mobile.digits, issued.code, purpose);
  if (!delivered.ok) {
    clearMobileOtp(mobile.digits, purpose);
    return json({ ok: false, error: delivered.error, detail: delivered.detail }, 502);
  }
  return json({ ok: true });
}
