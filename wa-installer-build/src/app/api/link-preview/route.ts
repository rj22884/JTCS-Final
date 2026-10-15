import { requireSession } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { fetchLinkPreview } from "@/lib/link-preview";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const raw = request.nextUrl.searchParams.get("url") ?? "";
  if (!raw.trim()) return json({ error: "invalid_url", detail: "url is required." }, 400);
  const result = await fetchLinkPreview(raw.trim());
  if (!result.ok) return json({ error: "preview_failed", detail: result.detail }, result.status || 502);
  return json({ preview: result.preview });
}
