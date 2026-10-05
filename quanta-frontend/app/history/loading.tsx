/** Skeleton du chargement de l'historique — même allure que la vraie page. */
export default function HistoryLoading() {
  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 pb-20 pt-28 sm:px-6 lg:px-8">
        {/* Titre */}
        <div className="mb-10 space-y-4">
          <div className="h-8 w-40 animate-pulse rounded-quanta bg-quanta-surface" />
          <div className="h-4 w-24 animate-pulse rounded-quanta bg-quanta-surface" />
          <div className="h-10 w-64 animate-pulse rounded-quanta bg-quanta-surface" />
          <div className="h-4 w-80 max-w-full animate-pulse rounded-quanta bg-quanta-surface" />
        </div>

        {/* Barre de recherche/filtres (future place) */}
        <div className="mb-6 h-11 w-full animate-pulse rounded-quanta bg-quanta-surface" />

        {/* Cartes d'analyses */}
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="glass rounded-card px-6 py-5"
              style={{ animationDelay: `${i * 120}ms` }}
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex-1 space-y-3">
                  <div className="h-5 w-56 animate-pulse rounded-quanta bg-quanta-elevated" />
                  <div className="h-3 w-72 max-w-full animate-pulse rounded-quanta bg-quanta-elevated" />
                  <div className="h-3 w-40 animate-pulse rounded-quanta bg-quanta-elevated" />
                </div>
                <div className="flex gap-2">
                  <div className="h-9 w-32 animate-pulse rounded-quanta bg-quanta-elevated" />
                  <div className="h-9 w-32 animate-pulse rounded-quanta bg-quanta-elevated" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
