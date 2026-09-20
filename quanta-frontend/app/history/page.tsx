"use client";

import { useEffect, useState } from "react";
import { Download, FileText, Clock, CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";

interface Analysis {
  analysis_id: string;
  status: "pending" | "running" | "done" | "error";
  query: string;
  created_at: string;
  updated_at: string;
  filename: string;
  confidence_score: number | null;
}

function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  }
  return baseUrl.replace(/\/$/, "");
}

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getStatusBadge(status: Analysis["status"]) {
  switch (status) {
    case "done":
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-quanta-gold/10 px-2.5 py-1 text-xs font-medium text-quanta-gold">
          <CheckCircle strokeWidth={1.5} className="size-3.5" aria-hidden />
          Terminé
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-400">
          <AlertCircle strokeWidth={1.5} className="size-3.5" aria-hidden />
          Erreur
        </span>
      );
    case "running":
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-quanta-cyan/10 px-2.5 py-1 text-xs font-medium text-quanta-cyan">
          <Loader2 strokeWidth={1.5} className="size-3.5 animate-spin" aria-hidden />
          En cours
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-quanta-muted/10 px-2.5 py-1 text-xs font-medium text-quanta-muted">
          <Clock strokeWidth={1.5} className="size-3.5" aria-hidden />
          En attente
        </span>
      );
  }
}

function getConfidenceDisplay(score: number | null): string {
  if (score === null) return "—";
  return `${Math.round(score * 100)}%`;
}

function getConfidenceColor(score: number | null): string {
  if (score === null) return "text-quanta-muted";
  if (score >= 0.8) return "text-quanta-gold";
  if (score >= 0.6) return "text-quanta-cyan";
  return "text-quanta-muted";
}

export default function HistoryPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [isLoadingAnalyses, setIsLoadingAnalyses] = useState(true);
  const [downloadingTheme, setDownloadingTheme] = useState<"dark" | "light" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;

    const fetchAnalyses = async () => {
      try {
        setIsLoadingAnalyses(true);
        setError(null);
        const baseUrl = getApiBaseUrl();
        const response = await fetch(`${baseUrl}/history`, {
          credentials: "include",
        });

        if (!response.ok) {
          throw new Error(`Erreur ${response.status}`);
        }

        const data = (await response.json()) as { analyses: Analysis[] };
        setAnalyses(data.analyses);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur de chargement");
      } finally {
        setIsLoadingAnalyses(false);
      }
    };

    fetchAnalyses();
  }, [isAuthenticated]);

  const handleDownloadPdf = async (analysisId: string, theme: "dark" | "light") => {
    try {
      setDownloadingTheme(theme);
      const baseUrl = getApiBaseUrl();
      const response = await fetch(`${baseUrl}/report/${analysisId}?theme=${theme}`, {
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(`Erreur ${response.status}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `rapport_quanta_${analysisId.slice(0, 8)}_${theme}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Erreur téléchargement PDF:", e);
    } finally {
      setDownloadingTheme(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-2">
          <Loader2 strokeWidth={1.5} className="size-6 animate-spin text-quanta-gold" />
          <span className="font-sans text-sm text-quanta-muted">Chargement...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="font-sans text-sm text-quanta-muted">Vous devez être connecté pour accéder à cette page.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-quanta-void px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-4xl">
        <div className="mb-8">
          <h1 className="font-sans text-2xl font-semibold text-quanta-primary">
            Mes analyses
          </h1>
          <p className="mt-2 font-sans text-sm text-quanta-muted">
            Historique de vos analyses statistiques
          </p>
        </div>

        {isLoadingAnalyses ? (
          <div className="flex items-center justify-center py-12">
            <div className="flex items-center gap-2">
              <Loader2 strokeWidth={1.5} className="size-6 animate-spin text-quanta-gold" />
              <span className="font-sans text-sm text-quanta-muted">Chargement de l'historique...</span>
            </div>
          </div>
        ) : error ? (
          <div className="rounded-quanta border border-quanta-border-subtle bg-quanta-surface px-6 py-4">
            <p className="font-sans text-sm text-red-400">{error}</p>
          </div>
        ) : analyses.length === 0 ? (
          <div className="rounded-quanta border border-quanta-border-subtle bg-quanta-surface px-6 py-12 text-center">
            <Clock strokeWidth={1.5} className="mx-auto mb-4 size-12 text-quanta-muted" aria-hidden />
            <p className="font-sans text-base text-quanta-primary">
              Aucune analyse pour le moment
            </p>
            <p className="mt-2 font-sans text-sm text-quanta-muted">
              Uploadez un fichier et lancez votre première analyse pour voir l'historique ici.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {analyses.map((analysis) => (
              <div
                key={analysis.analysis_id}
                className="rounded-quanta border border-quanta-border-subtle bg-quanta-surface px-6 py-4 transition-colors hover:bg-quanta-elevated"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <h3 className="font-sans text-base font-medium text-quanta-primary">
                        {analysis.filename}
                      </h3>
                      {getStatusBadge(analysis.status)}
                    </div>
                    
                    {analysis.query && (
                      <p className="font-sans text-sm text-quanta-muted">
                        Requête : {analysis.query}
                      </p>
                    )}
                    
                    <div className="flex flex-wrap items-center gap-4 text-xs">
                      <span className="font-sans text-quanta-muted">
                        {formatDate(analysis.created_at)}
                      </span>
                      {analysis.status === "done" && analysis.confidence_score !== null && (
                        <span className={`font-sans font-medium ${getConfidenceColor(analysis.confidence_score)}`}>
                          Score de confiance : {getConfidenceDisplay(analysis.confidence_score)}
                        </span>
                      )}
                    </div>
                  </div>

                  {analysis.status === "done" && (
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <button
                        type="button"
                        disabled={downloadingTheme !== null}
                        onClick={() => {
                          void handleDownloadPdf(analysis.analysis_id, "dark");
                        }}
                        aria-label={
                          downloadingTheme === "dark"
                            ? "Génération du rapport en cours"
                            : "Télécharger le rapport sombre"
                        }
                        className="inline-flex items-center justify-center gap-2 rounded-quanta border border-quanta-border-active bg-quanta-surface px-4 py-2 font-sans text-sm font-medium text-quanta-gold transition-colors hover:bg-quanta-elevated disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Download
                          strokeWidth={1.5}
                          className="size-4 shrink-0"
                          aria-hidden
                        />
                        {downloadingTheme === "dark" ? "Génération..." : "Rapport Dark"}
                      </button>
                      <button
                        type="button"
                        disabled={downloadingTheme !== null}
                        onClick={() => {
                          void handleDownloadPdf(analysis.analysis_id, "light");
                        }}
                        aria-label={
                          downloadingTheme === "light"
                            ? "Génération du rapport en cours"
                            : "Télécharger le rapport académique"
                        }
                        className="inline-flex items-center justify-center gap-2 rounded-quanta border border-quanta-border-active bg-quanta-surface px-4 py-2 font-sans text-sm font-medium text-quanta-gold transition-colors hover:bg-quanta-elevated disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <FileText
                          strokeWidth={1.5}
                          className="size-4 shrink-0"
                          aria-hidden
                        />
                        {downloadingTheme === "light" ? "Génération..." : "Rapport Académique"}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
