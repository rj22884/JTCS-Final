import { requireSession, requireUser } from "@/lib/admin";
import { deleteContact, getContact, updateContact } from "@/lib/contacts";
import { ensureRequestTime, json } from "@/lib/http";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  const contact = getContact(id);
  if (!contact) return json({ error: "not_found" }, 404);
  return json({ contact });
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;

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
  const mobile = (body as { mobile?: unknown }).mobile;
  const countryCode = (body as { countryCode?: unknown }).countryCode;
  const notes = (body as { notes?: unknown }).notes;
  const labels = (body as { labels?: unknown }).labels;
  if (typeof name !== "string" || typeof mobile !== "string") {
    return json({ error: "invalid_body", detail: "Name and mobile are required." }, 400);
  }
  const result = updateContact(id, {
    name,
    mobile,
    countryCode: typeof countryCode === "string" ? countryCode : undefined,
    notes: typeof notes === "string" ? notes : undefined,
    labels: Array.isArray(labels) ? (labels as never) : undefined,
  });
  if (!result.ok) {
    const status =
      result.error === "not_found"
        ? 404
        : result.error === "duplicate_mobile" || result.error === "deleted"
          ? 409
          : 400;
    return json({ error: result.error, detail: result.detail }, status);
  }
  return json({ ok: true, contact: result.contact });
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  const result = deleteContact(id);
  if (!result.ok) {
    const status = result.error === "not_found" ? 404 : result.error === "already_deleted" ? 409 : 400;
    return json({ error: result.error, detail: result.detail }, status);
  }
  return json({ ok: true, contact: result.contact, softDeleted: true });
}
