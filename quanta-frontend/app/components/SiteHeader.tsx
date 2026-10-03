"use client";

import Link from "next/link";
import { AuthButton } from "@/app/components/AuthButton";
import { LogoQ } from "@/app/components/LogoQ";

export function SiteHeader() {
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

        {/* Statut HUD + auth */}
        <div className="flex items-center gap-6">
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
