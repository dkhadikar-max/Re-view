import type { Metadata } from "next";
import { Fraunces, Outfit } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
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
  title: "Guest Revenue Agent",
  description:
    "The AI employee that manages every guest after booking — revenue, reviews, and lifetime value.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${sans.variable} font-sans antialiased`}>
        <div className="min-h-screen bg-hero-wash bg-grain">
          <Sidebar />
          <main className="ml-60 min-h-screen px-6 py-8 md:px-10">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
