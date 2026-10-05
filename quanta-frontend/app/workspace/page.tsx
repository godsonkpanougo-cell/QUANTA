"use client";

/**
 * A2 · Pilier 1 — Workspace : projets de recherche persistants.
 * Liste les projets (GET /projects), création en un formulaire
 * (POST /projects), ouverture du détail (versions, runs, replay).
 * Les données réelles viennent de l'API ; aucune donnée inventée.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FolderKanban, Loader2, Plus, RefreshCw } from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";

interface ProjectItem {
  project_id: string;
  name: string;
  description: string;
  dataset_hash: string | null;
  created_at: string;
  updated_at: string;
  n_runs: number;
  n_versions: number;
}

function apiBase(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  return baseUrl.replace(/\/$/, "");
}

export default function WorkspacePage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${apiBase()}/projects`, {
        credentials: "include",
      });
      if (res.status === 401) {
        setProjects([]);
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as { projects: ProjectItem[] };
      setProjects(data.projects ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur réseau");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    // Différé : evite un setState synchrone dans le corps de l'effet.
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [isAuthenticated, authLoading, load]);

  const createProject = async () => {
    if (!name.trim() || creating) return;
    try {
      setCreating(true);
      const res = await fetch(`${apiBase()}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name: name.trim(), description: description.trim() }),
      });
      if (!res.ok) {
        const detail = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(detail?.detail ?? `HTTP ${res.status}`);
      }
      setName("");
      setDescription("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Création impossible");
    } finally {
      setCreating(false);
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
        <h1 className="font-brand text-2xl text-quanta-primary">Workspace</h1>
        <p className="mt-4 font-sans text-quanta-muted">
          Connectez-vous pour retrouver vos projets de recherche persistants :
          datasets versionnés, analyses rattachées, comparaisons de versions.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-6 pt-28 pb-24">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-3 font-brand text-2xl text-quanta-primary">
            <FolderKanban strokeWidth={1.5} className="size-6 text-quanta-cyan" aria-hidden />
            Workspace
          </h1>
          <p className="mt-1 font-sans text-sm text-quanta-muted">
            Vos projets de recherche — chaque dataset et chaque analyse reste rattaché au projet.
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

      <section aria-label="Nouveau projet" className="glass mt-8 rounded-quanta border border-quanta-border-subtle p-5">
        <h2 className="flex items-center gap-2 font-sans text-sm font-medium text-quanta-secondary">
          <Plus strokeWidth={1.5} className="size-4 text-quanta-gold" aria-hidden />
          Nouveau projet
        </h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_2fr]">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nom du projet (ex : Mémoire L2 — perception du risque)"
            aria-label="Nom du projet"
            className="rounded-quanta border border-quanta-border-subtle bg-transparent px-3 py-2 font-sans text-sm text-quanta-primary placeholder:text-quanta-muted focus:border-quanta-cyan focus:outline-none"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description courte (optionnel)"
            aria-label="Description du projet"
            className="rounded-quanta border border-quanta-border-subtle bg-transparent px-3 py-2 font-sans text-sm text-quanta-primary placeholder:text-quanta-muted focus:border-quanta-cyan focus:outline-none"
          />
        </div>
        <button
          type="button"
          onClick={() => void createProject()}
          disabled={!name.trim() || creating}
          className="mt-4 inline-flex cursor-pointer items-center gap-2 rounded-quanta bg-quanta-gold px-5 py-2 font-sans text-sm font-medium text-quanta-void transition-all duration-300 hover:bg-quanta-gold-2 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {creating ? <Loader2 strokeWidth={1.5} className="size-4 animate-spin" aria-hidden /> : null}
          Créer le projet
        </button>
      </section>

      <section aria-label="Mes projets" className="mt-10">
        {loading ? (
          <div className="flex items-center gap-3 font-sans text-quanta-muted">
            <Loader2 strokeWidth={1.5} className="size-4 animate-spin" aria-hidden />
            Chargement des projets…
          </div>
        ) : projects.length === 0 ? (
          <p className="font-sans text-quanta-muted">
            Aucun projet pour l&apos;instant. Créez-en un ci-dessus, puis rattachez-y vos analyses
            depuis l&apos;historique.
          </p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2">
            {projects.map((p) => (
              <li key={p.project_id}>
                <Link
                  href={`/workspace/${p.project_id}`}
                  className="glass block rounded-quanta border border-quanta-border-subtle p-5 transition-quanta hover:border-quanta-cyan"
                >
                  <h3 className="font-sans text-base font-medium text-quanta-primary">{p.name}</h3>
                  {p.description && (
                    <p className="mt-1 line-clamp-2 font-sans text-sm text-quanta-muted">{p.description}</p>
                  )}
                  <p className="mt-3 font-mono text-xs text-quanta-secondary">
                    {p.n_runs} run{p.n_runs > 1 ? "s" : ""} · {p.n_versions} version{p.n_versions > 1 ? "s" : ""}
                  </p>
                  <p className="mt-1 font-mono text-xs text-quanta-muted">
                    MAJ {new Date(p.updated_at).toLocaleDateString("fr-FR")}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
