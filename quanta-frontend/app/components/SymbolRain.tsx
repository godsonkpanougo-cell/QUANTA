"use client";

import { useEffect, useRef } from "react";
import type { CSSProperties } from "react";

/**
 * Pluie de symboles mathématiques — minuscules, dorées, flottantes.
 * Calque FIXE plein écran rendu dans le layout racine : la pluie est
 * donc présente, identique et visible sur toutes les pages, à tout
 * moment du défilement (elle ne défile pas avec le contenu).
 * Chaque glyphe dérive lentement vers le haut en scintillant, puis
 * renaît plus bas : l'opacité est nulle aux deux extrémités du cycle,
 * la boucle est donc invisible. Rendu déterministe (PRNG à graine
 * fixe) : serveur et client produisent la même pluie — zéro erreur
 * d'hydratation. En pause quand l'onglet est masqué ; cachée si
 * prefers-reduced-motion (CSS).
 */

const GLYPHS = [
  "∑", "π", "∫", "√", "∞", "Δ", "φ", "λ", "σ", "∂", "≈", "∇",
  "ℏ", "∈", "∀", "∃", "ℝ", "μ", "χ", "ψ", "τ", "γ", "δ", "β",
  "θ", "ξ", "ζ", "Ω", "Σ", "⊕", "⊗", "∠", "∴", "∪", "∩", "≠",
] as const;

/* Deux ors de la palette : or profond et champagne. */
const GOLD_TONES = ["#C9A84C", "#E8D5A3"] as const;

/* PRNG mulberry32 — graine fixe = même rendu serveur / client. */
function mulberry32(seed: number): () => number {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* Densité : présence constante et lisible — 84 glyphes sur l'écran. */
const RAIN_COUNT = 84;

interface Flake {
  glyph: string;
  color: string;
  left: number; // % de la largeur
  top: number; // % de la hauteur
  size: number; // px
  peak: number; // opacité au sommet du scintillement
  drift: number; // px de dérive horizontale sur un cycle
  rise: number; // px d'ascension par cycle
  duration: number; // s — partagé par dérive et scintillement (resynchronisés)
  delay: number; // s, négatif : la pluie est déjà vivante au chargement
}

function buildRain(): Flake[] {
  const rand = mulberry32(20261005);
  return Array.from({ length: RAIN_COUNT }, () => ({
    glyph: GLYPHS[Math.floor(rand() * GLYPHS.length)],
    color: GOLD_TONES[Math.floor(rand() * GOLD_TONES.length)],
    left: rand() * 100,
    top: rand() * 100,
    size: 12 + rand() * 7,
    peak: 0.35 + rand() * 0.5,
    drift: (rand() - 0.5) * 48,
    rise: 40 + rand() * 40,
    duration: 9 + rand() * 13,
    delay: -rand() * 22,
  }));
}

/* Calculé une seule fois — déterministe, stable entre les rendus. */
const RAIN: Flake[] = buildRain();

export function SymbolRain() {
  const ref = useRef<HTMLDivElement>(null);

  /* Onglet masqué → animations en pause (CPU/GPU au repos). */
  useEffect(() => {
    const el = ref.current;
    if (!el) {
      return;
    }
    const sync = () => {
      el.dataset.paused = document.hidden ? "true" : "false";
    };
    sync();
    document.addEventListener("visibilitychange", sync);
    return () => document.removeEventListener("visibilitychange", sync);
  }, []);

  return (
    <div
      ref={ref}
      data-paused="false"
      aria-hidden
      className="symbol-rain pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      {RAIN.map((flake, index) => (
        <span
          key={index}
          className="symbol-flake"
          style={
            {
              left: `${flake.left}%`,
              top: `${flake.top}%`,
              color: flake.color,
              fontSize: `${flake.size}px`,
              animationDuration: `${flake.duration}s`,
              animationDelay: `${flake.delay}s`,
              "--peak": flake.peak,
              "--drift": `${flake.drift}px`,
              "--rise": `${flake.rise}px`,
            } as CSSProperties
          }
        >
          {flake.glyph}
        </span>
      ))}
    </div>
  );
}
