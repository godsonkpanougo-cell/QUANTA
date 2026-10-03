export function SiteFooter() {
  return (
    <footer className="border-t border-quanta-border-subtle">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 py-8 sm:flex-row">
        <p className="hud-label text-quanta-muted">QUANTA — Moteur d&apos;analyse statistique</p>
        <p className="hud-label text-quanta-muted">
          Calcul déterministe · Interprétation assistée · Rapport signable
        </p>
      </div>
    </footer>
  );
}
