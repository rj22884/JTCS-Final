import "server-only";

import { getContact, contactDialDigits, type Contact } from "@/lib/contacts";
import { resolveSecret } from "@/lib/secrets";
import { listCloudTemplates, sendCloudTemplate } from "@/lib/whatsapp/client";
import { addLiveOutbound, openConversationForPhone } from "@/lib/whatsapp/inbox";
import { mailboxReady } from "@/lib/whatsapp/status";

export const BULK_TEMPLATE_MAX = 40;
/** Pause between Meta sends to stay under Cloud API throughput. */
export const BULK_TEMPLATE_GAP_MS = 600;

export type BulkTemplateResult = {
  contactId: string;
  name: string;
  mobile: string;
  conversationId: string | null;
  ok: boolean;
  detail: string;
};

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function activeContact(id: string): Contact | null {
  const contact = getContact(id);
  if (!contact || contact.deletedAt) return null;
  return contact;
}

export async function sendBulkTemplate(input: {
  contactIds: string[];
  templateName: string;
  language: string;
}): Promise<{
  ok: boolean;
  sent: number;
  failed: number;
  skipped: number;
  results: BulkTemplateResult[];
  detail: string;
}> {
  const templateName = input.templateName.trim();
  const language = input.language.trim();
  const ids = [...new Set(input.contactIds.map((id) => id.trim()).filter(Boolean))];

  if (!templateName || !language) {
    return {
      ok: false,
      sent: 0,
      failed: 0,
      skipped: 0,
      results: [],
      detail: "Choose an approved template.",
    };
  }
  if (!ids.length) {
    return { ok: false, sent: 0, failed: 0, skipped: 0, results: [], detail: "Select at least one contact." };
  }
  if (ids.length > BULK_TEMPLATE_MAX) {
    return {
      ok: false,
      sent: 0,
      failed: 0,
      skipped: 0,
      results: [],
      detail: `Select at most ${BULK_TEMPLATE_MAX} contacts per bulk send.`,
    };
  }
  if (!mailboxReady()) {
    return {
      ok: false,
      sent: 0,
      failed: 0,
      skipped: 0,
      results: [],
      detail: "WhatsApp Cloud API is not connected.",
    };
  }

  const phoneNumberId = resolveSecret("phoneNumberId");
  const accessToken = resolveSecret("accessToken");
  if (!phoneNumberId || !accessToken) {
    return {
      ok: false,
      sent: 0,
      failed: 0,
      skipped: 0,
      results: [],
      detail: "Phone number ID or access token is missing.",
    };
  }

  const graphApiVersion = resolveSecret("graphApiVersion");
  const businessAccountId = resolveSecret("businessAccountId");
  let templatePreview = `Template: ${templateName}`;
  if (businessAccountId) {
    const listed = await listCloudTemplates({
      businessAccountId,
      accessToken,
      graphApiVersion,
    });
    if (listed.ok) {
      const match = listed.templates.find(
        (item) => item.name === templateName && item.language === language,
      );
      if (match?.preview) templatePreview = match.preview;
    }
  }
  const results: BulkTemplateResult[] = [];
  let sent = 0;
  let failed = 0;
  let skipped = 0;
  let first = true;

  for (const contactId of ids) {
    if (!first) await sleep(BULK_TEMPLATE_GAP_MS);
    first = false;

    const contact = activeContact(contactId);
    if (!contact) {
      skipped += 1;
      results.push({
        contactId,
        name: "",
        mobile: "",
        conversationId: null,
        ok: false,
        detail: "Contact missing or deleted.",
      });
      continue;
    }

    const phone = contactDialDigits(contact);
    const display = contact.displayMobile || `+${phone}`;
    const opened = openConversationForPhone(phone, contact.name);
    if (!opened) {
      failed += 1;
      results.push({
        contactId,
        name: contact.name,
        mobile: display,
        conversationId: null,
        ok: false,
        detail: "Could not open chat for this mobile.",
      });
      continue;
    }

    const result = await sendCloudTemplate({
      to: opened.detail.phone,
      phoneNumberId,
      accessToken,
      graphApiVersion,
      name: templateName,
      language,
      preview: templatePreview,
    });

    addLiveOutbound(
      opened.id,
      result.ok ? result.body : templatePreview,
      result.ok ? result.messageId : null,
      result.ok ? "sent" : "failed",
      { kind: "template" },
    );

    if (result.ok) {
      sent += 1;
      results.push({
        contactId,
        name: contact.name,
        mobile: display,
        conversationId: opened.id,
        ok: true,
        detail: "Meta accepted the message.",
      });
    } else {
      failed += 1;
      results.push({
        contactId,
        name: contact.name,
        mobile: display,
        conversationId: opened.id,
        ok: false,
        detail: result.detail || "Send failed.",
      });
    }
  }

  return {
    ok: failed === 0 && skipped === 0 && sent > 0,
    sent,
    failed,
    skipped,
    results,
    detail: `Sent ${sent}, failed ${failed}${skipped ? `, skipped ${skipped}` : ""}.`,
  };
}
