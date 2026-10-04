"use client";

import { useCallback, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { Download, FileText } from "lucide-react";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { ConfidenceScore } from "@/app/components/ConfidenceScore";
import { DatasetSnapshot } from "@/app/components/DatasetSnapshot";

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

const REVEAL_TRANSITION = {
  duration: 0.45,
  ease: [0.16, 1, 0.3, 1] as const,
};

function RevealBlock({
  index,
  children,
}: {
  index: number;
  children: ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...REVEAL_TRANSITION, delay: 0.1 + index * 0.09 }}
    >
      {children}
    </motion.div>
  );
}

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
          { method: "GET", credentials: "include" },
        );

        if (response.status === 401) {
          throw new Error("Connectez-vous pour continuer.");
        }
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

  /* Snapshot affiché dès qu'on connaît au moins les dimensions du dataset */
  const hasSnapshotData =
    typeof diagnosis.n_rows === "number" || typeof diagnosis.n_cols === "number";

  return (
    <div className="space-y-8 text-left">
      <RevealBlock index={0}>
        <div className="flex flex-col items-center gap-2 text-center">
          <span className="hud-label text-quanta-muted">Analyse terminée</span>
          <h2 className="font-display text-3xl font-light text-quanta-primary">
            Vos résultats sont prêts
          </h2>
          <div aria-hidden className="h-px w-12 bg-quanta-gold/40" />
        </div>
      </RevealBlock>

      <RevealBlock index={1}>
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
      </RevealBlock>

      <RevealBlock index={2}>
        {hasSnapshotData ? (
          <DatasetSnapshot
            rows={diagnosis.n_rows}
            cols={diagnosis.n_cols}
            datasetType={diagnosis.dataset_type}
          />
        ) : null}
      </RevealBlock>

      <RevealBlock index={3}>
        <div className="rounded-card border border-quanta-border-subtle bg-quanta-surface p-5">
          <p className="hud-label mb-4 text-quanta-muted">Métadonnées de l&apos;analyse</p>
          <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
            {metadataItems.map(({ label, value }) => (
              <div
                key={label}
                className="border-l border-quanta-border-subtle pl-3"
              >
                <p className="font-sans text-[10px] uppercase tracking-[0.14em] text-quanta-muted">
                  {label}
                </p>
                <p
                  className="mt-1 truncate font-mono text-sm text-quanta-primary"
                  title={value}
                >
                  {value}
                </p>
              </div>
            ))}
          </div>
        </div>
      </RevealBlock>

      {!llmAvailable ? (
        <RevealBlock index={4}>
          <p className="rounded-card border border-quanta-border-subtle bg-quanta-elevated px-4 py-3 text-center font-sans text-sm text-quanta-secondary">
            Interprétation LLM indisponible — résultats statistiques bruts
            disponibles dans le rapport PDF.
          </p>
        </RevealBlock>
      ) : null}

      {llmAvailable && interpretation.resume_executif ? (
        <RevealBlock index={4}>
          <div className="rounded-card border border-quanta-border-subtle bg-quanta-surface p-6">
            <p className="hud-label mb-3 text-quanta-muted">Résumé exécutif</p>
            <p className="border-l-2 border-quanta-gold/50 pl-4 font-sans text-sm leading-relaxed text-quanta-primary">
              {interpretation.resume_executif}
            </p>
          </div>
        </RevealBlock>
      ) : null}

      {llmAvailable && accordionLevels.length > 0 ? (
        <RevealBlock index={5}>
          <p className="hud-label mb-3 text-quanta-muted">Interprétation par niveau</p>
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
                <AccordionTrigger className="font-sans text-sm text-quanta-primary transition-colors hover:text-quanta-gold-2 hover:no-underline">
                  {label}
                </AccordionTrigger>
                <AccordionContent className="pb-4">
                  <div className="rounded-quanta bg-quanta-elevated px-4 py-3 font-sans text-sm leading-relaxed text-quanta-secondary">
                    {principale[key]}
                  </div>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </RevealBlock>
      ) : null}

      <RevealBlock index={6}>
        <div className="flex flex-col items-center gap-4 border-t border-quanta-border-subtle pt-8">
          <p className="hud-label text-quanta-muted">Rapport d&apos;analyse — PDF signable</p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              disabled={downloadingTheme !== null || !analysisId}
              onClick={() => {
                void handleDownloadPdf("light");
              }}
              aria-label={downloadingTheme === "light" ? "Génération du rapport en cours" : "Télécharger le rapport académique"}
              className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-quanta bg-quanta-gold px-6 py-3 font-sans text-sm font-medium text-quanta-void transition-quanta hover:bg-quanta-gold-2 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <FileText
                strokeWidth={1.5}
                className="size-4 shrink-0"
                aria-hidden
              />
              {downloadingTheme === "light"
                ? "Génération en cours…"
                : "Rapport académique"}
            </button>

            <button
              type="button"
              disabled={downloadingTheme !== null || !analysisId}
              onClick={() => {
                void handleDownloadPdf("dark");
              }}
              aria-label={downloadingTheme === "dark" ? "Génération du rapport en cours" : "Télécharger le rapport sombre"}
              className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-quanta border border-quanta-border-subtle px-6 py-3 font-sans text-sm text-quanta-primary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Download
                strokeWidth={1.5}
                className="size-4 shrink-0"
                aria-hidden
              />
              {downloadingTheme === "dark"
                ? "Génération en cours…"
                : "Rapport dark"}
            </button>
          </div>

          <button
            type="button"
            onClick={onNewAnalysis}
            className="cursor-pointer font-sans text-sm text-quanta-secondary transition-quanta hover:text-quanta-cyan"
          >
            ← Nouvelle analyse
          </button>
        </div>
      </RevealBlock>
    </div>
  );
}
