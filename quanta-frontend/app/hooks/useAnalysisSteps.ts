import { useEffect, useState, useRef } from "react";

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

const STEP_INTERVAL_MS = 3000;
const MAX_RUNNING_STEP = 6;
const FINAL_STEP = 8;

export type StepVisualState = "past" | "active" | "future";

export function useAnalysisSteps(
  isRunning: boolean,
  isFinished: boolean,
  startTime?: string,
) {
  const [currentStep, setCurrentStep] = useState(0);
  const inProgressRef = useRef(isRunning);

  useEffect(() => {
    inProgressRef.current = isRunning;

    // Si startTime est fourni, calculer l'étape initiale en fonction du temps écoulé
    if (startTime && isRunning && !isFinished) {
      const elapsed = Date.now() - new Date(startTime).getTime();
      const initialStep = Math.min(
        Math.floor(elapsed / STEP_INTERVAL_MS),
        MAX_RUNNING_STEP
      );
      setCurrentStep(initialStep);
    } else if (!isRunning || isFinished) {
      setCurrentStep(0);
    }

    const stepIntervalId = setInterval(() => {
      if (!inProgressRef.current || isFinished) {
        return;
      }
      setCurrentStep((previous) => Math.min(previous + 1, MAX_RUNNING_STEP));
    }, STEP_INTERVAL_MS);

    return () => {
      clearInterval(stepIntervalId);
    };
  }, [isRunning, isFinished, startTime]);

  const getStepState = (index: number, status: "done" | "running" | "error" | "cancelled" | "pending"): StepVisualState => {
    if (status === "done" || index < currentStep) {
      return "past";
    }
    if (index === currentStep) {
      return "active";
    }
    return "future";
  };

  return {
    currentStep,
    steps: STEPS,
    getStepState,
    finalStep: FINAL_STEP,
  };
}
