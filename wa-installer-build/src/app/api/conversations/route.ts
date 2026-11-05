import { requireSession } from "@/lib/admin";
import { filterSummaries, sortSummaries } from "@/lib/filter-conversations";
import { ensureRequestTime, json } from "@/lib/http";
import { listConversations } from "@/lib/store";
import { listLiveConversations } from "@/lib/whatsapp/inbox";
import { mailboxReady } from "@/lib/whatsapp/status";
import { FILTERS, type ConversationFilter } from "@/lib/types";
import type { NextRequest } from "next/server";

function isFilter(value: string | null): value is ConversationFilter {
  return FILTERS.some((filter) => filter.id === value);
}

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  try {
    // Omit `filter` so Inbox gets the full mailbox (incl. archived). Client chips
    // call filterSummaries; defaulting to "all" here stripped archives on every poll.
    const filterParam = request.nextUrl.searchParams.get("filter");
    const filter = isFilter(filterParam) ? filterParam : null;
    const query = request.nextUrl.searchParams.get("q") ?? "";
    const live = mailboxReady();
    const source = live ? listLiveConversations() : sortSummaries(listConversations());
    const conversations = filterSummaries(source, query, filter);
    return json({ conversations, demo: !live });
  } catch {
    return json({ ok: false, error: "storage_unavailable", detail: "Could not read conversations." }, 500);
  }
}
