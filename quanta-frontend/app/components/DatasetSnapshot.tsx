"use client";

import { motion } from "framer-motion";
import { useId, useMemo } from "react";

/**
 * DatasetSnapshot — la « signature visuelle » du jeu de données analysé.
 * Déterministe : une même base produit toujours la même empreinte
 * (hash simple des dimensions), aucune donnée réelle n'est affichée.
 * Représentation stylisée : silhouette lignes × colonnes + jauge d'aire.
 */

interface DatasetSnapshotProps {
  rows?: number;
  cols?: number;
  datasetType?: string;
}

const BAR_COUNT = 28;
const W = 560;
const H = 120;
const BASE_Y = H - 18;

/* Hash déterministe (FNV-1a 32 bits) — aucune dépendance, stable SSR/CSR. */
function fnv1a(input: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/* Générateur pseudo-aléatoire déterministe (mulberry32). */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function formatCount(n: number | undefined): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("fr-FR").format(n);
}

export function DatasetSnapshot({
  rows,
  cols,
  datasetType,
}: DatasetSnapshotProps) {
  const gradId = useId();

  const bars = useMemo(() => {
    const seed = fnv1a(
      `${rows ?? "u"}x${cols ?? "u"}x${datasetType ?? "none"}`,
    );
    const rand = mulberry32(seed);
    return Array.from({ length: BAR_COUNT }, (_, i) => {
      // Profil de « terrain » : hauteurs variées mais cohérentes (lissage voisin)
      const base = 0.25 + rand() * 0.65;
      const edge = Math.sin((i / (BAR_COUNT - 1)) * Math.PI); // plus bas sur les bords
      const h01 = Math.min(0.98, Math.max(0.08, base * (0.55 + 0.45 * edge)));
      return h01;
    });
  }, [rows, cols, datasetType]);

  const linePath = useMemo(() => {
    const step = (W - 24) / (BAR_COUNT - 1);
    const pts = bars.map(
      (h01, i) => `${(12 + i * step).toFixed(1)},${(BASE_Y - h01 * (H - 42)).toFixed(1)}`,
    );
    return `M${pts.join(" L")}`;
  }, [bars]);

  const areaPath = useMemo(() => {
    const step = (W - 24) / (BAR_COUNT - 1);
    const pts = bars.map(
      (h01, i) => `${(12 + i * step).toFixed(1)},${(BASE_Y - h01 * (H - 42)).toFixed(1)}`,
    );
    return `M12,${BASE_Y} L${pts.join(" L")} L${(12 + (BAR_COUNT - 1) * step).toFixed(1)},${BASE_Y} Z`;
  }, [bars]);

  const hasData = typeof rows === "number" && typeof cols === "number";

  return (
    <div className="glass glow-card rounded-card p-6">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <p className="hud-label text-quanta-muted">Empreinte du dataset</p>
          <p className="mt-1 font-sans text-xs text-quanta-secondary">
            Signature visuelle de la structure analysée — aucune donnée
            n&apos;est affichée.
          </p>
        </div>
        <div className="flex gap-5 text-right">
          <div>
            <p className="font-mono text-xl font-medium text-quanta-gold">
              {formatCount(rows)}
            </p>
            <p className="hud-label text-quanta-muted">lignes</p>
          </div>
          <div>
            <p className="font-mono text-xl font-medium text-quanta-cyan">
              {formatCount(cols)}
            </p>
            <p className="hud-label text-quanta-muted">colonnes</p>
          </div>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full"
        role="img"
        aria-label={
          hasData
            ? `Empreinte visuelle d'un dataset de ${rows} lignes et ${cols} colonnes`
            : "Empreinte visuelle du dataset indisponible"
        }
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#C9A84C" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#C9A84C" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient
            id={`${gradId}-line`}
            x1="0"
            y1="0"
            x2={W}
            y2="0"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="#C9A84C" />
            <stop offset="55%" stopColor="#E8D5A3" />
            <stop offset="100%" stopColor="#00D4FF" />
          </linearGradient>
        </defs>

        {/* Ligne de base */}
        <line
          x1="12"
          y1={BASE_Y}
          x2={W - 12}
          y2={BASE_Y}
          stroke="rgba(255,255,255,0.09)"
          strokeWidth="1"
        />

        <motion.g
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.15 }}
        >
          {/* Aire */}
          <motion.path
            d={areaPath}
            fill={`url(#${gradId})`}
            initial={{ opacity: 0, scaleY: 0.001 }}
            animate={{ opacity: 1, scaleY: 1 }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
            style={{ transformOrigin: `0 ${BASE_Y}` }}
          />
          {/* Silhouette */}
          <motion.path
            d={linePath}
            fill="none"
            stroke={`url(#${gradId}-line)`}
            strokeWidth="1.6"
            strokeLinejoin="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1], delay: 0.3 }}
          />
          {/* Barres verticales discrètes */}
          {bars.map((h01, i) => {
            const step = (W - 24) / (BAR_COUNT - 1);
            const x = 12 + i * step;
            return (
              <motion.rect
                key={i}
                x={(x - 1).toFixed(1)}
                y={BASE_Y - h01 * (H - 42)}
                width="2"
                height={h01 * (H - 42)}
                rx="1"
                fill="#00D4FF"
                opacity="0.16"
                initial={{ scaleY: 0 }}
                animate={{ scaleY: 1 }}
                transition={{
                  duration: 0.45,
                  delay: 0.35 + i * 0.018,
                  ease: [0.16, 1, 0.3, 1],
                }}
                style={{ transformOrigin: `0 ${BASE_Y}` }}
              />
            );
          })}
        </motion.g>
      </svg>

      {datasetType ? (
        <p className="mt-3 text-right font-mono text-[11px] text-quanta-muted">
          type : {datasetType}
        </p>
      ) : null}
    </div>
  );
}
