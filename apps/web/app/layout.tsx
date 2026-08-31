import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { JetBrains_Mono, Space_Grotesk } from "next/font/google";
import Script from "next/script";

import { THEME_BOOTSTRAP_SCRIPT } from "@/lib/theme";
import "./globals.css";

/** The redesign's two faces.
 *
 *  Space Grotesk carries every heading and the recipient's name on a
 *  certificate; JetBrains Mono carries credential IDs, API paths and the small
 *  tracked-out labels — anything a person might read character by character or
 *  copy by hand.
 *
 *  Loaded through next/font rather than the design's `<link>` to
 *  fonts.googleapis.com. That link is a render-blocking request to a third
 *  party on every page, and it hands the visitor's IP to Google on a page whose
 *  whole promise is that verifying a credential needs no account and no
 *  relationship with anyone. next/font self-hosts the files and inlines the
 *  @font-face rules, so neither is true here.
 */
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "CertForge", template: "%s · CertForge" },
  description: "Secure, verifiable digital credentials.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider>
      <html
        lang="en"
        suppressHydrationWarning
        className={`${spaceGrotesk.variable} ${jetbrainsMono.variable}`}
      >
        <body className="antialiased">
          {/* beforeInteractive: Next.js hoists this into <head> and runs it
           *  before the page paints, which is the whole point -- it sets
           *  data-theme ahead of any stylesheet applying, so there is no
           *  frame of the wrong theme to flash. Placed as the first child of
           *  <body> because that is where Next.js documents and tests this
           *  pattern; beforeInteractive scripts are only valid in the root
           *  layout at all. suppressHydrationWarning on <html> is needed
           *  alongside it: this script sets an attribute React did not
           *  render, and without the flag React would flag that as a
           *  server/client mismatch on every single page. */}
          <Script id="theme-bootstrap" strategy="beforeInteractive">
            {THEME_BOOTSTRAP_SCRIPT}
          </Script>
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
