/** WhatsApp Cloud API text formatting markers (sendable). Font/size/color are composer-local only. */

export const WA_TEXT_STYLES = ["bold", "italic", "strike", "mono"] as const;
export type WaTextStyle = (typeof WA_TEXT_STYLES)[number];

const MARKERS: Record<WaTextStyle, { open: string; close: string }> = {
  bold: { open: "*", close: "*" },
  italic: { open: "_", close: "_" },
  strike: { open: "~", close: "~" },
  mono: { open: "```", close: "```" },
};

export const COMPOSER_APPEARANCE = {
  fontFamily: {
    label: "Font",
    supported: true as const,
    delivery: "composer_only" as const,
    reason: "Shown while you type. WhatsApp Cloud API does not deliver custom fonts to the recipient.",
    options: [
      { value: "default", label: "Default", css: "inherit" },
      { value: "poppins", label: "Poppins", css: "var(--font-ui-body), Poppins, sans-serif" },
      { value: "sen", label: "Sen", css: "var(--font-ui-display), Sen, sans-serif" },
      { value: "georgia", label: "Georgia", css: "Georgia, serif" },
      { value: "mono", label: "Monospace", css: "ui-monospace, Consolas, monospace" },
    ],
  },
  fontSize: {
    label: "Size",
    supported: true as const,
    delivery: "composer_only" as const,
    reason: "Shown while you type. WhatsApp Cloud API does not deliver custom sizes to the recipient.",
    options: [
      { value: "sm", label: "Small", css: "13px" },
      { value: "default", label: "Default", css: "14.5px" },
      { value: "md", label: "Medium", css: "16px" },
      { value: "lg", label: "Large", css: "18px" },
      { value: "xl", label: "Extra large", css: "20px" },
    ],
  },
  textColor: {
    label: "Color",
    supported: true as const,
    delivery: "composer_only" as const,
    reason: "Shown while you type. WhatsApp Cloud API does not deliver custom colors to the recipient.",
    options: [
      { value: "default", label: "Default", css: "inherit" },
      { value: "ink", label: "Ink", css: "#193773" },
      { value: "purple", label: "Purple", css: "#5956d6" },
      { value: "coral", label: "Coral", css: "#f04e69" },
      { value: "green", label: "Green", css: "#008069" },
      { value: "black", label: "Black", css: "#111111" },
    ],
  },
} as const;

export type ComposerFontFamily = (typeof COMPOSER_APPEARANCE.fontFamily.options)[number]["value"];
export type ComposerFontSize = (typeof COMPOSER_APPEARANCE.fontSize.options)[number]["value"];
export type ComposerTextColor = (typeof COMPOSER_APPEARANCE.textColor.options)[number]["value"];

export function composerAppearanceCss(kind: "fontFamily" | "fontSize" | "textColor", value: string) {
  const options = COMPOSER_APPEARANCE[kind].options as readonly { value: string; css: string }[];
  return options.find((item) => item.value === value)?.css ?? "inherit";
}

/**
 * Wrap selection in WhatsApp markers.
 * - Selection present → wrap selection
 * - No selection but body has text → wrap entire body (fixes hi → hi*text*)
 * - Empty body → insert markers with caret between them
 */
export function wrapWaTextStyle(body: string, start: number, end: number, style: WaTextStyle) {
  const { open, close } = MARKERS[style];
  const safeStart = Math.max(0, Math.min(start, body.length));
  const safeEnd = Math.max(safeStart, Math.min(end, body.length));
  let from = safeStart;
  let to = safeEnd;
  let selected = body.slice(from, to);

  if (!selected) {
    if (body.length > 0) {
      from = 0;
      to = body.length;
      selected = body;
    } else {
      const next = `${open}${close}`;
      return {
        body: next,
        selectionStart: open.length,
        selectionEnd: open.length,
        cursor: open.length,
      };
    }
  }

  // Toggle off if already wrapped with the same markers.
  if (selected.startsWith(open) && selected.endsWith(close) && selected.length > open.length + close.length) {
    const inner = selected.slice(open.length, selected.length - close.length);
    const next = `${body.slice(0, from)}${inner}${body.slice(to)}`;
    return {
      body: next,
      selectionStart: from,
      selectionEnd: from + inner.length,
      cursor: from + inner.length,
    };
  }

  const next = `${body.slice(0, from)}${open}${selected}${close}${body.slice(to)}`;
  return {
    body: next,
    selectionStart: from + open.length,
    selectionEnd: from + open.length + selected.length,
    cursor: from + open.length + selected.length,
  };
}
