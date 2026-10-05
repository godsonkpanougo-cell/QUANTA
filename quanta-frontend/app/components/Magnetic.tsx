"use client";

import { useRef, type ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";

interface MagneticProps {
  children: ReactNode;
  /** Attraction max en px autour du centre. */
  strength?: number;
  className?: string;
}

/**
 * Attraction magnétique très légère : quand le curseur entre dans la
 * zone, le bouton glisse d'un ou deux pixels vers lui (25 % de
 * l'écart), puis revient avec un ressort à la sortie. Une nuance, pas
 * un gadget — et rien du tout sur tactile/réduit-motion.
 */
export function Magnetic({
  children,
  strength = 6,
  className,
}: MagneticProps) {
  const ref = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      ref={ref}
      className={className}
      onPointerMove={(event) => {
        const el = ref.current;
        if (!el || event.pointerType !== "mouse") {
          return;
        }
        const rect = el.getBoundingClientRect();
        const dx = event.clientX - (rect.left + rect.width / 2);
        const dy = event.clientY - (rect.top + rect.height / 2);
        void el.animate(
          [
            { transform: "translate3d(0,0,0)" },
            {
              transform: `translate3d(${(dx * strength) / 40}px, ${
                (dy * strength) / 40
              }px, 0)`,
            },
          ],
          { duration: 160, easing: "cubic-bezier(0.16, 1, 0.3, 1)", fill: "forwards" },
        );
      }}
      onPointerLeave={() => {
        const el = ref.current;
        if (!el) {
          return;
        }
        void el.animate(
          [
            { transform: el.style.transform || "translate3d(0,0,0)" },
            { transform: "translate3d(0,0,0)" },
          ],
          {
            duration: 420,
            easing: "cubic-bezier(0.34, 1.56, 0.64, 1)",
            fill: "forwards",
          },
        );
      }}
    >
      {children}
    </motion.div>
  );
}
