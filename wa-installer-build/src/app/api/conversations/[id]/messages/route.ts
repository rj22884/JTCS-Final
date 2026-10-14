import { requireUser } from "@/lib/admin";
import { sendCloudContact, sendCloudLocation, sendCloudText, sendWhatsAppText } from "@/lib/whatsapp/client";
import { ensureRequestTime, json } from "@/lib/http";
import { resolveSecret } from "@/lib/secrets";
import { addLiveOutbound, getLiveConversation } from "@/lib/whatsapp/inbox";
import { mailboxReady } from "@/lib/whatsapp/status";
import { addDemoMessage, getConversation, toSummary } from "@/lib/store";
import type { NextRequest } from "next/server";

const MESSAGE_LIMIT = 4096;

function rejectIfBlocked(conversation: { blocked?: boolean } | null) {
  if (conversation?.blocked) {
    return json({ error: "blocked", detail: "This contact is blocked. Unblock to send messages." }, 403);
  }
  return null;
}

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
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

  const record = body as {
    body?: unknown;
    replyToMessageId?: unknown;
    kind?: unknown;
    location?: unknown;
    contact?: unknown;
  };
  const kind = record.kind === "location" || record.kind === "contact" ? record.kind : "text";
  const replyTo = typeof record.replyToMessageId === "string" ? record.replyToMessageId.trim() : "";

  if (kind === "location") {
    const location = record.location;
    if (!location || typeof location !== "object" || Array.isArray(location)) {
      return json({ error: "invalid_location", detail: "Latitude and longitude are required." }, 400);
    }
    const latitude = Number((location as { latitude?: unknown }).latitude);
    const longitude = Number((location as { longitude?: unknown }).longitude);
    const name =
      typeof (location as { name?: unknown }).name === "string" ? (location as { name: string }).name : "";
    const address =
      typeof (location as { address?: unknown }).address === "string"
        ? (location as { address: string }).address
        : "";
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      return json({ error: "invalid_location", detail: "Latitude and longitude are required." }, 400);
    }
    if (!mailboxReady()) {
      return json({ error: "not_connected", detail: "Location needs a connected WhatsApp Business account." }, 409);
    }
    const conversation = getLiveConversation(id);
    if (!conversation) return json({ error: "not_found" }, 404);
    const blocked = rejectIfBlocked(conversation);
    if (blocked) return blocked;
    const phoneNumberId = resolveSecret("phoneNumberId");
    const accessToken = resolveSecret("accessToken");
    if (!phoneNumberId || !accessToken) {
      return json({ error: "not_connected", detail: "The phone number is not ready. Nothing was sent." }, 409);
    }
    const result = await sendCloudLocation({
      to: conversation.phone,
      phoneNumberId,
      accessToken,
      graphApiVersion: resolveSecret("graphApiVersion"),
      latitude,
      longitude,
      name,
      address,
    });
    const preview =
      result.ok && result.body
        ? result.body
        : `📍 ${name || address || `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`}`;
    const saved = addLiveOutbound(
      id,
      preview,
      result.ok ? result.messageId : null,
      result.ok ? "sent" : "failed",
      result.ok ? { kind: "location" } : { kind: "location", deliveryError: result.detail },
    );
    if (!saved) return json({ error: "not_found" }, 404);
    return json({
      demo: false,
      delivery: result.ok ? "sent" : "failed",
      detail: result.ok ? "Meta accepted the message." : result.detail,
      message: saved.message,
      conversation: saved.detail,
      summary: saved.summary,
    });
  }

  if (kind === "contact") {
    const contact = record.contact;
    if (!contact || typeof contact !== "object" || Array.isArray(contact)) {
      return json({ error: "invalid_contact", detail: "Name and phone are required." }, 400);
    }
    const name = typeof (contact as { name?: unknown }).name === "string" ? (contact as { name: string }).name.trim() : "";
    const phone =
      typeof (contact as { phone?: unknown }).phone === "string" ? (contact as { phone: string }).phone.trim() : "";
    if (!name || !phone) {
      return json({ error: "invalid_contact", detail: "Name and phone are required." }, 400);
    }
    if (!mailboxReady()) {
      return json({ error: "not_connected", detail: "Contact cards need a connected WhatsApp Business account." }, 409);
    }
    const conversation = getLiveConversation(id);
    if (!conversation) return json({ error: "not_found" }, 404);
    const blocked = rejectIfBlocked(conversation);
    if (blocked) return blocked;
    const phoneNumberId = resolveSecret("phoneNumberId");
    const accessToken = resolveSecret("accessToken");
    if (!phoneNumberId || !accessToken) {
      return json({ error: "not_connected", detail: "The phone number is not ready. Nothing was sent." }, 409);
    }
    const result = await sendCloudContact({
      to: conversation.phone,
      phoneNumberId,
      accessToken,
      graphApiVersion: resolveSecret("graphApiVersion"),
      name,
      phone,
    });
    const preview = result.ok && result.body ? result.body : `👤 ${name} · ${phone}`;
    const saved = addLiveOutbound(
      id,
      preview,
      result.ok ? result.messageId : null,
      result.ok ? "sent" : "failed",
      result.ok ? { kind: "contact" } : { kind: "contact", deliveryError: result.detail },
    );
    if (!saved) return json({ error: "not_found" }, 404);
    return json({
      demo: false,
      delivery: result.ok ? "sent" : "failed",
      detail: result.ok ? "Meta accepted the message." : result.detail,
      message: saved.message,
      conversation: saved.detail,
      summary: saved.summary,
    });
  }

  const text = record.body;
  if (typeof text !== "string") return json({ error: "invalid_message" }, 400);
  const trimmed = text.trim();
  if (!trimmed || trimmed.length > MESSAGE_LIMIT) return json({ error: "invalid_message" }, 400);

  if (mailboxReady()) {
    const conversation = getLiveConversation(id);
    if (!conversation) return json({ error: "not_found" }, 404);
    const blocked = rejectIfBlocked(conversation);
    if (blocked) return blocked;
    const phoneNumberId = resolveSecret("phoneNumberId");
    const accessToken = resolveSecret("accessToken");
    if (!phoneNumberId || !accessToken) {
      return json({ error: "not_connected", detail: "The phone number is not ready. Nothing was sent." }, 409);
    }
    const result = await sendCloudText({
      to: conversation.phone,
      body: trimmed,
      phoneNumberId,
      accessToken,
      graphApiVersion: resolveSecret("graphApiVersion"),
      replyToMessageId: replyTo || null,
    });
    const saved = addLiveOutbound(
      id,
      trimmed,
      result.ok ? result.messageId : null,
      result.ok ? "sent" : "failed",
      result.ok ? {} : { deliveryError: result.detail },
    );
    if (!saved) return json({ error: "not_found" }, 404);
    return json({
      demo: false,
      delivery: result.ok ? "sent" : "failed",
      detail: result.ok ? "Meta accepted the message." : result.detail,
      message: saved.message,
      conversation: saved.detail,
      summary: saved.summary,
    });
  }

  const conversation = getConversation(id);
  if (!conversation) return json({ error: "not_found" }, 404);
  const blocked = rejectIfBlocked(conversation);
  if (blocked) return blocked;
  const sendResult = await sendWhatsAppText({ to: conversation.phone, body: trimmed });
  const saved = addDemoMessage(id, trimmed);
  if (!saved) return json({ error: "not_found" }, 404);
  const updated = getConversation(id);
  if (!updated) return json({ error: "not_found" }, 404);

  return json({
    demo: true,
    delivery: "not_sent" as const,
    detail: sendResult.detail,
    send: sendResult,
    message: saved.message,
    conversation: saved.detail,
    summary: toSummary(updated),
  });
}
