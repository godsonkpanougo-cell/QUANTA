"use client";

import { useEffect, useMemo, useState } from "react";
import { animate, useMotionValue } from "framer-motion";
import { AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";

export type ConfidenceNiveau = "Élevé" | "Modéré" | "Faible" | "Très faible";

export interface ConfidenceScoreProps {
  score: number;
  niveau: ConfidenceNiveau | string;
  pointsDeVigilance: string[];
}

const ANIMATION_DURATION_S = 1.5;
const CIRCLE_SIZE_PX = 180;
const STROKE_WIDTH_PX = 2;
const CIRCLE_RADIUS_PX = (CIRCLE_SIZE_PX - STROKE_WIDTH_PX) / 2;
const CIRCLE_CIRCUMFERENCE = 2 * Math.PI * CIRCLE_RADIUS_PX;

const NO_VIGILANCE_PHRASE = "Aucun point de vigilance particulier";

function clampScore(score: number): number {
  return Math.min(100, Math.max(0, score));
}

function getNiveauStrokeColor(niveau: string): string {
  switch (niveau) {
    case "Élevé":
      return "#C9A84C";
    case "Modéré":
      return "#00D4FF";
    case "Faible":
      return "#F39C12";
    case "Très faible":
      return "#E74C3C";
    default:
      return "#9A9AA8";
  }
}

function getNiveauColorClass(niveau: string): string {
  switch (niveau) {
    case "Élevé":
      return "text-quanta-gold";
    case "Modéré":
      return "text-quanta-cyan";
    case "Faible":
      return "text-quanta-warning";
    case "Très faible":
      return "text-quanta-error";
    default:
      return "text-quanta-secondary";
  }
}

function isRelevantVigilancePoint(point: string): boolean {
  const trimmed = point.trim();
  return trimmed.length > 0 && !trimmed.includes(NO_VIGILANCE_PHRASE);
}

function shouldShowVigilanceIcon(points: string[]): boolean {
  return points.length > 0 && points.some(isRelevantVigilancePoint);
}

export function ConfidenceScore({
  score,
  niveau,
  pointsDeVigilance,
}: ConfidenceScoreProps) {
  const clampedScore = clampScore(score);
  const motionScore = useMotionValue(0);
  const [displayScore, setDisplayScore] = useState(0);
  const [strokeDashoffset, setStrokeDashoffset] = useState(CIRCLE_CIRCUMFERENCE);

  const strokeColor = getNiveauStrokeColor(niveau);
  const colorClass = getNiveauColorClass(niveau);

  const visibleVigilancePoints = useMemo(
    () => pointsDeVigilance.filter(isRelevantVigilancePoint),
    [pointsDeVigilance],
  );

  const showVigilanceIcon = shouldShowVigilanceIcon(pointsDeVigilance);

  useEffect(() => {
    motionScore.set(0);
    setDisplayScore(0);
    setStrokeDashoffset(CIRCLE_CIRCUMFERENCE);

    const controls = animate(motionScore, clampedScore, {
      duration: ANIMATION_DURATION_S,
      ease: "easeOut",
      onUpdate: (latest) => {
        setDisplayScore(Math.round(latest));
        const progress = latest / 100;
        setStrokeDashoffset(CIRCLE_CIRCUMFERENCE * (1 - progress));
      },
    });

    return () => {
      controls.stop();
    };
  }, [clampedScore, motionScore]);

  return (
    <div className="flex w-full flex-col items-center gap-6">
      <div
        className="relative flex items-center justify-center"
        style={{ width: CIRCLE_SIZE_PX, height: CIRCLE_SIZE_PX }}
      >
        <svg
          className="pointer-events-none absolute inset-0 -rotate-90"
          width={CIRCLE_SIZE_PX}
          height={CIRCLE_SIZE_PX}
          viewBox={`0 0 ${CIRCLE_SIZE_PX} ${CIRCLE_SIZE_PX}`}
          aria-hidden
        >
          <circle
            cx={CIRCLE_SIZE_PX / 2}
            cy={CIRCLE_SIZE_PX / 2}
            r={CIRCLE_RADIUS_PX}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={STROKE_WIDTH_PX}
          />
          <circle
            cx={CIRCLE_SIZE_PX / 2}
            cy={CIRCLE_SIZE_PX / 2}
            r={CIRCLE_RADIUS_PX}
            fill="none"
            stroke={strokeColor}
            strokeWidth={STROKE_WIDTH_PX}
            strokeLinecap="round"
            strokeDasharray={CIRCLE_CIRCUMFERENCE}
            strokeDashoffset={strokeDashoffset}
          />
        </svg>

        <div className="relative z-10 flex flex-col items-center">
          <span
            className={cn(
              "font-display text-7xl font-light tabular-nums leading-none",
              colorClass,
            )}
          >
            {displayScore}
          </span>
          <span
            className={cn(
              "mt-2 font-sans text-sm uppercase tracking-widest",
              colorClass,
            )}
          >
            {niveau}
          </span>
        </div>
      </div>

      {visibleVigilancePoints.length > 0 ? (
        <div className="w-full rounded-quanta bg-quanta-elevated px-4 py-3">
          <ul className="space-y-2">
            {visibleVigilancePoints.map((point) => (
              <li
                key={point}
                className="flex items-start gap-2 font-mono text-xs leading-relaxed text-quanta-muted"
              >
                {showVigilanceIcon ? (
                  <AlertTriangle
                    className="mt-0.5 size-3.5 shrink-0 text-quanta-gold"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                ) : null}
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
