import { requireFormCsrf } from "@/lib/admin";
import { recoveryPublicOk } from "@/lib/auth-policy";
import { ensureRequestTime, json } from "@/lib/http";
import { clearMobileOtp, consumeMobileOtp, deliverMobileOtp, issueMobileOtp } from "@/lib/mobile-otp";
import { normalizeMobile } from "@/lib/phone";
import { findUserById, findUserByMobileKey } from "@/lib/users";
import type { NextRequest } from "next/server";

/** Step 1: send OTP. Step 2: with code, return email only after OTP verifies (still careful). */
export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const rejected = requireFormCsrf(request);
  if (rejected) return rejected;
  const raw = await request.text();
  if (raw.length > 2000) return json({ ok: false, error: "invalid_value" }, 400);

  let mobileRaw = "";
  let code = "";
  try {
    const body = JSON.parse(raw) as { mobile?: unknown; email?: unknown; code?: unknown };
    mobileRaw = typeof body.mobile === "string" ? body.mobile : typeof body.email === "string" ? body.email : "";
    code = typeof body.code === "string" ? body.code.trim() : "";
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid) return json({ ok: false, error: "invalid_mobile" }, 400);

  if (code) {
    const match = consumeMobileOtp(mobile.digits, "recover_id", code);
    if (!match?.payload) return json({ ok: false, error: "invalid_code" }, 400);
    const user = findUserById(match.payload);
    if (!user || user.status !== "active") return json({ ok: false, error: "invalid_code" }, 400);
    return json({ ok: true, email: user.email });
  }

  const user = findUserByMobileKey(mobile.phoneKey);
  if (!user || user.status !== "active" || Number(user.verified) !== 1) {
    return json(recoveryPublicOk());
  }

  const issued = issueMobileOtp(mobile.digits, "recover_id", user.id);
  if (!issued.ok) {
    if (issued.error === "resend_cooldown") {
      return json({ ok: false, error: "resend_cooldown", retryAfterMs: issued.retryAfterMs }, 429);
    }
    return json({ ok: false, error: "sign_in_unavailable" }, 429);
  }
  const delivered = await deliverMobileOtp(mobile.digits, issued.code, "recover_id");
  if (!delivered.ok) {
    clearMobileOtp(mobile.digits, "recover_id");
    return json({ ok: false, error: delivered.error, detail: delivered.detail }, 502);
  }
  return json({ ...recoveryPublicOk(), next: "verify" });
}
