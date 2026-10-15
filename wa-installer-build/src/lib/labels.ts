import { LABELS, type Label } from "@/lib/types";

const SERVICE_GROUPS = ["GST", "TDS", "DSC", "ITR"] as const;

export function isLabel(value: string): value is Label {
  return (LABELS as readonly string[]).includes(value);
}

/** Misc is exclusive with GST/TDS/DSC/ITR. Returns Hindi/English guidance for a popup. */
export function labelSelectionError(next: readonly string[]): string | null {
  const labels = next.filter(isLabel);
  const hasMisc = labels.includes("Misc");
  const services = labels.filter((label) => label !== "Misc");
  if (hasMisc && services.length > 0) {
    return [
      "Yeh grouping select nahi ho sakti.",
      "",
      "Misc ke saath GST, TDS, DSC, ya ITR nahi chalegi.",
      "",
      "Kya tick karein:",
      "• Sirf Misc — miscellaneous contacts ke liye",
      "• Ya GST / TDS / DSC / ITR mein se ek ya zyada (Misc ke bina)",
    ].join("\n");
  }
  return null;
}

export function normalizeLabelList(values: unknown): Label[] {
  if (!Array.isArray(values)) return [];
  const next: Label[] = [];
  for (const value of values) {
    if (typeof value !== "string" || !isLabel(value)) continue;
    if (!next.includes(value)) next.push(value);
  }
  // Legacy / bad rows: prefer service groups over Misc when both present.
  if (next.includes("Misc") && next.some((label) => label !== "Misc")) {
    return next.filter((label) => label !== "Misc");
  }
  return next;
}

export function sanitizeLabels(values: unknown): { ok: true; labels: Label[] } | { ok: false; error: string } {
  if (!Array.isArray(values) || values.length > LABELS.length) {
    return { ok: false, error: "Invalid grouping." };
  }
  const next: Label[] = [];
  for (const value of values) {
    if (typeof value !== "string" || !isLabel(value)) {
      return { ok: false, error: "Invalid grouping." };
    }
    if (!next.includes(value)) next.push(value);
  }
  const conflict = labelSelectionError(next);
  if (conflict) return { ok: false, error: conflict };
  return { ok: true, labels: next };
}

/** Lower rank sorts first: GST → TDS → DSC → ITR → Misc → ungrouped. */
export function groupSortRank(labels: readonly Label[]): number {
  for (let index = 0; index < LABELS.length; index += 1) {
    if (labels.includes(LABELS[index]!)) return index;
  }
  return LABELS.length;
}

export function toggleLabel(current: readonly Label[], label: Label): { ok: true; labels: Label[] } | { ok: false; error: string } {
  const next = current.includes(label) ? current.filter((item) => item !== label) : [...current, label];
  return sanitizeLabels(next);
}

export { SERVICE_GROUPS };
