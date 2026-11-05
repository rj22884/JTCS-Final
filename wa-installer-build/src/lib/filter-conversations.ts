import { groupSortRank, isLabel } from "@/lib/labels";
import type { ConversationFilter, ConversationSummary } from "@/lib/types";

export function isMuted(mutedUntil: string | null | undefined, now = Date.now()) {
  if (!mutedUntil) return false;
  if (mutedUntil === "always") return true;
  const stamp = Date.parse(mutedUntil);
  return Number.isFinite(stamp) && stamp > now;
}

/** Pass `null` for no status/archive chip — return the full mailbox (incl. archived). */
export function filterSummaries(
  items: ConversationSummary[],
  query: string,
  filter: ConversationFilter | null,
) {
  const text = query.trim().toLowerCase();
  const digits = text.replace(/\D/g, "");

  return items.filter((item) => {
    const archived = Boolean(item.archived);
    if (filter === "archived") {
      if (!archived) return false;
    } else if (filter !== null && archived) {
      // Chip filters (all / unread / status / groups) hide archived; null keeps them for the client.
      return false;
    }
    if (filter === "unread" && item.unreadCount === 0) return false;
    if (
      (filter === "open" || filter === "pending" || filter === "resolved") &&
      item.status !== filter
    ) {
      return false;
    }
    if (filter && isLabel(filter) && !item.labels.includes(filter)) return false;
    if (!text) return true;

    const haystack = [item.name, item.phone, item.lastMessage, item.assignee, ...item.labels]
      .join(" ")
      .toLowerCase();
    if (haystack.includes(text)) return true;
    return digits.length >= 3 && item.phone.replace(/\D/g, "").includes(digits);
  });
}

export function sortSummaries(items: ConversationSummary[]) {
  return [...items].sort((left, right) => {
    const pin = Number(Boolean(right.pinned)) - Number(Boolean(left.pinned));
    if (pin !== 0) return pin;
    const group = groupSortRank(left.labels) - groupSortRank(right.labels);
    if (group !== 0) return group;
    return new Date(right.lastMessageAt).getTime() - new Date(left.lastMessageAt).getTime();
  });
}
