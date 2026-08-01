"use client";

import { useCallback, useState } from "react";
import { Download, FileText } from "lucide-react";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { ConfidenceScore } from "@/app/components/ConfidenceScore";

interface ConfidenceScoreData {
  score_global?: number;
  niveau?: string;
  points_de_vigilance?: string[];
}

interface DiagnosisData {
  n_rows?: number;
  n_cols?: number;
  dataset_type?: string;
}

interface InferenceData {
  action_executed?: string;
}

interface AnalysisPayload {
  confidence_score?: ConfidenceScoreData;
  diagnosis?: DiagnosisData;
  inference?: InferenceData;
  filename?: string;
}

interface InterpretationPrincipale {
  niveau_technique?: string;
  niveau_analytique?: string;
  niveau_decisionnel?: string;
}

interface Interpretation {
  llm_available?: boolean;
  resume_executif?: string;
  interpretation_principale?: InterpretationPrincipale;
}

interface AnalysisResult {
  analysis?: AnalysisPayload;
  confidence_score?: ConfidenceScoreData;
  interpretation?: Interpretation;
}

export interface AnalysisResultsProps {
  result: unknown;
  analysisId: string;
  onNewAnalysis: () => void;
}

const INTERPRETATION_LEVELS = [
  {
    id: "technique",
    label: "Niveau technique",
    key: "niveau_technique" as const,
  },
  {
    id: "analytique",
    label: "Niveau analytique",
    key: "niveau_analytique" as const,
  },
  {
    id: "decisionnel",
    label: "Niveau décisionnel",
    key: "niveau_decisionnel" as const,
  },
] as const;

function isAnalysisResult(value: unknown): value is AnalysisResult {
  return typeof value === "object" && value !== null;
}

function resolveResultPayload(result: AnalysisResult): {
  confidence: ConfidenceScoreData;
  analysis: AnalysisPayload;
  interpretation: Interpretation;
} {
  const interpretation = result.interpretation ?? {};
  const analysis = result.analysis ?? {};

  if (result.analysis) {
    return {
      confidence: analysis.confidence_score ?? {},
      analysis,
      interpretation,
    };
  }

  return {
    confidence: result.confidence_score ?? {},
    analysis: {},
    interpretation,
  };
}

function formatActionExecuted(actionExecuted: string | undefined): string {
  switch (actionExecuted) {
    case "compare_groups_2":
      return "Comparaison 2 groupes";
    case "compare_groups_k":
      return "Comparaison multi-groupes";
    case "regression_ols":
      return "Régression OLS";
    case "regression_logistic":
      return "Régression logistique";
    case "correlation":
      return "Corrélation";
    case "association":
      return "Association";
    case "descriptive_only":
      return "Analyse descriptive";
    default:
      return actionExecuted?.trim() || "—";
  }
}

export function AnalysisResults({
  result,
  analysisId,
  onNewAnalysis,
}: AnalysisResultsProps) {
  const [downloadingTheme, setDownloadingTheme] = useState<
    "dark" | "light" | null
  >(null);

  const handleDownloadPdf = useCallback(
    async (theme: "dark" | "light") => {
      if (!analysisId || downloadingTheme !== null) {
        return;
      }

      const baseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
      if (!baseUrl) {
        return;
      }

      setDownloadingTheme(theme);
      try {
        const response = await fetch(
          `${baseUrl}/report/${analysisId}?theme=${theme}`,
          { method: "GET" },
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const suffix = theme === "light" ? "academique" : "dark";
        a.download = `rapport_quanta_${suffix}_${analysisId.slice(0, 8)}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      } catch {
        // Le bouton se réactive dans finally ; pas de toast dédié en V1.
      } finally {
        setDownloadingTheme(null);
      }
    },
    [analysisId, downloadingTheme],
  );

  const data = isAnalysisResult(result) ? result : {};
  const { confidence, analysis, interpretation } = resolveResultPayload(data);
  const principale = interpretation.interpretation_principale ?? {};
  const diagnosis = analysis.diagnosis ?? {};
  const inference = analysis.inference ?? {};

  const scoreGlobal = confidence.score_global;
  const niveau = confidence.niveau ?? "—";
  const vigilancePoints = confidence.points_de_vigilance ?? [];
  const llmAvailable = interpretation.llm_available !== false;
  const metadataItems = [
    { label: "Dataset", value: analysis.filename ?? "—" },
    {
      label: "Lignes",
      value: typeof diagnosis.n_rows === "number" ? String(diagnosis.n_rows) : "—",
    },
    {
      label: "Colonnes",
      value: typeof diagnosis.n_cols === "number" ? String(diagnosis.n_cols) : "—",
    },
    { label: "Type", value: diagnosis.dataset_type ?? "—" },
    {
      label: "Test appliqué",
      value: formatActionExecuted(inference.action_executed),
    },
  ];

  const accordionLevels = INTERPRETATION_LEVELS.filter(
    ({ key }) => (principale[key] ?? "").trim().length > 0,
  );

  return (
    <div className="space-y-8 text-left">
      <div className="text-center">
        <span className="font-sans text-sm font-medium tracking-wide text-quanta-gold">
          Analyse terminée
        </span>
      </div>

      <div className="py-2">
        {typeof scoreGlobal === "number" ? (
          <ConfidenceScore
            score={scoreGlobal}
            niveau={niveau}
            pointsDeVigilance={vigilancePoints}
          />
        ) : (
          <p className="text-center font-display text-7xl font-light text-quanta-muted">
            —
          </p>
        )}
      </div>

      <div className="rounded-card bg-quanta-surface p-4">
        <h3 className="mb-4 font-sans text-sm font-medium tracking-wide text-quanta-primary">
          Métadonnées de l'analyse
        </h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {metadataItems.map(({ label, value }) => (
            <div key={label} className="space-y-1.5">
              <p className="font-mono text-xs uppercase tracking-widest text-quanta-muted">
                {label}
              </p>
              <p className="font-sans text-sm text-quanta-primary">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {!llmAvailable ? (
        <p className="text-center font-sans text-sm text-quanta-muted">
          Interprétation LLM indisponible — résultats statistiques bruts
          disponibles
        </p>
      ) : null}

      {llmAvailable && interpretation.resume_executif ? (
        <div className="rounded-card bg-quanta-surface p-6">
          <p className="font-sans text-sm leading-relaxed text-quanta-primary">
            {interpretation.resume_executif}
          </p>
        </div>
      ) : null}

      {llmAvailable && accordionLevels.length > 0 ? (
        <Accordion
          type="single"
          collapsible
          className="rounded-card border border-quanta-border-subtle bg-quanta-surface px-4"
        >
          {accordionLevels.map(({ id, label, key }) => (
            <AccordionItem
              key={id}
              value={id}
              className="border-quanta-border-subtle"
            >
              <AccordionTrigger className="font-sans text-sm text-quanta-primary hover:text-quanta-gold hover:no-underline">
                {label}
              </AccordionTrigger>
              <AccordionContent className="pb-4">
                <div className="rounded-card bg-quanta-elevated px-4 py-3 font-sans text-sm leading-relaxed text-quanta-secondary">
                  {principale[key]}
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      ) : null}

      <div className="flex flex-col items-center gap-3">
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            disabled={downloadingTheme !== null || !analysisId}
            onClick={() => {
              void handleDownloadPdf("dark");
            }}
            className="inline-flex items-center justify-center gap-2 rounded-quanta border border-quanta-border-active bg-quanta-surface px-8 py-3 font-sans text-sm font-medium text-quanta-gold transition-colors hover:bg-quanta-elevated disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Download
              strokeWidth={1.5}
              className="size-4 shrink-0"
              aria-hidden
            />
            {downloadingTheme === "dark"
              ? "Génération en cours..."
              : "Rapport Dark"}
          </button>

          <button
            type="button"
            disabled={downloadingTheme !== null || !analysisId}
            onClick={() => {
              void handleDownloadPdf("light");
            }}
            className="inline-flex items-center justify-center gap-2 rounded-quanta border border-quanta-border-active bg-quanta-surface px-8 py-3 font-sans text-sm font-medium text-quanta-gold transition-colors hover:bg-quanta-elevated disabled:cursor-not-allowed disabled:opacity-40"
          >
            <FileText
              strokeWidth={1.5}
              className="size-4 shrink-0"
              aria-hidden
            />
            {downloadingTheme === "light"
              ? "Génération en cours..."
              : "Rapport Académique"}
          </button>
        </div>

        <button
          type="button"
          onClick={onNewAnalysis}
          className="rounded-quanta bg-quanta-gold px-8 py-3 font-sans text-sm font-medium text-quanta-void transition-opacity hover:opacity-90"
        >
          Nouvelle analyse
        </button>
      </div>
    </div>
  );
}
