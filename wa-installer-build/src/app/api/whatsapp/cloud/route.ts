import { hasAdminSession, requireAdmin } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { cloudFieldState, saveCloudValues } from "@/lib/whatsapp/cloud-state";
import { readCloudInput } from "@/lib/whatsapp/cloud-form";
import type { NextRequest } from "next/server";

const MAX_BODY = 12_000;

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  if (!hasAdminSession(request)) return json({ ok: false, error: "unauthorized" }, 401);
  try {
    return json({ ok: true, ...cloudFieldState() });
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  const raw = await request.text();
  if (raw.length > MAX_BODY) return json({ ok: false, error: "invalid_value" }, 400);
  let payload: unknown;
  try {
    payload = JSON.parse(raw) as unknown;
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }
  const values = readCloudInput(payload && typeof payload === "object" ? (payload as { values?: unknown }).values : null);
  if (!values.ok) return json({ ok: false, error: values.error }, 400);
  try {
    const saved = saveCloudValues(values.values);
    if (!saved.ok) return json({ ok: false, error: saved.error }, 400);
    return json(saved);
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}
