import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { JetBrains_Mono, Space_Grotesk } from "next/font/google";
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
      <html lang="en" className={`${spaceGrotesk.variable} ${jetbrainsMono.variable}`}>
        <body className="antialiased">{children}</body>
      </html>
    </ClerkProvider>
  );
}
