export type LinkOrigin = "this-app" | "erp-login" | "meta" | "local-dev" | "loopback" | "other";

export type LinkFinding = {
  href: string;
  origin: LinkOrigin;
  ok: boolean;
  note: string;
};

export function classifyLink(href: string): LinkFinding {
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return { href, origin: "other", ok: false, note: "The link is not a valid URL." };
  }
  const host = url.hostname.toLowerCase();
  if (host === "wa.ukdscwala.com") {
    const secure = url.protocol === "https:";
    return {
      href,
      origin: "this-app",
      ok: secure,
      note: secure ? "Stays on this app." : "This app link must use https.",
    };
  }
  if (host === "app.jtcsxpert.com" && url.protocol === "https:" && url.pathname.startsWith("/login")) {
    return { href, origin: "erp-login", ok: true, note: "Official Customer Master login." };
  }
  if (host === "localhost" || host.endsWith(".localhost")) {
    return { href, origin: "local-dev", ok: true, note: "Local development only." };
  }
  if (host === "127.0.0.1" || host === "0.0.0.0" || host === "::1") {
    return { href, origin: "loopback", ok: true, note: "Loopback proxy, not a public link." };
  }
  if (host === "graph.facebook.com" || host === "developers.facebook.com") {
    return { href, origin: "meta", ok: url.protocol === "https:", note: "Meta documentation or API." };
  }
  if (host === "ukdscwala.com" || host === "www.ukdscwala.com" || host === "whatsapp.jtcsxpert.com") {
    return { href, origin: "other", ok: false, note: "This host is not the WhatsApp app or the Customer Master login." };
  }
  return { href, origin: "other", ok: true, note: "External link. It was not rewritten." };
}
