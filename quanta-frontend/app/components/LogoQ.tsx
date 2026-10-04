"use client";

import { useEffect, useState } from "react";

interface LogoQProps {
  size?: number;
  className?: string;
  /** Anime le tracé de l'anneau puis du vecteur (montée en session, hero). */
  animated?: boolean;
  /** Durée totale de l'animation de tracé (ms). */
  durationMs?: number;
  /** Délai avant le début du tracé (ms). */
  delayMs?: number;
}

/** Longueurs approximatives des tracés (viewBox 48) — mesurées une fois. */
const RING_LENGTH = 73.5; // arc principal de l'anneau entaillé
const VECTOR_LENGTH = 19.5; // trait oblique
const RING_SHARE = 0.68; // part du temps total pour l'anneau

/**
 * Symbole QUANTA — un Q traité comme un artefact mathématique :
 * un anneau entaillé (évocation de l'ensemble vide ∅) traversé par un
 * vecteur qui se détache et se termine par un point (élément).
 * Ultra-minimal, trait fin, or.
 *
 * Animé (animated) : l'anneau se trace d'un trait, le vecteur le traverse,
 * le point s'allume en dernier — comme une signature mathématique qui s'écrit.
 */
export function LogoQ({
  size = 28,
  className = "",
  animated = false,
  durationMs = 1100,
  delayMs = 0,
}: LogoQProps) {
  /* Le tracé démarre après le délai demandé — via un timer (système
     externe), pas d'appel setState synchrone dans le corps de l'effet. */
  const [drawn, setDrawn] = useState(!animated);

  useEffect(() => {
    if (!animated) {
      return;
    }
    const timer = setTimeout(() => setDrawn(true), delayMs + 60);
    return () => clearTimeout(timer);
  }, [animated, delayMs]);

  const ringDuration = Math.round(durationMs * RING_SHARE);
  const vectorDuration = Math.max(
    Math.round(durationMs * (1 - RING_SHARE)),
    220,
  );
  const vectorDelay = delayMs + ringDuration * 0.82;
  const dotDelay = delayMs + durationMs * 0.92;

  const easing = "cubic-bezier(0.65, 0, 0.35, 1)";

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden
      className={className}
    >
      <defs>
        <linearGradient
          id="quanta-q-grad"
          x1="10"
          y1="8"
          x2="40"
          y2="44"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#E8D5A3" />
          <stop offset="1" stopColor="#C9A84C" />
        </linearGradient>
      </defs>
      {/* Anneau entaillé — se trace d'un seul geste */}
      <path
        d="M 35.5 30 A 14 14 0 1 0 26.4 35.8"
        stroke="url(#quanta-q-grad)"
        strokeWidth="2.6"
        strokeLinecap="round"
        style={
          animated
            ? {
                strokeDasharray: RING_LENGTH,
                strokeDashoffset: drawn ? 0 : RING_LENGTH,
                transition: `stroke-dashoffset ${ringDuration}ms ${easing} ${delayMs}ms`,
              }
            : undefined
        }
      />
      {/* Vecteur — traverse l'anneau après le tracé */}
      <line
        x1="26.2"
        y1="25.4"
        x2="36"
        y2="40.5"
        stroke="url(#quanta-q-grad)"
        strokeWidth="2.6"
        strokeLinecap="round"
        style={
          animated
            ? {
                strokeDasharray: VECTOR_LENGTH,
                strokeDashoffset: drawn ? 0 : VECTOR_LENGTH,
                transition: `stroke-dashoffset ${vectorDuration}ms ${easing} ${vectorDelay}ms`,
              }
            : undefined
        }
      />
      {/* Point terminal — s'allume en dernier */}
      <circle
        cx="37.6"
        cy="42.8"
        r="1.9"
        fill="#E8D5A3"
        style={
          animated
            ? {
                opacity: drawn ? 1 : 0,
                transformOrigin: "37.6px 42.8px",
                transform: drawn ? "scale(1)" : "scale(0.2)",
                transition: `opacity 240ms ease-out ${dotDelay}ms, transform 240ms cubic-bezier(0.34, 1.56, 0.64, 1) ${dotDelay}ms`,
              }
            : undefined
        }
      />
    </svg>
  );
}
