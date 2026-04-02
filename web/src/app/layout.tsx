import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import { PersonaProvider } from "@/components/PersonaProvider";

export const metadata: Metadata = {
  title: "Renzo Rico — Data Scientist",
  description:
    "Portfolio of Renzo Rico — DS/ML engineer building systems that make data useful. London-based.",
  openGraph: {
    title: "Renzo Rico — Living Data Museum",
    description:
      "DS/ML engineer building systems that make data useful. Four projects. Four problems worth solving.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body>
        <PersonaProvider>{children}</PersonaProvider>
      </body>
    </html>
  );
}
