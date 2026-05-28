import type { Metadata } from "next";
import "./globals.css";
import { UpdateNotification } from "../components/update-notification";

export const metadata: Metadata = {
  title: "MiraDocs",
  description: "Local-first document intelligence workspace. Parse, inspect, and search any PDF, DOCX, or PPTX with hybrid RAG-powered retrieval.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        {children}
        <UpdateNotification />
      </body>
    </html>
  );
}
