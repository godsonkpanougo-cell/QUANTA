"use client";

import { useState } from "react";
import {
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
} from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AuthButton } from "@/app/components/AuthButton";
import { LogoQ } from "@/app/components/LogoQ";
import { cn } from "@/lib/utils";

interface NavLink {
  href: string;
  label: string;
  /** Lien secondaire : masqué sous lg pour tenir sur une ligne. */
  wide?: boolean;
  /** Libellé complet affiché au survol si le libellé est raccourci. */
  title?: string;
}

const NAV_LINKS: readonly NavLink[] = [
  { href: "/", label: "Accueil" },
  { href: "/workspace", label: "Workspace", wide: true },
  { href: "/conversation", label: "Conversation", wide: true },
  { href: "/history", label: "Historique" },
  {
    href: "/defense",
    label: "Soutenance",
    wide: true,
    title: "Préparer ma soutenance",
  },
] as const;

// La page Méthodologie (A3) est servie par l'API FastAPI, pas par Next.js :
// lien externe construit sur NEXT_PUBLIC_API_URL.
function methodologieHref(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
  return `${baseUrl.replace(/\/$/, "")}/methodologie`;
}

/**
 * Header QUANTA — verre liquide, wordmark, navigation.
 * Contrainte d'affichage : tout tient sur une seule ligne — wordmark
 * compact, libellés raccourcis, whitespace-nowrap, liens secondaires
 * réservés aux écrans lg+ ; sous md la nav défile horizontalement
 * (sans scrollbar visible) au lieu d'envelopper.
 *
 * Auto-hide : glisse hors écran quand on défile vers le bas, revient dès
 * qu'on remonte. Seuil de 120px + hystérésis pour éviter le clignotement
 * aux micro-scrolls ; désactivé visuellement si prefers-reduced-motion.
 */
export function SiteHeader() {
  const pathname = usePathname();
  const { scrollY } = useScroll();
  const reduceMotion = useReducedMotion();
  const [hidden, setHidden] = useState(false);

  useMotionValueEvent(scrollY, "change", (y) => {
    const previous = scrollY.getPrevious() ?? 0;
    if (y > previous && y > 120) {
      // Défilement vers le bas, au-delà du seuil → on escamote.
      setHidden(true);
    } else if (y < previous || y <= 80) {
      // Remontée (même d'1px) ou retour proche du sommet → on réaffiche.
      setHidden(false);
    }
  });

  return (
    <motion.header
      initial={false}
      animate={{ y: hidden ? "-100%" : "0%" }}
      transition={
        reduceMotion
          ? { duration: 0 }
          : { duration: 0.4, ease: [0.16, 1, 0.3, 1] }
      }
      className="glass fixed inset-x-0 top-0 z-50 border-x-0 border-t-0"
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        {/* Wordmark compact */}
        <Link
          href="/"
          aria-label="QUANTA — accueil"
          className="group flex shrink-0 items-center gap-3"
        >
          <LogoQ
            size={30}
            className="transition-transform duration-300 group-hover:rotate-[8deg]"
          />
          <span className="whitespace-nowrap font-brand text-base font-extralight tracking-[0.22em] text-quanta-primary transition-colors duration-200 group-hover:text-quanta-gold-2">
            QUANTA
          </span>
        </Link>

        {/* Navigation + auth — jamais sur deux lignes */}
        <div className="flex min-w-0 items-center gap-1.5 sm:gap-2.5">
          <nav
            aria-label="Navigation principale"
            className="no-scrollbar min-w-0 overflow-x-auto md:overflow-visible"
          >
            <ul className="flex items-center whitespace-nowrap">
              {NAV_LINKS.map(({ href, label, wide, title }) => {
                const active =
                  href === "/" ? pathname === "/" : pathname.startsWith(href);
                return (
                  <li
                    key={href}
                    className={cn("shrink-0", wide && "hidden lg:block")}
                  >
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      title={title}
                      className={cn(
                        "relative block px-2 py-2 font-sans text-sm transition-quanta sm:px-2.5",
                        active
                          ? "text-quanta-primary"
                          : "text-quanta-secondary hover:text-quanta-primary",
                      )}
                    >
                      {label}
                      {/* Soulignement or : glisse/fond en douceur */}
                      <span
                        aria-hidden
                        className={cn(
                          "absolute inset-x-2 bottom-1 h-px bg-quanta-gold transition-all duration-300 ease-out sm:inset-x-2.5",
                          active
                            ? "opacity-100 scale-x-100"
                            : "opacity-0 scale-x-40",
                        )}
                      />
                    </Link>
                  </li>
                );
              })}
              <li className="hidden shrink-0 lg:block">
                <a
                  href={methodologieHref()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="relative block px-2.5 py-2 font-sans text-sm text-quanta-secondary transition-quanta hover:text-quanta-primary"
                >
                  Méthodologie
                </a>
              </li>
            </ul>
          </nav>

          <div className="shrink-0">
            <AuthButton compact />
          </div>
        </div>
      </div>
    </motion.header>
  );
}
