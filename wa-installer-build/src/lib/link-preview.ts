import "server-only";

import { extractHttpUrls } from "@/lib/links";

export type LinkPreview = {
  url: string;
  title: string;
  description: string;
  image: string | null;
  siteName: string;
};

function isPrivateHostname(hostname: string) {
  const host = hostname.toLowerCase().replace(/\.$/, "");
  if (
    host === "localhost" ||
    host === "metadata.google.internal" ||
    host.endsWith(".localhost") ||
    host.endsWith(".local") ||
    host.endsWith(".internal")
  ) {
    return true;
  }
  return false;
}

function isPrivateIp(hostname: string) {
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(hostname)) return false;
  const parts = hostname.split(".").map(Number);
  if (parts.some((part) => !Number.isFinite(part) || part < 0 || part > 255)) return true;
  const [a, b] = parts;
  if (a === 10 || a === 127 || a === 0) return true;
  if (a === 169 && b === 254) return true;
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 192 && b === 168) return true;
  if (a === 100 && b >= 64 && b <= 127) return true;
  return false;
}

export function assertPublicHttpUrl(raw: string) {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return { ok: false as const, detail: "Invalid URL." };
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return { ok: false as const, detail: "Only http(s) links are supported." };
  }
  if (url.username || url.password) {
    return { ok: false as const, detail: "URL credentials are not allowed." };
  }
  if (isPrivateHostname(url.hostname) || isPrivateIp(url.hostname)) {
    return { ok: false as const, detail: "That host cannot be previewed." };
  }
  return { ok: true as const, url };
}

function metaContent(html: string, key: string) {
  const patterns = [
    new RegExp(`<meta[^>]+property=["']${key}["'][^>]+content=["']([^"']+)["']`, "i"),
    new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+property=["']${key}["']`, "i"),
    new RegExp(`<meta[^>]+name=["']${key}["'][^>]+content=["']([^"']+)["']`, "i"),
    new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+name=["']${key}["']`, "i"),
  ];
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match?.[1]) return decodeHtml(match[1].trim());
  }
  return "";
}

function decodeHtml(value: string) {
  return value
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function titleFromHtml(html: string) {
  const match = html.match(/<title[^>]*>([^<]{1,300})<\/title>/i);
  return match?.[1] ? decodeHtml(match[1].trim()) : "";
}

function absolutize(base: URL, value: string | null) {
  if (!value) return null;
  try {
    return new URL(value, base).href;
  } catch {
    return null;
  }
}

const previewCache = new Map<string, { at: number; value: LinkPreview | null }>();
const CACHE_MS = 30 * 60 * 1000;

export async function fetchLinkPreview(rawUrl: string): Promise<
  { ok: true; preview: LinkPreview } | { ok: false; detail: string; status?: number }
> {
  const checked = assertPublicHttpUrl(rawUrl);
  if (!checked.ok) return { ok: false, detail: checked.detail, status: 400 };

  const cached = previewCache.get(checked.url.href);
  if (cached && Date.now() - cached.at < CACHE_MS) {
    if (!cached.value) return { ok: false, detail: "No preview available.", status: 404 };
    return { ok: true, preview: cached.value };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(checked.url.href, {
      method: "GET",
      redirect: "follow",
      signal: controller.signal,
      headers: {
        Accept: "text/html,application/xhtml+xml",
        "User-Agent": "WhatsAppCRMLinkPreview/1.0",
      },
    });
    if (!response.ok) {
      previewCache.set(checked.url.href, { at: Date.now(), value: null });
      return { ok: false, detail: `Could not fetch link (${response.status}).`, status: 502 };
    }
    // Re-check final URL after redirects.
    const finalCheck = assertPublicHttpUrl(response.url || checked.url.href);
    if (!finalCheck.ok) {
      return { ok: false, detail: finalCheck.detail, status: 400 };
    }
    const contentType = response.headers.get("content-type") || "";
    if (!/text\/html|application\/xhtml\+xml/i.test(contentType)) {
      const preview: LinkPreview = {
        url: finalCheck.url.href,
        title: finalCheck.url.hostname,
        description: "",
        image: null,
        siteName: finalCheck.url.hostname.replace(/^www\./i, ""),
      };
      previewCache.set(checked.url.href, { at: Date.now(), value: preview });
      return { ok: true, preview };
    }
    const buffer = await response.arrayBuffer();
    const bytes = buffer.byteLength > 512_000 ? buffer.slice(0, 512_000) : buffer;
    const html = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    const title = metaContent(html, "og:title") || titleFromHtml(html) || finalCheck.url.hostname;
    const description = metaContent(html, "og:description") || metaContent(html, "description");
    const image = absolutize(finalCheck.url, metaContent(html, "og:image") || metaContent(html, "twitter:image") || null);
    const siteName =
      metaContent(html, "og:site_name") || finalCheck.url.hostname.replace(/^www\./i, "");
    const preview: LinkPreview = {
      url: finalCheck.url.href,
      title: title.slice(0, 200),
      description: description.slice(0, 300),
      image,
      siteName: siteName.slice(0, 120),
    };
    previewCache.set(checked.url.href, { at: Date.now(), value: preview });
    return { ok: true, preview };
  } catch {
    previewCache.set(checked.url.href, { at: Date.now(), value: null });
    return { ok: false, detail: "Could not load link preview.", status: 502 };
  } finally {
    clearTimeout(timer);
  }
}

export { extractHttpUrls };
