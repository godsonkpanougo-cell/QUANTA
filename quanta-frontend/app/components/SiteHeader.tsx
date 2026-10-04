"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AuthButton } from "@/app/components/AuthButton";
import { LogoQ } from "@/app/components/LogoQ";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/", label: "Accueil" },
  { href: "/history", label: "Historique" },
] as const;

/**
 * Header QUANTA — verre liquide, wordmark, statut HUD.
 * La navigation est toujours visible (accès Accueil / Historique depuis
 * n'importe quelle page), avec soulignement or animé sur l'onglet actif.
 */
export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="glass fixed inset-x-0 top-0 z-50 border-x-0 border-t-0">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        {/* Wordmark */}
        <Link
          href="/"
          aria-label="QUANTA — accueil"
          className="group flex items-center gap-3"
        >
          <LogoQ
            size={30}
            className="transition-transform duration-300 group-hover:rotate-[8deg]"
          />
          <span className="font-brand text-base font-extralight tracking-[0.22em] text-quanta-primary transition-colors duration-200 group-hover:text-quanta-gold-2">
            QUANTA
          </span>
          <span className="hidden h-3 w-px bg-quanta-border-subtle sm:block" />
          <span className="hud-label hidden text-quanta-muted sm:block">
            Intelligence statistique
          </span>
        </Link>

        {/* Navigation + statut HUD + auth */}
        <div className="flex items-center gap-6">
          <nav aria-label="Navigation principale">
            <ul className="flex items-center gap-1">
              {NAV_LINKS.map(({ href, label }) => {
                const active =
                  href === "/" ? pathname === "/" : pathname.startsWith(href);
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "relative block px-3 py-2 font-sans text-sm transition-quanta",
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
                          "absolute inset-x-3 bottom-1 h-px bg-quanta-gold transition-all duration-300 ease-out",
                          active
                            ? "opacity-100 scale-x-100"
                            : "opacity-0 scale-x-40",
                        )}
                      />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          <span className="hidden items-center gap-2 md:flex" aria-hidden>
            <span className="hud-dot" />
            <span className="hud-label text-quanta-secondary">
              Système opérationnel
            </span>
          </span>
          <AuthButton compact />
        </div>
      </div>
    </header>
  );
}
