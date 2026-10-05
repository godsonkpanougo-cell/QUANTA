import type { Metadata, Viewport } from "next";
import {
  Cormorant_Garamond,
  Jost,
  Orbitron,
  Space_Grotesk,
} from "next/font/google";
import "./globals.css";
import { GoldDust } from "@/app/components/GoldDust";
import { SymbolRain } from "@/app/components/SymbolRain";
import { AuthProvider } from "@/app/context/AuthContext";
import "@fontsource/jetbrains-mono";

/* ── Typographie QUANTA — aucune police générique ─────────────
   Orbitron          : wordmark & titres d'apparat (géométrique futuriste,
                       écho direct du logo anneau + vecteur)
   Cormorant Garamond: accents élégants & petites écritures (italique)
   Jost              : corps de texte, labels HUD (géométrique humaniste)
   Space Grotesk     : titres d'interface (display)                     */
const orbitron = Orbitron({
  subsets: ["latin"],
  variable: "--font-orbitron",
  weight: ["400", "500", "600", "700", "800", "900"],
});

const cormorant = Cormorant_Garamond({
  subsets: ["latin"],
  variable: "--font-cormorant",
  style: ["normal", "italic"],
  weight: ["400", "500", "600"],
});

const jost = Jost({
  subsets: ["latin"],
  variable: "--font-jost",
  weight: ["300", "400", "500", "600"],
});

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
        className={`${orbitron.variable} ${cormorant.variable} ${jost.variable} ${spaceGrotesk.variable} font-sans bg-quanta-void text-quanta-primary antialiased`}
      >
        {/* Calque contenu : au-dessus de la pluie de symboles (z-0).
            Aucun transform/filtre : les fixed descendants restent ancrés
            au viewport. */}
        <AuthProvider>
          <div className="relative z-10">{children}</div>
        </AuthProvider>
        {/* Pluie de symboles mathématiques — décorative, toutes les pages. */}
        <SymbolRain />
        {/* Poussière d'or au curseur — décoratif, toutes les pages. */}
        <GoldDust />
      </body>
    </html>
  );
}
