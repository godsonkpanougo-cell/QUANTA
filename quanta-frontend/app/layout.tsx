import type { Metadata } from "next";
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
  title: "QUANTA — Intelligence Statistique",
  description: "Tu déposes ta base. Tu reçois un rapport que tu peux signer.",
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