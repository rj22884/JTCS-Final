import {
  clearApprovalNotifyFailure,
  consumeApprovalToken,
  notifyAdminsOfPendingUser,
  publicAppBaseUrl,
  readApprovalToken,
} from "@/lib/account-approval";
import { requireAdmin, requireAdminSession } from "@/lib/admin";
import { getDb } from "@/lib/db";
import { ensureRequestTime, json } from "@/lib/http";
import { approveUser, findUserById, listUsersByStatus, parseUserRole, rejectUser } from "@/lib/users";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdminSession(request);
  if (gate.error) return gate.error;

  const pending = listUsersByStatus("pending_approval").map((user) => {
    const fail = getDb()
      .prepare("SELECT last_error, failed_at, attempts FROM approval_notify_failures WHERE user_id = ?")
      .get(user.id) as { last_error: string; failed_at: string; attempts: number | bigint } | undefined;
    return {
      id: user.id,
      name: user.name,
      email: user.email,
      mobile: user.mobile,
      role: user.role,
      createdAt: user.created_at,
      notifyFailure: fail
        ? { detail: fail.last_error, failedAt: fail.failed_at, attempts: Number(fail.attempts) }
        : null,
    };
  });
  const deleted = listUsersByStatus("deleted").map((user) => ({
    id: user.id,
    name: user.name,
    email: user.email,
    mobile: user.mobile,
    role: user.role,
    deletedAt: user.deleted_at,
  }));
  const rejected = listUsersByStatus("rejected").map((user) => ({
    id: user.id,
    name: user.name,
    email: user.email,
    mobile: user.mobile,
    role: user.role,
  }));

  return json({ pending, deleted, rejected });
}

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ error: "invalid_body" }, 400);
  }

  const action = (body as { action?: unknown }).action;
  const userId = typeof (body as { userId?: unknown }).userId === "string" ? (body as { userId: string }).userId : "";
  const token = typeof (body as { token?: unknown }).token === "string" ? (body as { token: string }).token : "";
  const role = parseUserRole((body as { role?: unknown }).role);

  if (token) {
    const parsed = readApprovalToken(token);
    if (!parsed || !parsed.ok) {
      const error = parsed && "error" in parsed ? parsed.error : "invalid";
      return json({ ok: false, error: `token_${error}` }, 400);
    }
    const result =
      parsed.action === "approve"
        ? approveUser(parsed.userId, gate.session!.userId!, role)
        : rejectUser(parsed.userId, gate.session!.userId!);
    if (!result.ok) return json({ ok: false, error: result.error }, 400);
    consumeApprovalToken(parsed.id);
    clearApprovalNotifyFailure(parsed.userId);
    return json({ ok: true, action: parsed.action, user: publicUser(result.user) });
  }

  if (!userId) return json({ error: "invalid_body", detail: "userId is required." }, 400);

  if (action === "approve") {
    const result = approveUser(userId, gate.session!.userId!, role);
    if (!result.ok) return json({ ok: false, error: result.error }, 400);
    clearApprovalNotifyFailure(userId);
    return json({ ok: true, action: "approve", user: publicUser(result.user) });
  }
  if (action === "reject") {
    const result = rejectUser(userId, gate.session!.userId!);
    if (!result.ok) return json({ ok: false, error: result.error }, 400);
    clearApprovalNotifyFailure(userId);
    return json({ ok: true, action: "reject", user: publicUser(result.user) });
  }
  if (action === "retry_notify") {
    const user = findUserById(userId);
    if (!user || user.status !== "pending_approval") return json({ ok: false, error: "not_pending" }, 400);
    const notify = await notifyAdminsOfPendingUser(user, publicAppBaseUrl());
    return json({ ok: notify.ok, detail: notify.detail }, notify.ok ? 200 : 502);
  }

  return json({ error: "invalid_action" }, 400);
}

function publicUser(user: {
  id: string;
  name: string;
  email: string;
  mobile: string | null;
  status: string;
  role: string;
}) {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    mobile: user.mobile,
    status: user.status,
    role: user.role,
  };
}
