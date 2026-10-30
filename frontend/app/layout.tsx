import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CodeMap — Understand your codebase",
  description: "Local-first AI codebase architecture and insight explorer.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
