import type { MetadataRoute } from "next";

/** Installable mobile app shell (Android/iOS). Desktop browser layout unchanged. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "WhatsApp CRM",
    short_name: "WA CRM",
    description: "WhatsApp Business inbox for teams.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    display_override: ["standalone", "minimal-ui"],
    orientation: "portrait-primary",
    background_color: "#f6f9fb",
    theme_color: "#5956d6",
    lang: "en",
    icons: [
      {
        src: "/icons/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
