"use client";

import Link from "next/link";
import { useEffect } from "react";
import { RotateCcw } from "lucide-react";

import { LogoQ } from "@/app/components/LogoQ";

/**
 * Erreur de route (segment) — verre or, bouton Réessayer.
 * Le reset() retente le rendu du segment sans recharger tout le site.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Journalisation console locale ; un hook Sentry/LogTail se brancherait ici.
    console.error("[QUANTA] Erreur de segment:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-quanta-void px-6 text-center">
      <div className="glass rounded-hero flex max-w-md flex-col items-center gap-6 px-8 py-12">
        <LogoQ size={56} />
        <p className="hud-label text-quanta-muted">Une perturbation est survenue</p>
        <h1 className="font-display text-2xl font-light text-quanta-primary">
          Cette vue n&apos;a pas pu s&apos;afficher
        </h1>
        <p className="font-sans text-sm leading-relaxed text-quanta-secondary">
          Le reste de l&apos;application fonctionne. Vous pouvez réessayer
          cette section ou revenir à l&apos;accueil.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="sheen inline-flex cursor-pointer items-center gap-2 rounded-quanta bg-quanta-gold px-6 py-2.5 font-sans text-sm font-medium text-quanta-void transition-quanta hover:bg-quanta-gold-2"
          >
            <RotateCcw strokeWidth={1.5} className="size-4" aria-hidden />
            Réessayer
          </button>
          <Link
            href="/"
            className="rounded-quanta border border-quanta-border-subtle px-6 py-2.5 font-sans text-sm text-quanta-secondary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan"
          >
            Accueil
          </Link>
        </div>
      </div>
    </div>
  );
}
