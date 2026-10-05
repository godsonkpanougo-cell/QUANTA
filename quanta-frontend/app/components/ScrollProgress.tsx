"use client";

import { motion, useReducedMotion, useScroll, useSpring } from "framer-motion";

/**
 * Progression de lecture — fine ligne or en haut de l'écran, au-dessus
 * du header (elle reste visible même quand il s'escamote). Ressort
 * doux pour que la ligne coule au lieu de trembler ; sous
 * prefers-reduced-motion, progression directe sans ressort.
 */
export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const reduceMotion = useReducedMotion();
  const smooth = useSpring(scrollYProgress, {
    stiffness: 140,
    damping: 28,
    mass: 0.4,
  });

  return (
    <motion.div
      aria-hidden
      className="fixed inset-x-0 top-0 z-[60] h-[2px] origin-left bg-gradient-to-r from-quanta-gold via-quanta-gold-2 to-quanta-gold"
      style={{ scaleX: reduceMotion ? scrollYProgress : smooth }}
    />
  );
}
