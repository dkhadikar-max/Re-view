import type { Metadata } from "next";
import { Fraunces, Outfit } from "next/font/google";
import { AuthShell } from "@/components/AuthShell";
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

export const metadata: Metadata = {
  title: "Revisit",
  description:
    "Revisit — the AI employee that manages every guest after booking: revenue, reviews, and lifetime value.",
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
