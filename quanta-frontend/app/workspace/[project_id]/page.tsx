"use client";

/**
 * A2 · Pilier 1 — Détail d'un projet : versions de dataset, runs,
 * replay à l'identique (cache garantit le même résultat), comparaison
 * de deux versions (delta de confiance + tests communs).
 * Endpoints : GET /projects/{id} · POST /projects/runs/{run_id}/replay
 *           · GET /projects/{id}/compare?version_a=&version_b=
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, GitCompare, Loader2, PlayCircle, RefreshCw } from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";

interface DatasetVersion {
  version_id: string;
  version_no: number;
  file_hash: string;
  file_id: string | null;
  filename: string | null;
  created_at: string;
}
interface Run {
  run_id: string;
  version_id: string;
  query: string;
  analysis_id: string | null;
  status: string;
  summary: string | null;
  created_at: string;
}
interface ProjectDetail {
  project_id: string;
  name: string;
  description: string;
  versions: DatasetVersion[];
  runs: Run[];
}
interface CompareResult {
  comparable: boolean;
  reason?: string;
  confidence?: { a?: number; b?: number; delta?: number };
  tests?: Array<{
    test: string;
    decision_a: string | null;
    decision_b: string | null;
    p_a: number | null;
    p_b: number | null;
  }>;
}

function apiBase(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  return baseUrl.replace(/\/$/, "");
}

export default function ProjectDetailPage() {
  const params = useParams<{ project_id: string }>();
  const projectId = params?.project_id;
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replaying, setReplaying] = useState<string | null>(null);
  const [replayMsg, setReplayMsg] = useState<string | null>(null);
  const [va, setVa] = useState<string>("");
  const [vb, setVb] = useState<string>("");
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [comparing, setComparing] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${apiBase()}/projects/${projectId}`, {
        credentials: "include",
      });
      if (res.status === 404) {
        setError("Projet introuvable (ou n'appartient pas à ce compte).");
        setProject(null);
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as ProjectDetail;
      setProject(data);
      const vids = (data.versions ?? []).map((v) => v.version_id);
      setVa(vids[0] ?? "");
      setVb(vids[1] ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur réseau");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!isAuthenticated) return;
    // Différé : evite un setState synchrone dans le corps de l'effet.
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [isAuthenticated, authLoading, load]);

  const replay = async (runId: string) => {
    try {
      setReplaying(runId);
      setReplayMsg(null);
      const res = await fetch(`${apiBase()}/projects/runs/${runId}/replay`, {
        method: "POST",
        credentials: "include",
      });
      const data = (await res.json()) as {
        replayed?: boolean;
        from_cache?: boolean;
        reason?: string;
        analysis?: { analysis_id?: string } | string;
      };
      if (!res.ok) throw new Error((data as { detail?: string }).detail ?? `HTTP ${res.status}`);
      if (data.replayed) {
        const aid =
          typeof data.analysis === "string"
            ? data.analysis
            : data.analysis?.analysis_id ?? "";
        setReplayMsg(
          `Rejoué à l'identique${data.from_cache ? " (cache — mêmes valeurs garanties)" : ""}.` +
            (aid ? ` Analyse : ${aid}` : ""),
        );
      } else {
        setReplayMsg(data.reason ?? "Replay indisponible.");
      }
      await load();
    } catch (e) {
      setReplayMsg(e instanceof Error ? e.message : "Replay impossible");
    } finally {
      setReplaying(null);
    }
  };

  const runCompare = async () => {
    if (!projectId || !va || !vb || va === vb) return;
    try {
      setComparing(true);
      setCompare(null);
      const res = await fetch(
        `${apiBase()}/projects/${projectId}/compare?version_a=${encodeURIComponent(va)}&version_b=${encodeURIComponent(vb)}`,
        { credentials: "include" },
      );
      const data = (await res.json()) as CompareResult & { detail?: string };
      if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
      setCompare(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Comparaison impossible");
    } finally {
      setComparing(false);
    }
  };

  const versionLabel = (vid: string) => {
    const v = project?.versions.find((x) => x.version_id === vid);
    return v ? `v${v.version_no}${v.filename ? ` — ${v.filename}` : ""}` : vid.slice(0, 8);
  };

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
        <h1 className="font-brand text-2xl text-quanta-primary">Projet</h1>
        <p className="mt-4 font-sans text-quanta-muted">
          Connectez-vous pour consulter ce projet.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-6 pt-28 pb-24">
      <Link
        href="/workspace"
        className="inline-flex items-center gap-2 font-sans text-sm text-quanta-secondary transition-quanta hover:text-quanta-cyan"
      >
        <ArrowLeft strokeWidth={1.5} className="size-4" aria-hidden />
        Retour au Workspace
      </Link>

      {error && (
        <p role="alert" className="mt-6 rounded-quanta border border-quanta-error/40 bg-quanta-error/10 px-4 py-3 font-sans text-sm text-quanta-error">
          {error}
        </p>
      )}

      {project && (
        <>
          <header className="mt-4">
            <h1 className="font-brand text-2xl text-quanta-primary">{project.name}</h1>
            {project.description && (
              <p className="mt-1 font-sans text-sm text-quanta-muted">{project.description}</p>
            )}
          </header>

          <section aria-label="Versions du dataset" className="mt-10">
            <h2 className="font-sans text-sm font-medium uppercase tracking-wide text-quanta-secondary">
              Versions du dataset ({project.versions.length})
            </h2>
            {project.versions.length === 0 ? (
              <p className="mt-3 font-sans text-quanta-muted">
                Aucune version enregistrée. Une version est créée quand une analyse est
                rattachée au projet.
              </p>
            ) : (
              <ul className="mt-4 grid gap-3 sm:grid-cols-2">
                {project.versions.map((v) => (
                  <li key={v.version_id} className="glass rounded-quanta border border-quanta-border-subtle p-4">
                    <p className="font-sans text-sm font-medium text-quanta-primary">
                      v{v.version_no} {v.filename ? `— ${v.filename}` : ""}
                    </p>
                    <p className="mt-1 break-all font-mono text-xs text-quanta-muted">
                      hash {v.file_hash.slice(0, 16)}…
                    </p>
                    <p className="mt-1 font-mono text-xs text-quanta-muted">
                      {new Date(v.created_at).toLocaleString("fr-FR")}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="Exécutions" className="mt-10">
            <h2 className="font-sans text-sm font-medium uppercase tracking-wide text-quanta-secondary">
              Exécutions ({project.runs.length})
            </h2>
            {replayMsg && (
              <p className="mt-3 rounded-quanta border border-quanta-cyan/40 bg-quanta-cyan/10 px-4 py-2 font-sans text-sm text-quanta-cyan">
                {replayMsg}
              </p>
            )}
            {project.runs.length === 0 ? (
              <p className="mt-3 font-sans text-quanta-muted">
                Aucune exécution. Rattachez une analyse au projet depuis l&apos;historique.
              </p>
            ) : (
              <ul className="mt-4 space-y-3">
                {project.runs.map((r) => (
                  <li
                    key={r.run_id}
                    className="glass flex flex-wrap items-center justify-between gap-3 rounded-quanta border border-quanta-border-subtle p-4"
                  >
                    <div className="min-w-0">
                      <p className="font-sans text-sm text-quanta-primary">
                        {versionLabel(r.version_id)} — <span className="font-mono text-xs">{r.status}</span>
                      </p>
                      <p className="mt-0.5 truncate font-sans text-xs text-quanta-muted">
                        {r.query || "(requête vide)"}
                      </p>
                      {r.analysis_id && (
                        <p className="font-mono text-xs text-quanta-secondary">
                          analyse {r.analysis_id.slice(0, 12)}…
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {r.analysis_id && (
                        <Link
                          href={`/defense/${r.analysis_id}`}
                          className="inline-flex items-center gap-1 rounded-quanta border border-quanta-border-subtle px-3 py-1.5 font-sans text-xs text-quanta-secondary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan"
                        >
                          Soutenance
                        </Link>
                      )}
                      <button
                        type="button"
                        onClick={() => void replay(r.run_id)}
                        disabled={replaying === r.run_id}
                        className="inline-flex cursor-pointer items-center gap-1 rounded-quanta border border-quanta-border-subtle px-3 py-1.5 font-sans text-xs text-quanta-secondary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan disabled:opacity-40"
                        title="Rejouer à l'identique (mêmes données, même requête)"
                      >
                        {replaying === r.run_id ? (
                          <Loader2 strokeWidth={1.5} className="size-3.5 animate-spin" aria-hidden />
                        ) : (
                          <PlayCircle strokeWidth={1.5} className="size-3.5" aria-hidden />
                        )}
                        Rejouer
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {project.versions.length >= 2 && (
            <section aria-label="Comparer deux versions" className="glass mt-10 rounded-quanta border border-quanta-border-subtle p-5">
              <h2 className="flex items-center gap-2 font-sans text-sm font-medium text-quanta-secondary">
                <GitCompare strokeWidth={1.5} className="size-4 text-quanta-gold" aria-hidden />
                Comparer deux versions
              </h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
                <select
                  value={va}
                  onChange={(e) => setVa(e.target.value)}
                  aria-label="Version A"
                  className="rounded-quanta border border-quanta-border-subtle bg-transparent px-3 py-2 font-sans text-sm text-quanta-primary"
                >
                  {project.versions.map((v) => (
                    <option key={v.version_id} value={v.version_id} className="bg-quanta-void">
                      {versionLabel(v.version_id)}
                    </option>
                  ))}
                </select>
                <select
                  value={vb}
                  onChange={(e) => setVb(e.target.value)}
                  aria-label="Version B"
                  className="rounded-quanta border border-quanta-border-subtle bg-transparent px-3 py-2 font-sans text-sm text-quanta-primary"
                >
                  {project.versions.map((v) => (
                    <option key={v.version_id} value={v.version_id} className="bg-quanta-void">
                      {versionLabel(v.version_id)}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => void runCompare()}
                  disabled={comparing || !va || !vb || va === vb}
                  className="inline-flex cursor-pointer items-center gap-2 rounded-quanta bg-quanta-gold px-4 py-2 font-sans text-sm font-medium text-quanta-void transition-all hover:bg-quanta-gold-2 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {comparing ? <Loader2 strokeWidth={1.5} className="size-4 animate-spin" aria-hidden /> : null}
                  Comparer
                </button>
              </div>
              {compare && (
                <div className="mt-4">
                  {!compare.comparable ? (
                    <p className="font-sans text-sm text-quanta-warning">{compare.reason}</p>
                  ) : (
                    <>
                      {compare.confidence && (
                        <p className="font-mono text-sm text-quanta-primary">
                          Confiance A : {compare.confidence.a ?? "—"} · B : {compare.confidence.b ?? "—"}
                          {typeof compare.confidence.delta === "number" && (
                            <> · Δ {compare.confidence.delta > 0 ? "+" : ""}{compare.confidence.delta}</>
                          )}
                        </p>
                      )}
                      {compare.tests && compare.tests.length > 0 && (
                        <table className="mt-3 w-full font-sans text-xs">
                          <thead>
                            <tr className="text-left text-quanta-muted">
                              <th className="py-1 pr-3">Test</th>
                              <th className="py-1 pr-3">Décision A</th>
                              <th className="py-1 pr-3">Décision B</th>
                              <th className="py-1">p A / p B</th>
                            </tr>
                          </thead>
                          <tbody className="text-quanta-primary">
                            {compare.tests.map((t) => (
                              <tr key={t.test} className="border-t border-quanta-border-subtle">
                                <td className="py-1 pr-3">{t.test}</td>
                                <td className="py-1 pr-3">{t.decision_a ?? "—"}</td>
                                <td className="py-1 pr-3">{t.decision_b ?? "—"}</td>
                                <td className="py-1 font-mono">
                                  {t.p_a ?? "—"} / {t.p_b ?? "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </>
                  )}
                </div>
              )}
            </section>
          )}
        </>
      )}

      {!project && !loading && !error && (
        <p className="mt-6 flex items-center gap-2 font-sans text-quanta-muted">
          <RefreshCw strokeWidth={1.5} className="size-4" aria-hidden />
          Projet indisponible.
        </p>
      )}
    </main>
  );
}
