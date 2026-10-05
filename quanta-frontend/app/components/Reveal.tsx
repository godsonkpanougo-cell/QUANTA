"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { CSSProperties, ReactNode } from "react";

const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];

interface RevealProps {
  children: ReactNode;
  className?: string;
  /** Décalage (s) — chorégraphie des blocs visibles au chargement. */
  delay?: number;
  /** Amplitude de la montée (px). */
  y?: number;
  style?: CSSProperties;
}

/**
 * Révélation au scroll : le bloc monte en fondu la première fois qu'il
 * entre dans l'écran (une seule fois). Sous prefers-reduced-motion, le
 * contenu est rendu immédiatement, sans déplacement.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  y = 24,
  style,
}: RevealProps) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  }

  return (
    <motion.div
      className={className}
      style={style}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -56px 0px" }}
      transition={{ duration: 0.7, ease: EASE, delay }}
    >
      {children}
    </motion.div>
  );
}
