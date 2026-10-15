import { notifyAdminsOfPendingUser, publicAppBaseUrl } from "@/lib/account-approval";
import { requireFormCsrf } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { consumeMobileOtp } from "@/lib/mobile-otp";
import { normalizeMobile } from "@/lib/phone";
import { createPendingUser, findDeletedConflict, findLiveConflict, type RegisterPayload } from "@/lib/users";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const rejected = requireFormCsrf(request);
  if (rejected) return rejected;
  const raw = await request.text();
  if (raw.length > 2000) return json({ ok: false, error: "invalid_value" }, 400);

  let mobileRaw = "";
  let code = "";
  try {
    const body = JSON.parse(raw) as { mobile?: unknown; code?: unknown; email?: unknown };
    mobileRaw = typeof body.mobile === "string" ? body.mobile : typeof body.email === "string" ? body.email : "";
    code = typeof body.code === "string" ? body.code.trim() : "";
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid || !/^\d{6}$/.test(code)) return json({ ok: false, error: "invalid_code" }, 400);

  const match = consumeMobileOtp(mobile.digits, "register", code);
  if (!match?.payload) return json({ ok: false, error: "invalid_code" }, 400);

  let payload: RegisterPayload;
  try {
    payload = JSON.parse(match.payload) as RegisterPayload;
  } catch {
    return json({ ok: false, error: "invalid_code" }, 400);
  }
  if (!payload?.email || !payload.passwordHash || !payload.mobileKey || !payload.name) {
    return json({ ok: false, error: "invalid_code" }, 400);
  }
  if (payload.role && payload.role !== "admin" && payload.role !== "member") {
    return json({ ok: false, error: "invalid_code" }, 400);
  }

  if (findDeletedConflict(payload.email, payload.mobileKey)) {
    return json(
      {
        ok: false,
        error: "deleted_account_exists",
        detail: "A deleted account blocks registration. Ask an admin to permanently remove it first.",
      },
      409,
    );
  }
  if (findLiveConflict(payload.email, payload.mobileKey)) {
    return json({ ok: true, status: "pending_approval", detail: "If registration can continue, it is awaiting admin approval." });
  }

  try {
    const user = createPendingUser(payload);
    const notify = await notifyAdminsOfPendingUser(user, publicAppBaseUrl());
    return json({
      ok: true,
      status: "pending_approval",
      detail: notify.ok
        ? "Mobile verified. Your account is pending admin approval via WhatsApp."
        : "Mobile verified. Your account is pending approval. Admin notification could not be sent yet; an admin can retry from Approvals.",
      notifyOk: notify.ok,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (/UNIQUE/i.test(message)) {
      return json({ ok: true, status: "pending_approval" });
    }
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}
