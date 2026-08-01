"use client";

import { useCallback, useState } from "react";

import { AnalysisProgress } from "@/app/components/AnalysisProgress";
import { AnalysisResults } from "@/app/components/AnalysisResults";
import { UploadZone } from "@/app/components/UploadZone";

const QUERY_EXAMPLES = [
  "Comparer le revenu entre régions",
  "Analyser l'association genre × diplôme",
  "Prédire le salaire par l'expérience",
] as const;

type Phase = "idle" | "uploading" | "analyzing" | "done" | "error";

interface UploadResponse {
  file_id: string;
}

interface AnalyzeResponse {
  analysis_id: string;
}

function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  }
  return baseUrl.replace(/\/$/, "");
}

async function parseErrorResponse(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") {
      return data.detail;
    }
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((entry) => {
          if (typeof entry === "object" && entry !== null && "msg" in entry) {
            return String((entry as { msg: unknown }).msg);
          }
          return String(entry);
        })
        .join(" ");
    }
  } catch {
    // ignore JSON parse errors
  }
  return `Erreur HTTP ${response.status}`;
}

export function HomePage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [result, setResult] = useState<unknown | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canAnalyze = selectedFile !== null;
  const isUploading = phase === "uploading";

  const resetAll = useCallback(() => {
    setPhase("idle");
    setAnalysisId(null);
    setResult(null);
    setErrorMessage(null);
    setSelectedFile(null);
    setQuery("");
  }, []);

  const retry = useCallback(() => {
    setPhase("idle");
    setAnalysisId(null);
    setResult(null);
    setErrorMessage(null);
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!selectedFile) {
      return;
    }

    try {
      setPhase("uploading");
      setErrorMessage(null);
      setResult(null);
      setAnalysisId(null);

      const baseUrl = getApiBaseUrl();

      const formData = new FormData();
      formData.append("file", selectedFile);

      const uploadResponse = await fetch(`${baseUrl}/upload`, {
        method: "POST",
        body: formData,
      });

      if (!uploadResponse.ok) {
        throw new Error(await parseErrorResponse(uploadResponse));
      }

      const uploadData = (await uploadResponse.json()) as UploadResponse;
      const fileId = uploadData.file_id;

      const analyzeResponse = await fetch(`${baseUrl}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_id: fileId, query: query.trim() }),
      });

      if (!analyzeResponse.ok) {
        throw new Error(await parseErrorResponse(analyzeResponse));
      }

      const analyzeData = (await analyzeResponse.json()) as AnalyzeResponse;
      setAnalysisId(analyzeData.analysis_id);
      setPhase("analyzing");
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Une erreur est survenue pendant l'analyse.";
      setErrorMessage(message);
      setPhase("error");
    }
  }, [query, selectedFile]);

  const handleLoadSample = useCallback(async () => {
    try {
      setErrorMessage(null);
      const response = await fetch("/sample_data.csv");
      if (!response.ok) {
        throw new Error("Impossible de charger le fichier d'exemple.");
      }
      const blob = await response.blob();
      const file = new File([blob], "sample_data.csv", {
        type: "text/csv",
      });
      setSelectedFile(file);
      setQuery("Analyser automatiquement ce dataset");
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Impossible de charger le fichier d'exemple.";
      setErrorMessage(message);
      setPhase("error");
    }
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-quanta-void">
      <div className="w-full space-y-8 px-6 text-center">
        <h1 className="font-display text-5xl font-light tracking-widest text-quanta-gold">
          QUANTA
        </h1>
        <p className="mx-auto max-w-md font-sans text-sm text-quanta-secondary">
          Tu déposes ta base. Tu reçois un rapport que tu peux signer.
        </p>
        <div className="mx-auto h-px w-16 bg-quanta-gold opacity-30" />

        <div className="mx-auto w-full max-w-xl space-y-4 text-left">
          {phase === "analyzing" && analysisId ? (
            <AnalysisProgress
              analysisId={analysisId}
              onComplete={(res) => {
                setResult(res);
                setPhase("done");
              }}
              onError={(msg) => {
                setErrorMessage(msg);
                setPhase("error");
              }}
            />
          ) : null}

          {phase === "done" && result !== null && analysisId ? (
            <AnalysisResults
              result={result}
              analysisId={analysisId}
              onNewAnalysis={resetAll}
            />
          ) : null}

          {phase === "error" ? (
            <div className="space-y-4 text-center">
              <p className="font-sans text-sm text-quanta-error">
                {errorMessage ?? "Une erreur est survenue."}
              </p>
              <button
                type="button"
                onClick={retry}
                className="rounded-quanta bg-quanta-gold px-8 py-3 font-sans text-sm font-medium text-quanta-void"
              >
                Réessayer
              </button>
            </div>
          ) : null}

          {phase === "idle" || phase === "uploading" ? (
            <>
              <UploadZone
                selectedFile={selectedFile}
                onFileSelect={setSelectedFile}
              />

              <div className="text-center">
                <button
                  type="button"
                  onClick={() => {
                    void handleLoadSample();
                  }}
                  className="font-sans text-xs text-quanta-muted transition-colors hover:text-quanta-cyan cursor-pointer"
                >
                  Pas de fichier ? Tester avec un exemple →
                </button>
              </div>

              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                rows={3}
                placeholder={
                  "Optionnel — Ex: comparer le revenu entre régions...\n" +
                  "Si vide, QUANTA analyse automatiquement."
                }
                className="w-full resize-none rounded-quanta border border-quanta-border-subtle bg-quanta-elevated px-4 py-3 font-sans text-sm text-quanta-primary placeholder:text-quanta-muted focus:border-quanta-cyan focus:shadow-[0_0_0_3px_rgba(0,212,255,0.08)] focus:outline-none"
              />

              <div className="flex flex-wrap justify-center gap-2">
                {QUERY_EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => setQuery(example)}
                    className="cursor-pointer rounded-full border border-quanta-border-subtle bg-quanta-surface px-3 py-1 font-sans text-xs text-quanta-muted"
                  >
                    {example}
                  </button>
                ))}
              </div>

              <div className="text-center">
                <button
                  type="button"
                  disabled={!canAnalyze || isUploading}
                  onClick={() => {
                    void handleAnalyze();
                  }}
                  className="rounded-quanta bg-quanta-gold px-8 py-3 font-sans text-sm font-medium text-quanta-void transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {isUploading ? "Envoi..." : "Analyser"}
                </button>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </main>
  );
}
