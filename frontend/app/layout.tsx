import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kryber — Turn long videos into Shorts",
  description: "Paste a video. Kryber finds the moments worth watching.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
