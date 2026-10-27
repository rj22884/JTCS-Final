import { requireUser } from "@/lib/admin";
import { BULK_TEMPLATE_MAX, sendBulkTemplate } from "@/lib/bulk-template";
import { ensureRequestTime, json } from "@/lib/http";
import type { NextRequest } from "next/server";

export const maxDuration = 120;

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

  const contactIds = (body as { contactIds?: unknown }).contactIds;
  const name = (body as { name?: unknown }).name;
  const language = (body as { language?: unknown }).language;

  if (!Array.isArray(contactIds) || contactIds.some((id) => typeof id !== "string")) {
    return json({ error: "invalid_contacts", detail: "contactIds must be a string array." }, 400);
  }
  if (typeof name !== "string" || typeof language !== "string") {
    return json({ error: "invalid_template", detail: "Choose an approved template." }, 400);
  }
  if (contactIds.length > BULK_TEMPLATE_MAX) {
    return json(
      {
        error: "too_many",
        detail: `Select at most ${BULK_TEMPLATE_MAX} contacts per bulk send.`,
        max: BULK_TEMPLATE_MAX,
      },
      400,
    );
  }

  const result = await sendBulkTemplate({
    contactIds,
    templateName: name,
    language,
  });

  if (!result.results.length && !result.ok) {
    return json(
      {
        error: "bulk_failed",
        detail: result.detail,
        sent: result.sent,
        failed: result.failed,
        skipped: result.skipped,
        results: result.results,
      },
      409,
    );
  }

  return json({
    ok: true,
    max: BULK_TEMPLATE_MAX,
    sent: result.sent,
    failed: result.failed,
    skipped: result.skipped,
    detail: result.detail,
    results: result.results,
  });
}
