import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://xrasktheref.vercel.app"),
  title: "Ask the Ref — Current football rules, cited",
  description: "Search the current IFAB Laws of the Game with exact section citations.",
  openGraph: {
    title: "Ask the Ref — Current football rules, cited",
    description: "Search the current IFAB Laws of the Game with exact section citations.",
    type: "website",
  },
  twitter: { card: "summary_large_image" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
