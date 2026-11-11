import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Relay: AI support agent",
  description: "An AI agent that drafts replies to support emails, checks every fact, and waits for a person to approve.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
