"use client";

/**
 * Dernier filet : erreur du layout racine lui-même (crash global).
 * Doit embarquer ses propres styles — globals.css n'est pas garanti ici.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="fr">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0A0A0F",
          color: "#E8E8E8",
          fontFamily:
            "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        }}
      >
        <div
          style={{
            maxWidth: 420,
            padding: "40px 32px",
            textAlign: "center",
            borderRadius: 16,
            border: "1px solid rgba(201,168,76,0.25)",
            background: "rgba(19,19,26,0.8)",
          }}
        >
          <div
            style={{
              fontFamily: "'Unbounded', system-ui, sans-serif",
              fontSize: 20,
              letterSpacing: "0.22em",
              color: "#E8D5A3",
            }}
          >
            QUANTA
          </div>
          <p
            style={{
              marginTop: 16,
              fontSize: 14,
              lineHeight: 1.6,
              color: "#9A9AA8",
            }}
          >
            Une erreur inattendue a interrompu l&apos;application.
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: 24,
              cursor: "pointer",
              padding: "10px 24px",
              borderRadius: 8,
              border: "none",
              background: "#C9A84C",
              color: "#0A0A0F",
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            Réessayer
          </button>
          <p style={{ marginTop: 12, fontSize: 11, color: "#55555F" }}>
            {error.digest ? `Réf. ${error.digest}` : null}
          </p>
        </div>
      </body>
    </html>
  );
}
