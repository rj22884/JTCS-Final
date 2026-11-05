import { requireSession, requireUser } from "@/lib/admin";
import { createContact, findContactByPhoneKey, listContacts } from "@/lib/contacts";
import { ensureRequestTime, json } from "@/lib/http";
import { normalizeMobile } from "@/lib/phone";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const phone = request.nextUrl.searchParams.get("phone") ?? "";
  if (phone.trim()) {
    const normalized = normalizeMobile(phone);
    if (!normalized.valid) return json({ contact: null, saved: false });
    const contact = findContactByPhoneKey(normalized.phoneKey);
    const active = contact && !contact.deletedAt ? contact : null;
    return json({ contact: active, saved: Boolean(active) });
  }
  const q = request.nextUrl.searchParams.get("q") ?? "";
  return json({ contacts: listContacts(q) });
}

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireUser(request);
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
  const name = (body as { name?: unknown }).name;
  const mobile = (body as { mobile?: unknown }).mobile;
  const countryCode = (body as { countryCode?: unknown }).countryCode;
  const notes = (body as { notes?: unknown }).notes;
  const labels = (body as { labels?: unknown }).labels;
  if (typeof name !== "string" || typeof mobile !== "string") {
    return json({ error: "invalid_body", detail: "Name and mobile are required." }, 400);
  }
  const result = createContact({
    name,
    mobile,
    countryCode: typeof countryCode === "string" ? countryCode : undefined,
    notes: typeof notes === "string" ? notes : "",
    labels: Array.isArray(labels) ? (labels as never) : undefined,
  });
  if (!result.ok) {
    const status = result.error === "duplicate_mobile" ? 409 : 400;
    return json({ error: result.error, detail: result.detail }, status);
  }
  return json({ ok: true, contact: result.contact });
}
