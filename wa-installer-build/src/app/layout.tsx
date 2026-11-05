import type { Metadata, Viewport } from "next";
import { Poppins, Sen } from "next/font/google";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

/** Gupshup brand pair: Sen headlines + Poppins UI/body (ClearTax-like product hierarchy). */
const uiBody = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-ui-body",
  display: "swap",
});

const uiDisplay = Sen({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-ui-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "WhatsApp CRM",
  description:
    "WhatsApp Business inbox for teams. Demo mode uses sample conversations and is not connected to Meta.",
  applicationName: "WhatsApp CRM",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "WA CRM",
  },
  formatDetection: {
    telephone: false,
  },
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  other: {
    "mobile-web-app-capable": "yes",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
  themeColor: "#5956d6",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`h-full overflow-x-hidden ${uiBody.variable} ${uiDisplay.variable}`}>
      <body className="h-full overflow-x-hidden overscroll-x-none font-sans text-wa-ink antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
