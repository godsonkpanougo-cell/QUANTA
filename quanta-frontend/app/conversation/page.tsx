"use client";

/**
 * A2 · Pilier 2 — Session conversationnelle sur un dataset.
 * Gauche : sessions existantes + création (dataset = uploads de l'historique).
 * Droite : tour par tour — question → analysis_id → polling /status →
 * réponse affichée (interprétation LLM ou mode dégradé, signalé tel quel).
 * Endpoints : GET/POST /conversations · POST /conversations/{id}/ask
 *           · GET /status/{analysis_id}.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, MessageSquare, Plus, RefreshCw, Send } from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";

interface HistoryItem {
  analysis_id: string;
  file_id: string;
  status: string;
  query: string;
  filename: string | null;
  created_at: string;
}
interface SessionItem {
  session_id: string;
  file_id: string;
  file_hash: string;
  project_id: string | null;
  created_at: string;
  updated_at: string;
  n_turns: number;
}
interface Turn {
  turn_id: string;
  turn_no: number;
  query: string;
  analysis_id: string;
  status: string;
  created_at: string;
}
interface StatusResponse {
  analysis_id: string;
  status: "pending" | "done" | "error";
  result?: {
    interpretation?: {
      llm_available?: boolean;
      reason?: string;
      resume_executif?: string;
      conclusion_generale?: string;
      interpretation_principale?: {
        niveau_technique?: string;
        niveau_analytique?: string;
        niveau_decisionnel?: string;
      };
    };
  };
  error?: string;
}

function apiBase(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  return baseUrl.replace(/\/$/, "");
}

export default function ConversationPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [datasets, setDatasets] = useState<HistoryItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [query, setQuery] = useState("");
  const [asking, setAsking] = useState(false);
  const [pendingTurn, setPendingTurn] = useState<{ query: string; analysisId: string } | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [answerDegraded, setAnswerDegraded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [sessRes, histRes] = await Promise.all([
        fetch(`${apiBase()}/conversations`, { credentials: "include" }),
        fetch(`${apiBase()}/history`, { credentials: "include" }),
      ]);
      if (sessRes.status === 401 || histRes.status === 401) return;
      if (!sessRes.ok || !histRes.ok) throw new Error("Chargement impossible");
      const sess = (await sessRes.json()) as { sessions: SessionItem[] };
      const hist = (await histRes.json()) as { analyses: HistoryItem[] };
      setSessions(sess.sessions ?? []);
      setDatasets((hist.analyses ?? []).filter((a) => a.status === "done"));
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

  const openSession = async (sessionId: string) => {
    try {
      setActiveId(sessionId);
      setAnswer(null);
      setPendingTurn(null);
      const res = await fetch(`${apiBase()}/conversations/${sessionId}`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as { turns: Turn[] };
      setTurns(data.turns ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Session illisible");
    }
  };

  const createSession = async (fileId: string) => {
    try {
      setError(null);
      const res = await fetch(`${apiBase()}/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ file_id: fileId }),
      });
      if (!res.ok) {
        const detail = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(detail?.detail ?? `HTTP ${res.status}`);
      }
      const created = (await res.json()) as SessionItem;
      await load();
      await openSession(created.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Création impossible");
    }
  };

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  useEffect(() => stopPolling, []);

  const ask = async () => {
    if (!activeId || !query.trim() || asking) return;
    try {
      setAsking(true);
      setError(null);
      setAnswer(null);
      setAnswerDegraded(false);
      const res = await fetch(`${apiBase()}/conversations/${activeId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ query: query.trim() }),
      });
      if (!res.ok) {
        const detail = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(detail?.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { analysis_id: string };
      setPendingTurn({ query: query.trim(), analysisId: data.analysis_id });
      setQuery("");
      setTurns((prev) => prev);
      // Poll /status jusqu'à done/error
      stopPolling();
      const poll = async () => {
        try {
          const sres = await fetch(`${apiBase()}/status/${data.analysis_id}`, {
            credentials: "include",
          });
          if (!sres.ok) return;
          const sdata = (await sres.json()) as StatusResponse;
          if (sdata.status === "done") {
            stopPolling();
            const interp = sdata.result?.interpretation ?? {};
            if (interp.llm_available) {
              const parts = [
                interp.interpretation_principale?.niveau_technique,
                interp.interpretation_principale?.niveau_analytique,
                interp.interpretation_principale?.niveau_decisionnel,
              ].filter(Boolean) as string[];
              setAnswer(
                parts.join("\n\n") ||
                  interp.resume_executif ||
                  interp.conclusion_generale ||
                  "Analyse terminée — consultez le détail dans l'historique.",
              );
              setAnswerDegraded(false);
            } else {
              setAnswer(
                "Mode dégradé : le service d'interprétation est momentanément indisponible, " +
                  "mais l'analyse statistique a bien été exécutée. " +
                  (interp.reason ?? "Consultez le résultat chiffré dans l'historique."),
              );
              setAnswerDegraded(true);
            }
            setPendingTurn(null);
            if (activeId) await openSession(activeId);
          } else if (sdata.status === "error") {
            stopPolling();
            setAnswer(`L'analyse a échoué : ${sdata.error ?? "erreur inconnue"}`);
            setAnswerDegraded(true);
            setPendingTurn(null);
          }
        } catch {
          // erreur réseau passagère : on retente au prochain tick
        }
      };
      await poll();
      if (pollingRef.current === null && pendingTurn === null) {
        // démarre l'intervalle seulement si le statut n'est pas encore final
        pollingRef.current = setInterval(() => void poll(), 3000);
        // Garde-fou : arrêt après 3 minutes
        setTimeout(() => {
          if (pollingRef.current) {
            stopPolling();
            setPendingTurn(null);
          }
        }, 180000);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Question impossible");
      setPendingTurn(null);
    } finally {
      setAsking(false);
    }
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
        <h1 className="font-brand text-2xl text-quanta-primary">Conversation</h1>
        <p className="mt-4 font-sans text-quanta-muted">
          Connectez-vous pour interroger vos datasets en langage naturel, tour par tour.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-6 pt-28 pb-24">
      <header>
        <h1 className="flex items-center gap-3 font-brand text-2xl text-quanta-primary">
          <MessageSquare strokeWidth={1.5} className="size-6 text-quanta-cyan" aria-hidden />
          Conversation
        </h1>
        <p className="mt-1 font-sans text-sm text-quanta-muted">
          Interrogez un dataset déjà uploadé, tour par tour. Chaque réponse est calculée
          sur vos données — l&apos;IA rédige, elle n&apos;invente pas.
        </p>
      </header>

      {error && (
        <p role="alert" className="mt-6 rounded-quanta border border-quanta-error/40 bg-quanta-error/10 px-4 py-3 font-sans text-sm text-quanta-error">
          {error}
        </p>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-[300px_1fr]">
        <aside aria-label="Sessions et datasets">
          <div className="glass rounded-quanta border border-quanta-border-subtle p-4">
            <h2 className="flex items-center gap-2 font-sans text-xs font-medium uppercase tracking-wide text-quanta-secondary">
              <Plus strokeWidth={1.5} className="size-3.5 text-quanta-gold" aria-hidden />
              Nouvelle session
            </h2>
            {datasets.length === 0 ? (
              <p className="mt-2 font-sans text-xs text-quanta-muted">
                Aucun dataset disponible. Lancez d&apos;abord une analyse depuis l&apos;accueil.
              </p>
            ) : (
              <ul className="mt-3 space-y-2">
                {datasets.slice(0, 6).map((d) => (
                  <li key={`${d.file_id}-${d.analysis_id}`}>
                    <button
                      type="button"
                      onClick={() => void createSession(d.file_id)}
                      className="w-full cursor-pointer truncate rounded-quanta border border-quanta-border-subtle px-3 py-2 text-left font-sans text-xs text-quanta-secondary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan"
                    >
                      {d.filename ?? "dataset"}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="glass mt-4 rounded-quanta border border-quanta-border-subtle p-4">
            <h2 className="flex items-center justify-between font-sans text-xs font-medium uppercase tracking-wide text-quanta-secondary">
              Sessions
              <button
                type="button"
                onClick={() => void load()}
                aria-label="Rafraîchir les sessions"
                className="cursor-pointer text-quanta-muted transition-quanta hover:text-quanta-cyan"
              >
                <RefreshCw strokeWidth={1.5} className="size-3.5" aria-hidden />
              </button>
            </h2>
            {sessions.length === 0 ? (
              <p className="mt-2 font-sans text-xs text-quanta-muted">Aucune session.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {sessions.map((s) => (
                  <li key={s.session_id}>
                    <button
                      type="button"
                      onClick={() => void openSession(s.session_id)}
                      className={`w-full cursor-pointer rounded-quanta border px-3 py-2 text-left font-sans text-xs transition-quanta ${
                        activeId === s.session_id
                          ? "border-quanta-cyan text-quanta-cyan"
                          : "border-quanta-border-subtle text-quanta-secondary hover:border-quanta-cyan hover:text-quanta-cyan"
                      }`}
                    >
                      {s.file_hash.slice(0, 10)}… · {s.n_turns} tour{s.n_turns > 1 ? "s" : ""}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        <section aria-label="Conversation" className="glass min-h-[420px] rounded-quanta border border-quanta-border-subtle p-5">
          {!activeId ? (
            <p className="font-sans text-sm text-quanta-muted">
              Sélectionnez une session ou créez-en une sur un dataset uploadé.
            </p>
          ) : (
            <>
              <ul aria-label="Tours précédents" className="space-y-3">
                {turns.map((t) => (
                  <li key={t.turn_id} className="rounded-quanta border border-quanta-border-subtle p-3">
                    <p className="font-sans text-sm text-quanta-primary">
                      <span className="font-mono text-xs text-quanta-muted">#{t.turn_no} · </span>
                      {t.query}
                    </p>
                    <p className="mt-1 font-mono text-xs text-quanta-secondary">
                      {t.status === "done" ? "✓ analysé" : `… ${t.status}`}
                      {t.analysis_id ? ` · analyse ${t.analysis_id.slice(0, 10)}…` : ""}
                    </p>
                  </li>
                ))}
              </ul>

              {pendingTurn && (
                <div className="mt-4 flex items-center gap-2 rounded-quanta border border-quanta-cyan/40 bg-quanta-cyan/5 px-4 py-3">
                  <Loader2 strokeWidth={1.5} className="size-4 animate-spin text-quanta-cyan" aria-hidden />
                  <p className="font-sans text-sm text-quanta-secondary">
                    Analyse en cours : « {pendingTurn.query} »
                  </p>
                </div>
              )}

              {answer && (
                <div
                  className={`mt-4 rounded-quanta border px-4 py-3 ${
                    answerDegraded
                      ? "border-quanta-warning/40 bg-quanta-warning/5"
                      : "border-quanta-cyan/40 bg-quanta-cyan/5"
                  }`}
                >
                  <p className="whitespace-pre-line font-sans text-sm text-quanta-primary">{answer}</p>
                </div>
              )}

              <form
                className="mt-6 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void ask();
                }}
              >
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Ex : compare les moyennes de salaire entre hommes et femmes"
                  aria-label="Votre question"
                  className="flex-1 rounded-quanta border border-quanta-border-subtle bg-transparent px-3 py-2 font-sans text-sm text-quanta-primary placeholder:text-quanta-muted focus:border-quanta-cyan focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={!query.trim() || asking}
                  className="inline-flex cursor-pointer items-center gap-2 rounded-quanta bg-quanta-gold px-4 py-2 font-sans text-sm font-medium text-quanta-void transition-all hover:bg-quanta-gold-2 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {asking ? <Loader2 strokeWidth={1.5} className="size-4 animate-spin" aria-hidden /> : <Send strokeWidth={1.5} className="size-4" aria-hidden />}
                  Poser
                </button>
              </form>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
