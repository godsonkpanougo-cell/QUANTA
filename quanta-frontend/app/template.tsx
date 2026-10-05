"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Transition entre les pages : à chaque navigation interne, la vue
 * monte en fondu sur 8px. Court (420 ms), déclenché au montage du
 * template — donc à chaque changement de route, mais pas pendant
 * l'entrée du site que gère déjà le splash.
 */
export default function Template({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.42, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}
