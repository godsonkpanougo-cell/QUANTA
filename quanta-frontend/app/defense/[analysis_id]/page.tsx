"use client";

/**
 * A2 · Pilier 4 — « Préparer ma soutenance » : Mode Soutenance anti-blackout.
 * Questions probables du jury AVEC réponses chiffrées tirées du résultat
 * persisté (aucun chiffre inventé, aucun LLM, déterministe).
 * Endpoint : GET /defense/{analysis_id}.
 */

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, GraduationCap, Loader2, Printer } from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";

interface FicheIdentite {
  filename: string | null;
  n_rows: number | null;
  n_cols: number | null;
  score_global: number | null;
  niveau_confiance: string | null;
  test_execute: string | null;
  requete: string;
}
interface QuestionJury {
  question: string;
  reponse: string;
  [k: string]: unknown;
}
interface DefenseVigilance {
  vigilance: string;
  defense_preparee: string;
}
interface DefensePack {
  analysis_id: string;
  fiche_identite: FicheIdentite;
  questions_probables: QuestionJury[];
  defenses_points_de_vigilance: DefenseVigilance[];
  memo_derniere_ligne: Array<{ chiffre: string; ce_que_ca_prouve: string }>;
  n_questions: number;
}

function apiBase(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  return baseUrl.replace(/\/$/, "");
}

export default function DefensePage({ params }: { params: Promise<{ analysis_id: string }> }) {
  const { analysis_id } = use(params);
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [pack, setPack] = useState<DefensePack | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadPack() {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`${apiBase()}/defense/${analysis_id}`, {
          credentials: "include",
        });
        if (res.status === 404) {
          if (!cancelled) setError("Analyse introuvable (ou n'appartient pas à ce compte).");
          return;
        }
        if (res.status === 400) {
          const body = (await res.json().catch(() => null)) as { detail?: string } | null;
          if (!cancelled) setError(body?.detail ?? "Soutenance indisponible pour cette analyse.");
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as DefensePack;
        if (!cancelled) setPack(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Chargement impossible");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (!isAuthenticated) return;
    // Différé : évite un setState synchrone dans le corps de l'effet.
    const t = setTimeout(() => void loadPack(), 0);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    return () => {
      cancelled = true;
    };
  }, [analysis_id, isAuthenticated, authLoading]);

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
        <h1 className="font-brand text-2xl text-quanta-primary">Préparer ma soutenance</h1>
        <p className="mt-4 font-sans text-quanta-muted">
          Connectez-vous pour générer votre préparation anti-blackout.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 pt-28 pb-24">
      <Link
        href="/history"
        className="print:hidden inline-flex items-center gap-2 font-sans text-sm text-quanta-secondary transition-quanta hover:text-quanta-cyan"
      >
        <ArrowLeft strokeWidth={1.5} className="size-4" aria-hidden />
        Retour à l&apos;historique
      </Link>

      <header className="mt-4">
        <h1 className="flex items-center gap-3 font-brand text-2xl text-quanta-primary">
          <GraduationCap strokeWidth={1.5} className="size-6 text-quanta-gold" aria-hidden />
          Préparer ma soutenance
        </h1>
        <p className="mt-1 font-sans text-sm text-quanta-muted">
          Questions probables du jury, réponses chiffrées tirées de votre analyse.
          Généré de façon déterministe depuis les données persistées — aucun chiffre inventé.
        </p>
      </header>

      {error && (
        <>
          <p role="alert" className="mt-6 rounded-quanta border border-quanta-error/40 bg-quanta-error/10 px-4 py-3 font-sans text-sm text-quanta-error">
            {error}
          </p>
          <Link
            href="/history"
            className="mt-4 inline-flex font-sans text-sm text-quanta-secondary transition-quanta hover:text-quanta-cyan"
          >
            ← Choisir une analyse terminée
          </Link>
        </>
      )}

      {pack && (
        <>
          {/* Fiche d'identité de l'analyse */}
          <section aria-label="Fiche d'identité" className="glass mt-8 rounded-quanta border border-quanta-border-subtle p-5">
            <h2 className="font-sans text-sm font-medium uppercase tracking-wide text-quanta-secondary">
              Fiche d&apos;identité
            </h2>
            <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 font-sans text-sm sm:grid-cols-2">
              <div className="flex justify-between gap-4">
                <dt className="text-quanta-muted">Fichier</dt>
                <dd className="truncate text-right text-quanta-primary">{pack.fiche_identite.filename ?? "—"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-quanta-muted">Données</dt>
                <dd className="font-mono text-quanta-primary">
                  {pack.fiche_identite.n_rows ?? "—"} lignes × {pack.fiche_identite.n_cols ?? "—"} colonnes
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-quanta-muted">Test exécuté</dt>
                <dd className="text-right text-quanta-primary">{pack.fiche_identite.test_execute ?? "—"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-quanta-muted">Score de confiance</dt>
                <dd className="font-mono text-quanta-primary">
                  {pack.fiche_identite.score_global ?? "—"}
                  {pack.fiche_identite.niveau_confiance ? ` (${pack.fiche_identite.niveau_confiance})` : ""}
                </dd>
              </div>
              {pack.fiche_identite.requete && (
                <div className="flex justify-between gap-4 sm:col-span-2">
                  <dt className="shrink-0 text-quanta-muted">Requête</dt>
                  <dd className="text-right text-quanta-primary">{pack.fiche_identite.requete}</dd>
                </div>
              )}
            </dl>
          </section>

          {/* Mémo dernière ligne — à connaître par cœur avant d'entrer dans la salle */}
          {pack.memo_derniere_ligne.length > 0 && (
            <section aria-label="Mémo dernière ligne" className="glass mt-6 rounded-quanta border border-quanta-gold/40 p-5">
              <h2 className="font-sans text-sm font-medium text-quanta-gold">
                Mémo dernière ligne — les chiffres à connaître par cœur
              </h2>
              <ul className="mt-3 space-y-3">
                {pack.memo_derniere_ligne.map((m, i) => (
                  <li key={i} className="rounded-quanta border border-quanta-border-subtle p-3">
                    <p className="font-mono text-sm text-quanta-primary">{m.chiffre}</p>
                    <p className="mt-1 font-sans text-xs text-quanta-muted">{m.ce_que_ca_prouve}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Questions probables du jury + réponses chiffrées */}
          <section aria-label="Questions du jury" className="mt-10">
            <h2 className="font-sans text-sm font-medium uppercase tracking-wide text-quanta-secondary">
              Questions probables du jury ({pack.n_questions})
            </h2>
            <ul className="mt-4 space-y-4">
              {pack.questions_probables.map((q, i) => (
                <li key={i} className="glass rounded-quanta border border-quanta-border-subtle p-4">
                  <p className="font-sans text-sm font-medium text-quanta-primary">
                    <span className="mr-2 font-mono text-xs text-quanta-muted">Q{i + 1}</span>
                    {q.question}
                  </p>
                  <p className="mt-2 border-l-2 border-quanta-cyan/50 pl-3 font-sans text-sm whitespace-pre-line text-quanta-secondary">
                    {q.reponse}
                  </p>
                </li>
              ))}
            </ul>
          </section>

          {/* Défenses aux points de vigilance (Skeptic Engine) */}
          {pack.defenses_points_de_vigilance.length > 0 && (
            <section aria-label="Points de vigilance" className="mt-10">
              <h2 className="font-sans text-sm font-medium uppercase tracking-wide text-quanta-secondary">
                Points de vigilance & défenses préparées
              </h2>
              <ul className="mt-4 space-y-4">
                {pack.defenses_points_de_vigilance.map((d, i) => (
                  <li key={i} className="rounded-quanta border border-quanta-warning/30 p-4">
                    <p className="font-sans text-sm text-quanta-warning">{d.vigilance}</p>
                    <p className="mt-2 font-sans text-xs text-quanta-muted">{d.defense_preparee}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="mt-10 flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex cursor-pointer items-center gap-2 rounded-quanta border border-quanta-border-subtle px-4 py-2 font-sans text-sm text-quanta-secondary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan"
            >
              <Printer strokeWidth={1.5} className="size-4" aria-hidden />
              Imprimer / enregistrer en PDF
            </button>
            <Link
              href={`/audit/${analysis_id}`}
              className="inline-flex items-center gap-2 font-sans text-sm text-quanta-secondary transition-quanta hover:text-quanta-cyan"
            >
              Pièce jointe pour le jury : dossier d&apos;audit →
            </Link>
          </div>
        </>
      )}
    </main>
  );
}
