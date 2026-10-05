"use client";

/**
 * A2 · Pilier 3 — Dossier d'audit : Repro Pack ZIP d'une analyse.
 * Chaque chiffre publié est recalculable par un tiers : le pack contient
 * les données, le code d'analyse et les résultats persistés (lecture pure).
 * Endpoint : GET /repro_pack/{analysis_id}?theme=dark|light (ZIP).
 */

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FileArchive, Loader2 } from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";

function apiBase(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  return baseUrl.replace(/\/$/, "");
}

const CONTENU_PACK = [
  "donnees brutes utilisées (export du dataset analysé)",
  "requête originale et intention détectée",
  "résultats statistiques persistés (chaque chiffre du rapport)",
  "journal d'audit des transformations de données",
  "code de recalcul : le tiers rejoue et retrouve les mêmes valeurs",
];

export default function AuditDossierPage({
  params,
}: {
  params: Promise<{ analysis_id: string }>;
}) {
  const { analysis_id } = use(params);
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [downloading, setDownloading] = useState<"dark" | "light" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  useEffect(() => {
    // Réinitialisation différée : évite un setState synchrone dans l'effet.
    const t = setTimeout(() => {
      setError(null);
      setOk(false);
    }, 0);
    return () => clearTimeout(t);
  }, [analysis_id]);

  const download = async (theme: "dark" | "light") => {
    try {
      setDownloading(theme);
      setError(null);
      setOk(false);
      const res = await fetch(
        `${apiBase()}/repro_pack/${analysis_id}?theme=${theme}`,
        { credentials: "include" },
      );
      if (res.status === 404) {
        setError("Analyse introuvable (ou n'appartient pas à ce compte).");
        return;
      }
      if (res.status === 400) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null;
        setError(body?.detail ?? "Repro Pack indisponible pour cette analyse.");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `repro_pack_${analysis_id.slice(0, 8)}_${theme}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setOk(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Téléchargement impossible");
    } finally {
      setDownloading(null);
    }
  };

  if (authLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center pt-16">
        <Loader2 strokeWidth={1.5} className="size-6 animate-spin text-quanta-muted" />
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="mx-auto max-w-3xl px-6 pt-32 pb-24">
        <h1 className="font-brand text-2xl text-quanta-primary">Dossier d&apos;audit</h1>
        <p className="mt-4 font-sans text-quanta-muted">
          Connectez-vous pour télécharger le Repro Pack d&apos;une analyse.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 pt-28 pb-24">
      <Link
        href="/history"
        className="inline-flex items-center gap-2 font-sans text-sm text-quanta-secondary transition-quanta hover:text-quanta-cyan"
      >
        <ArrowLeft strokeWidth={1.5} className="size-4" aria-hidden />
        Retour à l&apos;historique
      </Link>

      <header className="mt-4">
        <h1 className="font-brand text-2xl text-quanta-primary">Dossier d&apos;audit</h1>
        <p className="mt-1 font-mono text-xs text-quanta-muted">analyse {analysis_id}</p>
        <p className="mt-3 font-sans text-sm text-quanta-muted">
          Le Repro Pack rend votre analyse <b className="text-quanta-primary">auditable par un tiers</b> :
          votre encadreur peut recalculer chaque chiffre du mémoire sans vous croire sur parole.
        </p>
      </header>

      {error && (
        <p role="alert" className="mt-6 rounded-quanta border border-quanta-error/40 bg-quanta-error/10 px-4 py-3 font-sans text-sm text-quanta-error">
          {error}
        </p>
      )}
      {ok && (
        <p role="status" className="mt-6 rounded-quanta border border-quanta-cyan/40 bg-quanta-cyan/10 px-4 py-3 font-sans text-sm text-quanta-cyan">
          Repro Pack téléchargé — vérifiez le ZIP dans vos fichiers.
        </p>
      )}

      <section aria-label="Télécharger" className="glass mt-8 rounded-quanta border border-quanta-border-subtle p-5">
        <h2 className="flex items-center gap-2 font-sans text-sm font-medium text-quanta-secondary">
          <FileArchive strokeWidth={1.5} className="size-4 text-quanta-gold" aria-hidden />
          Repro Pack (.zip)
        </h2>
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void download("dark")}
            disabled={downloading !== null}
            className="inline-flex cursor-pointer items-center gap-2 rounded-quanta bg-quanta-gold px-5 py-2 font-sans text-sm font-medium text-quanta-void transition-all hover:bg-quanta-gold-2 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {downloading === "dark" ? <Loader2 strokeWidth={1.5} className="size-4 animate-spin" aria-hidden /> : null}
            Télécharger (thème sombre)
          </button>
          <button
            type="button"
            onClick={() => void download("light")}
            disabled={downloading !== null}
            className="inline-flex cursor-pointer items-center gap-2 rounded-quanta border border-quanta-border-subtle px-5 py-2 font-sans text-sm text-quanta-secondary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan disabled:cursor-not-allowed disabled:opacity-40"
          >
            {downloading === "light" ? <Loader2 strokeWidth={1.5} className="size-4 animate-spin" aria-hidden /> : null}
            Version impression (thème clair)
          </button>
        </div>
      </section>

      <section aria-label="Contenu du pack" className="glass mt-6 rounded-quanta border border-quanta-border-subtle p-5">
        <h2 className="font-sans text-sm font-medium text-quanta-secondary">Ce que contient le pack</h2>
        <ul className="mt-3 space-y-2">
          {CONTENU_PACK.map((item) => (
            <li key={item} className="flex items-start gap-2 font-sans text-sm text-quanta-muted">
              <span aria-hidden className="mt-1.5 size-1.5 shrink-0 rounded-full bg-quanta-cyan" />
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-4 font-sans text-xs text-quanta-muted">
          Lecture pure côté serveur : le pack est reconstruit depuis les données persistées,
          sans recalcul, sans LLM — les valeurs ne peuvent pas différer de celles du rapport.
        </p>
      </section>

      <div className="mt-8 flex flex-wrap gap-4">
        <Link
          href={`/defense/${analysis_id}`}
          className="inline-flex items-center gap-2 font-sans text-sm text-quanta-secondary transition-quanta hover:text-quanta-cyan"
        >
          Étape suivante : préparer ma soutenance →
        </Link>
      </div>
    </main>
  );
}
