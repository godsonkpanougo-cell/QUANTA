"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

import { LogoQ } from "@/app/components/LogoQ";

const SESSION_KEY = "quanta-splash-shown";

/* Choreographie (ms) :
   0–250  : le vide. 250–1350 : l'anneau se trace, le vecteur le traverse,
   ~1500  : le point s'allume. 1050–1600 : « QUANTA » monte en suivi de
   lettres. 1850–2550 : le logo rétrécit et glisse vers sa place dans le
   header (fondu de l'overlay) — le hero prend le relais à l'identique. */
const SPLASH_MS = 2550;
/* Logo géant : 480px au démarrage (50% de plus qu'à l'origine) — plafonné
   responsivement à 88% de la largeur / 62% de la hauteur du viewport
   (voir logoSize) pour que wordmark + ligne + signature tiennent à l'écran. */
const LOGO_SIZE = 480;
const HOLD_MS = 1850;
const GLIDE_MS = 700;

/* Cible : logo du header (32px) — centre du carré à gauche du header. */
const TARGET_SIZE = 32;
const TARGET_CENTER = { x: 40, y: 32 };

/**
 * Écran de démarrage QUANTA — une fois par session (sessionStorage).
 * Le logo se trace en très grand, seul, au centre exact de l'écran ;
 * complet, il rétrécit et se déplace vers le header tandis que le
 * wordmark s'efface — une seule entité, jamais deux logos. Respecte
 * prefers-reduced-motion (sortie immédiate).
 */
export function SplashScreen() {
  /* Décision de montage lue au premier render client : sessionStorage est
     disponible dès l'hydratation — pas d'effet + setState en cascade. */
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

  /* Décalage du centre de l'écran vers le centre du logo du header.
     Le logo est positionné indépendamment du wordmark (absolute
     inset-0 m-auto) : son centre naturel est EXACTEMENT le centre du
     viewport — la cible est donc la formule directe, sans mesure DOM
     (une mesure dépendrait du timing de layout de LogoQ et atterrissait
     ~70px au-dessus du header). */
  const [target, setTarget] = useState({ x: 0, y: 0 });
  /* Taille effective du logo (clamp responsive — initialisé à LOGO_SIZE,
     corrigé avant le début du tracé à 250ms). */
  const [logoSize, setLogoSize] = useState(LOGO_SIZE);
  useEffect(() => {
    const onResize = () => {
      setTarget({
        x: TARGET_CENTER.x - window.innerWidth / 2,
        y: TARGET_CENTER.y - window.innerHeight / 2,
      });
      setLogoSize(
        Math.min(
          LOGO_SIZE,
          window.innerWidth * 0.88,
          window.innerHeight * 0.62,
        ),
      );
    };
    onResize();
    window.addEventListener("resize", onResize, { passive: true });
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    <AnimatePresence>
      {visible ? (
        <motion.div
          key="quanta-splash"
          aria-hidden
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.3 } }}
          className="fixed inset-0 z-[100] overflow-hidden"
        >
          {/* Fond void — s'estompe pendant le glissement pour révéler la page
              (et le header) sous le logo volant. */}
          <motion.div
            className="absolute inset-0 bg-[#07070C]"
            initial={{ opacity: 1 }}
            animate={{ opacity: 0 }}
            transition={{
              delay: HOLD_MS / 1000,
              duration: GLIDE_MS / 1000,
              ease: "easeInOut",
            }}
          />

          {/* Halo or derrière le logo en train de se tracer */}
          <motion.div
            className="pointer-events-none absolute inset-0 m-auto size-[680px] rounded-full"
            style={{
              background:
                "radial-gradient(circle, rgba(201,168,76,0.10), transparent 62%)",
            }}
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: [0, 1, 1, 0], scale: [0.85, 1, 1, 0.6] }}
            transition={{ duration: SPLASH_MS / 1000, times: [0, 0.18, 0.72, 1] }}
          />

          {/* Le logo : se trace en géant, puis rétrécit vers le header */}
          <motion.div
            className="absolute inset-0 m-auto flex items-center justify-center"
            style={{ width: logoSize, height: logoSize }}
            initial={{ scale: 1, x: 0, y: 0 }}
            animate={{
              scale: [1, 1, TARGET_SIZE / logoSize],
              x: [0, 0, target.x],
              y: [0, 0, target.y],
            }}
            transition={{
              duration: SPLASH_MS / 1000,
              times: [0, HOLD_MS / SPLASH_MS, 1],
              ease: [0.7, 0, 0.25, 1],
            }}
          >
            <LogoQ size={logoSize} animated durationMs={1100} delayMs={250} />
          </motion.div>

          {/* Wordmark + ligne — calque indépendant sous le logo (le logo
              reste centré exactement, indépendant de ce calque). */}
          <div
            className="absolute left-1/2 -translate-x-1/2 overflow-hidden"
            style={{ top: `calc(50% + ${logoSize / 2 + 40}px)` }}
          >
            <motion.p
              className="font-brand text-3xl font-extralight tracking-[0.5em] text-quanta-primary sm:text-4xl"
              initial={{ y: "110%" }}
              animate={{ y: ["110%", "0%", "0%", "130%"] }}
              transition={{
                duration: SPLASH_MS / 1000,
                times: [0.41, 0.63, 0.75, 0.9],
                ease: [0.16, 1, 0.3, 1],
              }}
            >
              QUANTA
            </motion.p>

            {/* Ligne or — se déploie puis se résorbe */}
            <motion.div
              className="mx-auto mt-6 h-px bg-gradient-to-r from-transparent via-quanta-gold/60 to-transparent"
              initial={{ width: 0 }}
              animate={{ width: [0, 180, 180, 0], opacity: [0, 1, 1, 0] }}
              transition={{
                duration: SPLASH_MS / 1000,
                times: [0.5, 0.66, 0.75, 0.9],
                ease: "easeOut",
              }}
            />
          </div>

          {/* Signature basale — paraît, disparaît */}
          <motion.p
            className="hud-label absolute inset-x-0 bottom-16 text-center text-quanta-muted"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.7, 0.7, 0] }}
            transition={{
              duration: SPLASH_MS / 1000,
              times: [0.5, 0.62, 0.74, 0.88],
            }}
          >
            Intelligence statistique
          </motion.p>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
