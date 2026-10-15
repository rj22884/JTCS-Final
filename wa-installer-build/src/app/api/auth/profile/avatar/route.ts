import { requireSession, requireUser } from "@/lib/admin";
import { clearUserAvatar, readUserAvatar, saveUserAvatar } from "@/lib/avatars";
import { ensureRequestTime, json } from "@/lib/http";
import { findUserById, publicProfile } from "@/lib/users";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const avatar = readUserAvatar(gate.session!.userId!);
  if (!avatar) return json({ error: "not_found" }, 404);
  return new Response(avatar.bytes, {
    status: 200,
    headers: {
      "Content-Type": avatar.mimeType,
      "Cache-Control": "private, max-age=300",
      "Content-Disposition": "inline",
    },
  });
}

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return json({ error: "invalid_body", detail: "Expected multipart form data." }, 400);
  }
  const file = form.get("photo");
  if (!(file instanceof File)) {
    return json({ error: "invalid_body", detail: "photo file is required." }, 400);
  }
  const bytes = Buffer.from(await file.arrayBuffer());
  const mime = file.type || "application/octet-stream";
  const saved = saveUserAvatar(gate.session!.userId!, bytes, mime);
  if (!saved.ok) return json({ error: saved.error, detail: saved.detail }, 400);
  const user = findUserById(gate.session!.userId!)!;
  return json({ ok: true, profile: publicProfile(user), detail: "Photo saved." });
}

export async function DELETE(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  clearUserAvatar(gate.session!.userId!);
  const user = findUserById(gate.session!.userId!)!;
  return json({ ok: true, profile: publicProfile(user), detail: "Photo removed." });
}
