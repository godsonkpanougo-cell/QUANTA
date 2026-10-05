import Link from "next/link";

import { LogoQ } from "@/app/components/LogoQ";
import { SiteFooter } from "@/app/components/SiteFooter";

export const metadata = { title: "Page introuvable — QUANTA" };

/**
 * 404 QUANTA : le logo entaillé (ensemble vide) illustre littéralement
 * la page manquante — ∅ — puis retour à l'accueil.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col">
      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <LogoQ size={72} className="opacity-70" />
        <p className="hud-label mt-10 text-quanta-muted">Erreur 404</p>
        <h1 className="mt-3 font-brand text-4xl font-extralight text-quanta-primary">
          Cette page n&apos;existe pas
        </h1>
        <p className="mt-4 max-w-sm font-sans text-sm leading-relaxed text-quanta-secondary">
          Comme l&apos;ensemble vide, cette page est belle — mais vide.
          Retournons vers quelque chose de concret.
        </p>
        <Link
          href="/"
          className="sheen mt-10 inline-flex items-center gap-2 rounded-quanta bg-quanta-gold px-6 py-2.5 font-sans text-sm font-medium text-quanta-void transition-quanta hover:bg-quanta-gold-2"
        >
          Retour à QUANTA
        </Link>
      </main>
      <SiteFooter />
    </div>
  );
}
