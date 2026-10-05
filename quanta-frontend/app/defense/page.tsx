"use client";

/**
 * A2 · Pilier 4 — Index « Préparer ma soutenance » : liste des analyses
 * terminées, chacune prête pour la génération du pack soutenance
 * (déterministe, sans LLM). Point d'entrée de l'onglet du header.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FileArchive, GraduationCap, Loader2, RefreshCw } from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";

interface HistoryItem {
  analysis_id: string;
  status: string;
  query: string;
  filename: string | null;
  confidence_score: number | null;
  created_at: string;
}

function apiBase(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  return baseUrl.replace(/\/$/, "");
}

export default function DefenseIndexPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${apiBase()}/history`, { credentials: "include" });
      if (res.status === 401) {
        setItems([]);
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as { analyses: HistoryItem[] };
      setItems((data.analyses ?? []).filter((a) => a.status === "done"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur réseau");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    // Différé : évite un setState synchrone dans le corps de l'effet.
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [isAuthenticated, authLoading, load]);

  if (authLoading || (loading && isAuthenticated)) {
    return (
      <main className="flex min-h-screen items-center justify-center pt-16">
        <Loader2 strokeWidth={1.5} className="size-6 animate-spin text-quanta-muted" />
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="mx-auto max-w-3xl px-6 pt-32 pb-24">
        <h1 className="flex items-center gap-3 font-brand text-2xl text-quanta-primary">
          <GraduationCap strokeWidth={1.5} className="size-6 text-quanta-gold" aria-hidden />
          Préparer ma soutenance
        </h1>
        <p className="mt-4 font-sans text-quanta-muted">
          Connectez-vous : chaque analyse terminée devient une préparation anti-blackout —
          questions probables du jury avec réponses chiffrées, issues de vos données.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-6 pt-28 pb-24">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="flex items-center gap-3 font-brand text-2xl text-quanta-primary">
            <GraduationCap strokeWidth={1.5} className="size-6 text-quanta-gold" aria-hidden />
            Préparer ma soutenance
          </h1>
          <p className="mt-1 font-sans text-sm text-quanta-muted">
            Choisissez une analyse terminée. Le pack est généré de façon déterministe :
            aucune question invention, aucun chiffre inventé.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          aria-label="Rafraîchir"
          className="inline-flex cursor-pointer items-center gap-2 rounded-quanta border border-quanta-border-subtle px-3 py-2 font-sans text-sm text-quanta-secondary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan"
        >
          <RefreshCw strokeWidth={1.5} className={loading ? "size-4 animate-spin" : "size-4"} aria-hidden />
        </button>
      </header>

      {error && (
        <p role="alert" className="mt-6 rounded-quanta border border-quanta-error/40 bg-quanta-error/10 px-4 py-3 font-sans text-sm text-quanta-error">
          {error}
        </p>
      )}

      <section aria-label="Analyses terminées" className="mt-8">
        {items.length === 0 ? (
          <p className="font-sans text-quanta-muted">
            Aucune analyse terminée. Lancez d&apos;abord une analyse depuis l&apos;accueil.
          </p>
        ) : (
          <ul className="space-y-4">
            {items.map((a) => (
              <li key={a.analysis_id} className="glass rounded-quanta border border-quanta-border-subtle p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h2 className="font-sans text-base font-medium text-quanta-primary">
                      {a.filename ?? "dataset"}
                    </h2>
                    {a.query && (
                      <p className="mt-0.5 truncate font-sans text-sm text-quanta-muted">{a.query}</p>
                    )}
                    <p className="mt-2 font-mono text-xs text-quanta-secondary">
                      {a.confidence_score !== null ? `confiance ${a.confidence_score} · ` : ""}
                      {new Date(a.created_at).toLocaleDateString("fr-FR")}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/defense/${a.analysis_id}`}
                      className="inline-flex items-center gap-2 rounded-quanta bg-quanta-gold px-4 py-2 font-sans text-sm font-medium text-quanta-void transition-all hover:bg-quanta-gold-2"
                    >
                      <GraduationCap strokeWidth={1.5} className="size-4" aria-hidden />
                      Soutenance
                    </Link>
                    <Link
                      href={`/audit/${a.analysis_id}`}
                      className="inline-flex items-center gap-2 rounded-quanta border border-quanta-border-subtle px-4 py-2 font-sans text-sm text-quanta-secondary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan"
                    >
                      <FileArchive strokeWidth={1.5} className="size-4" aria-hidden />
                      Dossier d&apos;audit
                    </Link>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
