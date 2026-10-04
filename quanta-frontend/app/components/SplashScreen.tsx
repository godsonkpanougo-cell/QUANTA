"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

import { LogoQ } from "@/app/components/LogoQ";

const SESSION_KEY = "quanta-splash-shown";
/* Durées calées sur le tracé du logo (1100 ms) + respiration du wordmark. */
const SPLASH_MS = 2400;
const EXIT_MS = 700;

/**
 * Écran de démarrage QUANTA — une fois par session (sessionStorage).
 * Fond void, le logo se trace (anneau → vecteur → point), le wordmark
 * « QUANTA » apparaît en suivi de lettres, puis l'ensemble se dissout
 * vers la page. Respecte prefers-reduced-motion (sortie immédiate).
 */
export function SplashScreen() {
  /* Décision de montage lue au premier render client : sessionStorage est
     disponible dès l'hydratation, pas besoin d'un effet + setState (qui
     provoquerait un render en cascade). SSR rend null via typeof window. */
  const [visible, setVisible] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      const alreadyShown = sessionStorage.getItem(SESSION_KEY) === "1";
      const reduced = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      return !alreadyShown && !reduced;
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (!visible) {
      return;
    }
    try {
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      // sessionStorage indisponible : le splash se montrera à chaque visite.
    }
    const timer = setTimeout(() => setVisible(false), SPLASH_MS);
    return () => clearTimeout(timer);
  }, [visible]);

  return (
    <AnimatePresence>
      {visible ? (
        <motion.div
          key="quanta-splash"
          aria-hidden
          initial={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: EXIT_MS / 1000, ease: "easeInOut" }}
          className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-[#0A0A0F]"
        >
          {/* Halo or discret derrière le logo */}
          <div
            className="pointer-events-none absolute size-72 rounded-full"
            style={{
              background:
                "radial-gradient(circle, rgba(201,168,76,0.10), transparent 65%)",
            }}
          />

          <LogoQ size={88} animated durationMs={1100} delayMs={250} />

          <div className="mt-7 overflow-hidden">
            <motion.p
              className="font-brand text-xl font-extralight tracking-[0.42em] text-quanta-primary"
              initial={{ y: "110%" }}
              animate={{ y: 0 }}
              transition={{
                duration: 0.7,
                ease: [0.16, 1, 0.3, 1],
                delay: 1.15,
              }}
            >
              QUANTA
            </motion.p>
          </div>

          <motion.div
            className="mt-5 h-px bg-gradient-to-r from-transparent via-quanta-gold/60 to-transparent"
            initial={{ width: 0 }}
            animate={{ width: 120 }}
            transition={{ duration: 0.6, delay: 1.6, ease: "easeOut" }}
          />

          <motion.p
            className="hud-label absolute bottom-16 text-quanta-muted"
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.7 }}
            transition={{ delay: 1.9, duration: 0.4 }}
          >
            Intelligence statistique
          </motion.p>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
