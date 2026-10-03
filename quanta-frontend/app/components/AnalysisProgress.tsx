"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { cn } from "@/lib/utils";
import { useAnalysisSteps, StepVisualState } from "@/app/hooks/useAnalysisSteps";

const POLL_INTERVAL_MS = 2000;
const COMPLETE_DELAY_MS = 500;
const POLL_TIMEOUT_MS = 300000; // 5 minutes (300 secondes)

type AnalysisStatus = "pending" | "running" | "done" | "error" | "cancelled";

interface AnalysisStatusResponse {
  status: "pending" | "running" | "done" | "error" | "cancelled";
  result?: unknown;
  error?: string;
}

export interface AnalysisProgressProps {
  analysisId: string;
  onComplete: (result: unknown) => void;
  onError: (message: string) => void;
  onCancel?: () => void;
}

const MOTION_TRANSITION = {
  duration: 0.3,
  ease: [0.4, 0, 0.2, 1] as const,
};

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

  const response = await fetch(`${baseUrl}/status/${analysisId}`, {
    credentials: "include",
  });

  if (response.status === 401) {
    throw new Error("Connectez-vous pour continuer.");
  }
  if (!response.ok) {
    throw new Error(
      `Impossible de récupérer le statut (HTTP ${response.status}).`,
    );
  }

  return response.json() as Promise<AnalysisStatusResponse>;
}

async function cancelAnalysis(analysisId: string): Promise<void> {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  }

  const response = await fetch(`${baseUrl}/analyses/${analysisId}/cancel`, {
    method: "POST",
    credentials: "include",
  });

  if (response.status === 401) {
    throw new Error("Connectez-vous pour continuer.");
  }
  if (!response.ok) {
    throw new Error(
      `Impossible d'annuler l'analyse (HTTP ${response.status}).`,
    );
  }
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
  onCancel,
}: AnalysisProgressProps) {
  const [status, setStatus] = useState<AnalysisStatus>("running");
  const [isCancelling, setIsCancelling] = useState(false);
  const finishedRef = useRef(false);

  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  const onCancelRef = useRef(onCancel);

  onCompleteRef.current = onComplete;
  onErrorRef.current = onError;
  onCancelRef.current = onCancel;

  const { currentStep, steps, getStepState, finalStep } = useAnalysisSteps(
    status === "running" || status === "pending",
    finishedRef.current,
    undefined // Pas de startTime pour une nouvelle analyse
  );

  useEffect(() => {
    finishedRef.current = false;
    setStatus("running");

    let completeTimeoutId: ReturnType<typeof setTimeout> | null = null;

    const finishWithError = (message: string) => {
      if (finishedRef.current) {
        return;
      }
      finishedRef.current = true;
      setStatus("error");
      onErrorRef.current(message);
    };

    const finishWithSuccess = (result: unknown) => {
      if (finishedRef.current) {
        return;
      }
      finishedRef.current = true;
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

        if (data.status === "cancelled") {
          finishWithError("Analyse annulée par l'utilisateur.");
          return;
        }
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Impossible de contacter le serveur d'analyse.";
        finishWithError(message);
      }
    };

    const pollWithTimeout = async () => {
      const deadline = Date.now() + POLL_TIMEOUT_MS;
      
      while (Date.now() < deadline && !finishedRef.current) {
        await pollStatus();
        
        if (finishedRef.current) {
          return;
        }
        
        await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      
      if (!finishedRef.current) {
        finishWithError(`L'analyse a dépassé le délai maximum de ${POLL_TIMEOUT_MS / 1000} secondes.`);
      }
    };

    void pollWithTimeout();

    return () => {
      if (completeTimeoutId) {
        clearTimeout(completeTimeoutId);
      }
    };
  }, [analysisId]);

  const handleCancel = async () => {
    if (isCancelling || finishedRef.current) {
      return;
    }
    setIsCancelling(true);
    try {
      await cancelAnalysis(analysisId);
      if (onCancelRef.current) {
        onCancelRef.current();
      }
    } catch (error) {
      console.error("Erreur lors de l'annulation:", error);
      setIsCancelling(false);
    }
  };

  return (
    <div className="rounded-card border border-quanta-border-subtle bg-quanta-surface p-8">
      <div className="mb-10 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {status === "running" || status === "pending" ? (
            <span className="hud-dot" aria-hidden />
          ) : null}
          <div>
            <p className="hud-label text-quanta-muted">Pipeline d&apos;analyse</p>
            <h2 className="mt-1 font-display text-xl font-light text-quanta-primary">
              {status === "done"
                ? "Analyse terminée"
                : "Analyse en cours…"}
            </h2>
          </div>
        </div>
        {(status === "running" || status === "pending") && !finishedRef.current && (
          <button
            type="button"
            onClick={handleCancel}
            disabled={isCancelling}
            className="cursor-pointer rounded-quanta border border-quanta-border-subtle px-3.5 py-1.5 font-sans text-xs text-quanta-secondary transition-quanta hover:border-quanta-error/50 hover:text-quanta-error disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isCancelling ? "Annulation…" : "Annuler"}
          </button>
        )}
      </div>

      <div className="flex flex-row items-start gap-2 overflow-x-auto">
        {steps.map((label, index) => {
          const stepState = getStepState(index, status);
          const connectorPast = index < currentStep || status === "done";

          return (
            <Fragment key={label}>
              <motion.div
                layout
                className="flex min-w-[80px] max-w-[110px] flex-col items-center gap-3"
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
                      "text-center font-sans text-xs leading-snug",
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

              {index < steps.length - 1 ? (
                <StepConnector isPast={connectorPast} />
              ) : null}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
