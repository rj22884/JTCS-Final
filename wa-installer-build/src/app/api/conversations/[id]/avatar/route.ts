import { requireSession, requireUser } from "@/lib/admin";
import { clearContactAvatar, readContactAvatar, saveContactAvatar } from "@/lib/contact-avatars";
import { ensureRequestTime, json } from "@/lib/http";
import { getLiveConversation } from "@/lib/whatsapp/inbox";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  if (!getLiveConversation(id)) return json({ error: "not_found" }, 404);
  const avatar = readContactAvatar(id);
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

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  if (!getLiveConversation(id)) return json({ error: "not_found" }, 404);

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
  const saved = saveContactAvatar(id, bytes, file.type || "application/octet-stream");
  if (!saved.ok) return json({ error: saved.error, detail: saved.detail }, 400);
  const conversation = getLiveConversation(id);
  return json({ ok: true, conversation, detail: "Contact photo saved." });
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  if (!getLiveConversation(id)) return json({ error: "not_found" }, 404);
  clearContactAvatar(id);
  const conversation = getLiveConversation(id);
  return json({ ok: true, conversation, detail: "Contact photo removed." });
}
