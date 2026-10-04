"use client";

import { motion } from "framer-motion";

/**
 * Transition de page globale : léger fondu + montée, cohérent avec les
 * `.reveal` existants. S'exécute à chaque navigation de route (template.tsx).
 * Respecte l'accessibilité : framer-motion + prefers-reduced-motion géré
 * par la durée courte (le composant reste sobre, pas de mouvement ample).
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.42, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}
