import type { Metadata } from "next";
import { Fraunces, Outfit } from "next/font/google";
import { AuthShell } from "@/components/AuthShell";
import { REVISIT } from "@/lib/brand";
import "./globals.css";

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
});

const sans = Outfit({
  subsets: ["latin"],
  variable: "--font-sans",
  weight: ["300", "400", "500", "600", "700"],
});

// SEO_AEO_GEO_AUDIT.md §2/§9 — root defaults. Route-specific pages
// (onboard) override title/description/canonical via their own
// layout; the authenticated app tree and /celebrate/[token] override
// `robots` to noindex via their own layouts (see those files) rather
// than a robots.txt Disallow, since a discovered token URL still
// needs to hit a real noindex meta tag to be reliably kept out of
// search results, per SEO_AEO_GEO_IMPLEMENTATION.md.
export const metadata: Metadata = {
  metadataBase: new URL(REVISIT.siteUrl),
  title: {
    default: REVISIT.title,
    template: `%s | ${REVISIT.name}`,
  },
  description: REVISIT.description,
  applicationName: REVISIT.name,
  alternates: {
    canonical: "/",
  },
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    type: "website",
    url: REVISIT.siteUrl,
    siteName: REVISIT.name,
    title: REVISIT.title,
    description: REVISIT.description,
  },
  twitter: {
    card: "summary_large_image",
    title: REVISIT.title,
    description: REVISIT.description,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${sans.variable} font-sans antialiased`}>
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
