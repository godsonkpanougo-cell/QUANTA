import type { Metadata, Viewport } from "next";
import { Space_Grotesk } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/app/context/AuthContext";
import "@fontsource/space-grotesk";
import "@fontsource/jetbrains-mono";
import "@fontsource/unbounded";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["300", "400", "500"],
});

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? "https://quanta.onrender.com",
  ),
  title: "QUANTA — Intelligence Statistique",
  description: "Tu déposes ta base. Tu reçois un rapport que tu peux signer.",
  openGraph: {
    type: "website",
    siteName: "QUANTA",
    title: "QUANTA — Intelligence Statistique",
    description:
      "Dépose ta base de données, reçois un rapport statistique signable.",
    locale: "fr_FR",
  },
  twitter: {
    card: "summary_large_image",
    title: "QUANTA — Intelligence Statistique",
    description:
      "Dépose ta base de données, reçois un rapport statistique signable.",
  },
};

export const viewport: Viewport = {
  themeColor: "#0A0A0F",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body
        className={`${spaceGrotesk.variable} font-sans bg-quanta-void text-quanta-primary antialiased`}
      >
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}