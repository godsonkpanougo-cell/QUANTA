"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion } from "framer-motion";

import { cn } from "@/lib/utils";
import { useAnalysisSteps, StepVisualState } from "@/app/hooks/useAnalysisSteps";

const POLL_INTERVAL_MS = 2000;
const COMPLETE_DELAY_MS = 500;
const POLL_TIMEOUT_MS = 300000; // 5 minutes (300 secondes)
const MAX_CONSECUTIVE_POLL_FAILURES = 3; // tolère une micro-coupure réseau avant d'abandonner
const TRANSIENT_ERROR_GRACE_MS = 8000; // fenêtre worker→fallback : "error" peut repasser à "running"
const POLL_BACKOFF_FACTOR = 2; // double l'intervalle après chaque échec réseau

/* Chargé en lazy : three.js n'arrive dans le bundle que quand une analyse démarre */
const MorphBlob = dynamic(
  () => import("@/app/components/MorphBlob").then((m) => m.MorphBlob),
  {
    ssr: false,
    loading: () => (
      <div
        aria-hidden
        className="size-full animate-pulse rounded-full bg-[radial-gradient(circle,rgba(0,212,255,0.10),transparent_65%)]"
      />
    ),
  },
);

type AnalysisStatus = "pending" | "running" | "done" | "error" | "cancelled";

interface AnalysisStatusResponse {
  status: "pending" | "running" | "done" | "error" | "cancelled";
  result?: unknown;
  error?: string;
}

/* Erreur définitive (session expirée) : inutile de retenter le poll. */
class AuthError extends Error {}

/* Le backend renvoie parfois un traceback Python brut dans `error` ;
   on ne l'affiche jamais tel quel à l'utilisateur. */
function sanitizeStatusError(raw: string | undefined): string {
  if (!raw) {
    return "Une erreur est survenue pendant l'analyse.";
  }
  const looksLikeTraceback =
    /Traceback|KeyError|raise |File "/.test(raw) || raw.includes("\n");
  if (looksLikeTraceback || raw.length > 300) {
    return "L'analyse a échoué côté serveur. Le service génératif est peut-être momentanément indisponible — réessayez dans quelques instants.";
  }
  return raw;
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
    throw new AuthError("Connectez-vous pour continuer.");
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
    let consecutivePollFailures = 0;
    let transientError: { message: string; firstSeenAt: number } | null = null;
    let nextDelayMs = POLL_INTERVAL_MS;

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

        consecutivePollFailures = 0;
        nextDelayMs = POLL_INTERVAL_MS;

        if (data.status === "done") {
          finishWithSuccess(data.result ?? null);
          return;
        }

        if (data.status === "error") {
          /* Fenêtre transitoire worker→fallback (~1-5 s) : le statut peut
             repasser à "running" quand le fallback in-memory prend le relais.
             On ne fige l'erreur qu'après un délai de grâce. */
          if (transientError === null) {
            transientError = {
              message: sanitizeStatusError(data.error),
              firstSeenAt: Date.now(),
            };
          } else if (
            Date.now() - transientError.firstSeenAt >=
            TRANSIENT_ERROR_GRACE_MS
          ) {
            finishWithError(transientError.message);
          }
          return;
        }

        if (data.status === "cancelled") {
          finishWithError("Analyse annulée par l'utilisateur.");
          return;
        }

        /* Statut redevenu pending/running : la panne transitoire est passée. */
        transientError = null;
      } catch (error) {
        if (error instanceof AuthError) {
          finishWithError(error.message);
          return;
        }

        /* Tolérance réseau : N échecs consécutifs avant d'abandonner le poll. */
        consecutivePollFailures += 1;
        nextDelayMs = POLL_INTERVAL_MS * POLL_BACKOFF_FACTOR;
        if (consecutivePollFailures >= MAX_CONSECUTIVE_POLL_FAILURES) {
          const cause =
            error instanceof Error
              ? error.message
              : "Impossible de contacter le serveur d'analyse.";
          finishWithError(
            `Connexion au serveur perdue après ${MAX_CONSECUTIVE_POLL_FAILURES} tentatives (${cause}). Vérifiez votre connexion puis relancez l'analyse.`,
          );
        }
      }
    };

    const pollWithTimeout = async () => {
      const deadline = Date.now() + POLL_TIMEOUT_MS;
      
      while (Date.now() < deadline && !finishedRef.current) {
        await pollStatus();
        
        if (finishedRef.current) {
          return;
        }
        
        await new Promise(resolve => setTimeout(resolve, nextDelayMs));
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
    <div className="glass rounded-hero p-8">
      <div className="mb-6 flex items-center justify-between gap-4">
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

      {/* ── Sphère polymorphe : une morphologie par étape ── */}
      <div className="flex flex-col items-center gap-2 py-4">
        <div className="size-60 sm:size-72">
          <MorphBlob
            step={currentStep}
            done={status === "done"}
            error={status === "error"}
          />
        </div>
        <AnimatePresence mode="wait">
          <motion.p
            key={`current-${currentStep}-${status}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={MOTION_TRANSITION}
            className={cn(
              "mt-2 font-display text-2xl font-light",
              status === "error" ? "text-quanta-error" : "text-quanta-cyan",
            )}
          >
            {status === "done"
              ? "Rapport prêt"
              : (steps[Math.min(currentStep, steps.length - 1)] ?? "")}
          </motion.p>
        </AnimatePresence>
        <p className="hud-label text-quanta-muted">
          Étape {Math.min(currentStep + 1, steps.length)} / {steps.length}
        </p>
      </div>

      <div className="mt-6 flex flex-row items-start gap-2 overflow-x-auto border-t border-quanta-border-subtle pt-6">
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
