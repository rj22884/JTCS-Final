import { requireSession, requireUser } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { hashPassword, isAcceptablePassword, verifyPassword } from "@/lib/passwords";
import {
  findUserById,
  publicProfile,
  updatePassword,
  updateProfileName,
} from "@/lib/users";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const user = findUserById(gate.session!.userId!);
  if (!user) return json({ error: "not_found" }, 404);
  return json({ profile: publicProfile(user) });
}

export async function PATCH(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const user = findUserById(gate.session!.userId!);
  if (!user) return json({ error: "not_found" }, 404);

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ error: "invalid_body" }, 400);
  }

  const name = (body as { name?: unknown }).name;
  const currentPassword = (body as { currentPassword?: unknown }).currentPassword;
  const nextPassword = (body as { nextPassword?: unknown }).nextPassword;

  if (typeof name === "string") {
    const renamed = updateProfileName(user.id, name);
    if (!renamed.ok) return json({ error: renamed.error, detail: renamed.detail }, 400);
  }

  const changingPassword = typeof nextPassword === "string" && nextPassword.length > 0;
  if (changingPassword) {
    if (typeof currentPassword !== "string" || !currentPassword) {
      return json({ error: "invalid_value", detail: "Current password is required to set a new password." }, 400);
    }
    if (!isAcceptablePassword(nextPassword)) {
      return json({ error: "invalid_value", detail: "New password must be at least 8 characters." }, 400);
    }
    if (!verifyPassword(currentPassword, user.password_hash)) {
      return json({ error: "sign_in_failed", detail: "Current password is incorrect." }, 401);
    }
    updatePassword(user.id, hashPassword(nextPassword), gate.session!.id);
  }

  const fresh = findUserById(user.id)!;
  return json({
    ok: true,
    profile: publicProfile(fresh),
    detail: changingPassword ? "Profile and password saved." : "Profile saved.",
  });
}
