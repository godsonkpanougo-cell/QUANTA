"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { cn } from "@/lib/utils";

const STEPS = [
  "Réception du fichier",
  "Diagnostic structurel",
  "Nettoyage des données",
  "Sélection des tests",
  "Calculs statistiques",
  "Vérification des conditions",
  "Interprétation",
  "Finalisation du rapport",
] as const;

const POLL_INTERVAL_MS = 2000;
const STEP_INTERVAL_MS = 3000;
const COMPLETE_DELAY_MS = 500;
const MAX_RUNNING_STEP = 6;
const FINAL_STEP = 8;

type AnalysisStatus = "running" | "done" | "error";

type StepVisualState = "past" | "active" | "future";

interface AnalysisStatusResponse {
  status: "pending" | "running" | "done" | "error";
  result?: unknown;
  error?: string;
}

export interface AnalysisProgressProps {
  analysisId: string;
  onComplete: (result: unknown) => void;
  onError: (message: string) => void;
}

const MOTION_TRANSITION = {
  duration: 0.3,
  ease: [0.4, 0, 0.2, 1] as const,
};

function getStepState(
  index: number,
  currentStep: number,
  status: AnalysisStatus,
): StepVisualState {
  if (status === "done" || index < currentStep) {
    return "past";
  }
  if (index === currentStep) {
    return "active";
  }
  return "future";
}

function getApiBaseUrl(): string | null {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) {
    return null;
  }
  return baseUrl.replace(/\/$/, "");
}

async function fetchAnalysisStatus(
  analysisId: string,
): Promise<AnalysisStatusResponse> {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  }

  const response = await fetch(`${baseUrl}/status/${analysisId}`);

  if (!response.ok) {
    throw new Error(
      `Impossible de récupérer le statut (HTTP ${response.status}).`,
    );
  }

  return response.json() as Promise<AnalysisStatusResponse>;
}

interface StepDotProps {
  state: StepVisualState;
}

function StepDot({ state }: StepDotProps) {
  if (state === "past") {
    return (
      <motion.div
        layout
        className="size-2.5 shrink-0 rounded-full bg-quanta-gold"
        transition={MOTION_TRANSITION}
      />
    );
  }

  if (state === "active") {
    return (
      <motion.div
        layout
        className="size-2.5 shrink-0 rounded-full bg-quanta-cyan"
        animate={{
          scale: [1, 1.35, 1],
          opacity: [1, 0.55, 1],
        }}
        transition={{
          duration: 1.5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />
    );
  }

  return (
    <motion.div
      layout
      className="size-2.5 shrink-0 rounded-full border border-quanta-muted bg-transparent"
      transition={MOTION_TRANSITION}
    />
  );
}

interface StepConnectorProps {
  isPast: boolean;
}

function StepConnector({ isPast }: StepConnectorProps) {
  return (
    <div className="flex min-w-4 flex-1 items-center pt-1">
      <motion.div
        className="h-px w-full"
        animate={{
          backgroundColor: isPast ? "#C9A84C" : "rgba(85, 85, 99, 0.45)",
        }}
        transition={MOTION_TRANSITION}
      />
    </div>
  );
}

export function AnalysisProgress({
  analysisId,
  onComplete,
  onError,
}: AnalysisProgressProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [status, setStatus] = useState<AnalysisStatus>("running");

  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  const inProgressRef = useRef(true);
  const finishedRef = useRef(false);

  onCompleteRef.current = onComplete;
  onErrorRef.current = onError;

  useEffect(() => {
    inProgressRef.current = true;
    finishedRef.current = false;
    setCurrentStep(0);
    setStatus("running");

    let pollIntervalId: ReturnType<typeof setInterval> | null = null;
    let stepIntervalId: ReturnType<typeof setInterval> | null = null;
    let completeTimeoutId: ReturnType<typeof setTimeout> | null = null;

    const finishWithError = (message: string) => {
      if (finishedRef.current) {
        return;
      }
      finishedRef.current = true;
      inProgressRef.current = false;
      setStatus("error");
      onErrorRef.current(message);
    };

    const finishWithSuccess = (result: unknown) => {
      if (finishedRef.current) {
        return;
      }
      finishedRef.current = true;
      inProgressRef.current = false;
      setCurrentStep(FINAL_STEP);
      setStatus("done");
      completeTimeoutId = setTimeout(() => {
        onCompleteRef.current(result);
      }, COMPLETE_DELAY_MS);
    };

    const pollStatus = async () => {
      if (finishedRef.current) {
        return;
      }

      try {
        const data = await fetchAnalysisStatus(analysisId);

        if (finishedRef.current) {
          return;
        }

        if (data.status === "done") {
          finishWithSuccess(data.result ?? null);
          return;
        }

        if (data.status === "error") {
          finishWithError(
            data.error ?? "Une erreur est survenue pendant l'analyse.",
          );
          return;
        }

        if (data.status === "running" || data.status === "pending") {
          inProgressRef.current = true;
        }
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Impossible de contacter le serveur d'analyse.";
        finishWithError(message);
      }
    };

    void pollStatus();
    pollIntervalId = setInterval(() => {
      void pollStatus();
    }, POLL_INTERVAL_MS);

    stepIntervalId = setInterval(() => {
      if (!inProgressRef.current || finishedRef.current) {
        return;
      }
      setCurrentStep((previous) => Math.min(previous + 1, MAX_RUNNING_STEP));
    }, STEP_INTERVAL_MS);

    return () => {
      if (pollIntervalId) {
        clearInterval(pollIntervalId);
      }
      if (stepIntervalId) {
        clearInterval(stepIntervalId);
      }
      if (completeTimeoutId) {
        clearTimeout(completeTimeoutId);
      }
    };
  }, [analysisId]);

  return (
    <div className="rounded-card bg-quanta-surface p-8">
      <h2 className="mb-8 text-center font-display text-xl font-light text-quanta-primary">
        Analyse en cours...
      </h2>

      <div className="flex flex-row items-start gap-2 overflow-x-auto">
        {STEPS.map((label, index) => {
          const stepState = getStepState(index, currentStep, status);
          const connectorPast = index < currentStep || status === "done";

          return (
            <Fragment key={label}>
              <motion.div
                layout
                className="flex min-w-[88px] max-w-[120px] flex-col items-center gap-2"
                transition={MOTION_TRANSITION}
              >
                <StepDot state={stepState} />
                <AnimatePresence mode="wait">
                  <motion.p
                    key={`${label}-${stepState}`}
                    initial={{ opacity: 0.6, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0.6, y: -4 }}
                    transition={MOTION_TRANSITION}
                    className={cn(
                      "text-center font-sans text-sm leading-snug",
                      stepState === "past" && "text-quanta-secondary",
                      stepState === "active" &&
                        "font-medium text-quanta-cyan",
                      stepState === "future" && "text-quanta-muted",
                    )}
                  >
                    {label}
                  </motion.p>
                </AnimatePresence>
              </motion.div>

              {index < STEPS.length - 1 ? (
                <StepConnector isPast={connectorPast} />
              ) : null}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
