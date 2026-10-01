import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ask the Ref — Current football rules, cited",
  description: "Search the current IFAB Laws of the Game with exact section citations.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
