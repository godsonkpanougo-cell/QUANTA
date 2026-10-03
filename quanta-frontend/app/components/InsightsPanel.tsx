"use client";

import { useId, useMemo } from "react";
import Link from "next/link";
import { Activity, Gauge, Timer, Database } from "lucide-react";

/**
 * InsightsPanel — ce que l'utilisateur voit de la consommation de QUANTA.
 *
 * Volontairement opaque sur la mécanique interne : on expose uniquement des
 * agrégats d'usage (volume d'analyses, score de confiance perçu, temps de
 * calcul investi), jamais les étapes, modèles ou prompts du pipeline.
 * Tous les calculs sont dérivés côté client de la liste /history.
 */

export interface InsightAnalysis {
  analysis_id: string;
  status: "pending" | "running" | "done" | "error";
  created_at: string;
  updated_at: string;
  confidence_score: number | null;
}

const DAY_MS = 86_400_000;
const WINDOW_DAYS = 14;

/* ── Helpers ─────────────────────────────────────────────── */

function startOfDay(ts: number): number {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/** Durée de calcul d'une analyse (secondes), bridée contre les horloges folles. */
function computeSeconds(a: InsightAnalysis): number {
  const start = Date.parse(a.created_at);
  const end = Date.parse(a.updated_at);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 0;
  return Math.min(Math.max((end - start) / 1000, 0), 6 * 3600);
}

function formatDay(ts: number): string {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(ts));
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return s > 0 ? `${m} min ${s} s` : `${m} min`;
  }
  return `${(seconds / 3600).toFixed(1)} h`;
}

/* ── Données dérivées ────────────────────────────────────── */

interface Insights {
  /** Nombre d'analyses par jour sur la fenêtre (index 0 = le plus ancien). */
  perDay: number[];
  dayLabels: string[];
  /** Temps de calcul total par jour (secondes). */
  secondsPerDay: number[];
  /** Scores de confiance des analyses terminées, ordre chronologique. */
  confidence: Array<{ score: number; date: number }>;
  total: number;
  thisWeek: number;
  avgConfidence: number | null;
  avgSeconds: number | null;
}

function buildInsights(analyses: InsightAnalysis[]): Insights {
  const now = Date.now();
  const today = startOfDay(now);
  const firstDay = today - (WINDOW_DAYS - 1) * DAY_MS;

  const perDay = Array.from({ length: WINDOW_DAYS }, () => 0);
  const secondsPerDay = Array.from({ length: WINDOW_DAYS }, () => 0);
  const confidence: Array<{ score: number; date: number }> = [];
  const durations: number[] = [];
  let thisWeek = 0;

  for (const a of analyses) {
    const created = Date.parse(a.created_at);
    if (Number.isFinite(created)) {
      const dayIndex = Math.round((startOfDay(created) - firstDay) / DAY_MS);
      if (dayIndex >= 0 && dayIndex < WINDOW_DAYS) {
        perDay[dayIndex] += 1;
        if (created >= now - 7 * DAY_MS) thisWeek += 1;
      }
    }
    if (a.status === "done") {
      const secs = computeSeconds(a);
      durations.push(secs);
      const dayIndex = Number.isFinite(created)
        ? Math.round((startOfDay(created) - firstDay) / DAY_MS)
        : -1;
      if (dayIndex >= 0 && dayIndex < WINDOW_DAYS) secondsPerDay[dayIndex] += secs;
      if (a.confidence_score !== null && Number.isFinite(a.confidence_score)) {
        confidence.push({ score: a.confidence_score, date: created });
      }
    }
  }
  confidence.sort((x, y) => x.date - y.date);

  const scored = confidence.map((c) => c.score);
  const avgConfidence =
    scored.length > 0 ? scored.reduce((s, v) => s + v, 0) / scored.length : null;
  const avgSeconds =
    durations.length > 0
      ? durations.reduce((s, v) => s + v, 0) / durations.length
      : null;

  return {
    perDay,
    dayLabels: perDay.map((_, i) => formatDay(firstDay + i * DAY_MS)),
    secondsPerDay,
    confidence,
    total: analyses.length,
    thisWeek,
    avgConfidence,
    avgSeconds,
  };
}

/* ── Tuiles ──────────────────────────────────────────────── */

function StatTile({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="glass glow-card rounded-card p-5">
      <div className="flex items-center justify-between">
        <span className="hud-label text-quanta-muted">{label}</span>
        <span className={tone} aria-hidden>
          {icon}
        </span>
      </div>
      <p className="mt-3 font-mono text-2xl font-medium text-quanta-primary">
        {value}
      </p>
    </div>
  );
}

/* ── Graphe : aire (activité par jour) ───────────────────── */

function ActivityAreaChart({ values, labels }: { values: number[]; labels: string[] }) {
  const gradId = useId();
  const W = 560;
  const H = 170;
  const L = 10;
  const R = 10;
  const T = 16;
  const B = 26;

  const max = Math.max(1, ...values);
  const innerW = W - L - R;
  const innerH = H - T - B;
  const x = (i: number) => L + (i * innerW) / Math.max(values.length - 1, 1);
  const y = (v: number) => T + (1 - v / max) * innerH;

  const line = values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(v)}`).join(" ");
  const area = `${line} L${x(values.length - 1)},${H - B} L${x(0)},${H - B} Z`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="img"
      aria-label="Nombre d'analyses par jour sur les 14 derniers jours"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#C9A84C" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#C9A84C" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((k) => (
        <line
          key={k}
          x1={L}
          x2={W - R}
          y1={T + k * innerH}
          y2={T + k * innerH}
          stroke="rgba(255,255,255,0.05)"
          strokeWidth="1"
        />
      ))}
      <line
        x1={L}
        x2={W - R}
        y1={H - B}
        y2={H - B}
        stroke="rgba(255,255,255,0.09)"
        strokeWidth="1"
      />
      <path d={area} fill={`url(#${gradId})`} />
      <path d={line} fill="none" stroke="#C9A84C" strokeWidth="1.6" strokeLinejoin="round" />
      {values.map((v, i) =>
        v > 0 ? (
          <g key={i}>
            <circle cx={x(i)} cy={y(v)} r="3" fill="#E8D5A3">
              <title>{`${v} analyse(s) — ${labels[i]}`}</title>
            </circle>
          </g>
        ) : null,
      )}
      {labels.map((lab, i) =>
        i % 3 === 0 || i === labels.length - 1 ? (
          <text
            key={i}
            x={x(i)}
            y={H - 8}
            textAnchor="middle"
            fontSize="9"
            fill="rgba(154,154,168,0.8)"
            fontFamily="var(--font-geist), sans-serif"
          >
            {lab}
          </text>
        ) : null,
      )}
    </svg>
  );
}

/* ── Graphe : ligne (qualité perçue des bases) ───────────── */

function QualityLineChart({
  points,
}: {
  points: Array<{ score: number; date: number }>;
}) {
  const gradId = useId();
  const W = 560;
  const H = 170;
  const L = 10;
  const R = 10;
  const T = 16;
  const B = 26;

  if (points.length === 0) {
    return (
      <p className="flex h-[170px] items-center justify-center font-sans text-sm text-quanta-muted">
        Aucun score de confiance pour le moment.
      </p>
    );
  }

  const innerW = W - L - R;
  const innerH = H - T - B;
  const x = (i: number) => L + (i * innerW) / Math.max(points.length - 1, 1);
  const y = (score: number) =>
    T + (1 - Math.min(Math.max(score, 0), 1)) * innerH;

  const avg =
    points.reduce((s, p) => s + p.score, 0) / points.length;

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.score)}`).join(" ");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="img"
      aria-label="Score de confiance des analyses, dans l'ordre chronologique"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#00D4FF" />
          <stop offset="100%" stopColor="#8A63FF" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((k) => (
        <line
          key={k}
          x1={L}
          x2={W - R}
          y1={T + k * innerH}
          y2={T + k * innerH}
          stroke="rgba(255,255,255,0.05)"
          strokeWidth="1"
        />
      ))}
      <line
        x1={L}
        x2={W - R}
        y1={y(avg)}
        y2={y(avg)}
        stroke="#34D399"
        strokeWidth="1"
        strokeDasharray="4 5"
        opacity="0.7"
      />
      <line
        x1={L}
        x2={W - R}
        y1={H - B}
        y2={H - B}
        stroke="rgba(255,255,255,0.09)"
        strokeWidth="1"
      />
      <path d={path} fill="none" stroke={`url(#${gradId})`} strokeWidth="1.6" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.score)} r="3" fill="#E8D5A3">
          <title>{`${Math.round(p.score * 100)} % — ${formatDay(p.date)}`}</title>
        </circle>
      ))}
      <text
        x={W - R}
        y={y(avg) - 6}
        textAnchor="end"
        fontSize="9"
        fill="#34D399"
        fontFamily="var(--font-geist), sans-serif"
      >
        moyenne {Math.round(avg * 100)} %
      </text>
      <text
        x={L}
        y={H - 8}
        fontSize="9"
        fill="rgba(154,154,168,0.8)"
        fontFamily="var(--font-geist), sans-serif"
      >
        {formatDay(points[0].date)}
      </text>
      <text
        x={W - R}
        y={H - 8}
        textAnchor="end"
        fontSize="9"
        fill="rgba(154,154,168,0.8)"
        fontFamily="var(--font-geist), sans-serif"
      >
        {formatDay(points[points.length - 1].date)}
      </text>
    </svg>
  );
}

/* ── Graphe : barres (énergie de calcul par jour) ────────── */

function ComputeBarsChart({ values, labels }: { values: number[]; labels: string[] }) {
  const gradId = useId();
  const W = 560;
  const H = 150;
  const L = 10;
  const R = 10;
  const T = 14;
  const B = 24;

  const max = Math.max(60, ...values);
  const innerW = W - L - R;
  const innerH = H - T - B;
  const slot = innerW / values.length;
  const barW = Math.min(slot * 0.55, 26);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="img"
      aria-label="Temps de calcul total investi par jour sur les 14 derniers jours"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#8A63FF" />
          <stop offset="100%" stopColor="#8A63FF" stopOpacity="0.25" />
        </linearGradient>
      </defs>
      <line
        x1={L}
        x2={W - R}
        y1={H - B}
        y2={H - B}
        stroke="rgba(255,255,255,0.09)"
        strokeWidth="1"
      />
      {values.map((v, i) => {
        const h = (v / max) * innerH;
        const bx = L + i * slot + (slot - barW) / 2;
        const by = H - B - h;
        return v > 0 ? (
          <rect key={i} x={bx} y={by} width={barW} height={h} rx="3" fill={`url(#${gradId})`}>
            <title>{`${formatDuration(v)} de calcul — ${labels[i]}`}</title>
          </rect>
        ) : null;
      })}
      {labels.map((lab, i) =>
        i % 3 === 0 || i === labels.length - 1 ? (
          <text
            key={i}
            x={L + i * slot + slot / 2}
            y={H - 8}
            textAnchor="middle"
            fontSize="9"
            fill="rgba(154,154,168,0.8)"
            fontFamily="var(--font-geist), sans-serif"
          >
            {lab}
          </text>
        ) : null,
      )}
    </svg>
  );
}

/* ── Panneau ─────────────────────────────────────────────── */

export function InsightsPanel({ analyses }: { analyses: InsightAnalysis[] }) {
  const insights = useMemo(() => buildInsights(analyses), [analyses]);

  if (analyses.length === 0) {
    return null;
  }

  return (
    <section aria-label="Statistiques d'usage QUANTA" className="mt-14 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="hud-label text-quanta-muted">Votre activité</p>
          <h2 className="mt-2 font-brand text-2xl font-extralight text-quanta-primary">
            Comment QUANTA travaille pour vous
          </h2>
          <p className="mt-2 max-w-xl font-sans text-sm leading-relaxed text-quanta-secondary">
            Volume d&apos;analyses, qualité perçue des bases et énergie de calcul
            — l&apos;usage, sans jamais exposer la mécanique interne.
          </p>
        </div>
      </div>

      {/* Tuiles */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          icon={<Database strokeWidth={1.5} className="size-4 text-quanta-gold" />}
          label="Analyses totales"
          value={String(insights.total)}
          tone="text-quanta-gold"
        />
        <StatTile
          icon={<Activity strokeWidth={1.5} className="size-4 text-quanta-cyan" />}
          label="Cette semaine"
          value={String(insights.thisWeek)}
          tone="text-quanta-cyan"
        />
        <StatTile
          icon={<Gauge strokeWidth={1.5} className="size-4 text-quanta-emerald" />}
          label="Score moyen"
          value={
            insights.avgConfidence !== null
              ? `${Math.round(insights.avgConfidence * 100)} %`
              : "—"
          }
          tone="text-quanta-emerald"
        />
        <StatTile
          icon={<Timer strokeWidth={1.5} className="size-4 text-quanta-violet-2" />}
          label="Temps moyen"
          value={insights.avgSeconds !== null ? formatDuration(insights.avgSeconds) : "—"}
          tone="text-quanta-violet-2"
        />
      </div>

      {/* Graphes */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="glass glow-card rounded-card p-6">
          <p className="hud-label text-quanta-muted">Activité des analyses</p>
          <p className="mt-1 font-sans text-xs text-quanta-secondary">
            Analyses lancées par jour — 14 derniers jours.
          </p>
          <div className="mt-4">
            <ActivityAreaChart values={insights.perDay} labels={insights.dayLabels} />
          </div>
        </div>

        <div className="glass glow-card rounded-card p-6">
          <p className="hud-label text-quanta-muted">Qualité des bases analysées</p>
          <p className="mt-1 font-sans text-xs text-quanta-secondary">
            Score de confiance de chaque analyse, chronologique.
          </p>
          <div className="mt-4">
            <QualityLineChart points={insights.confidence} />
          </div>
        </div>

        <div className="glass glow-card rounded-card p-6 lg:col-span-2">
          <p className="hud-label text-quanta-muted">Énergie de calcul</p>
          <p className="mt-1 font-sans text-xs text-quanta-secondary">
            Temps total de calcul investi par jour — la charge que QUANTA
            consomme pour vous, sans en révéler la mécanique.
          </p>
          <div className="mt-4">
            <ComputeBarsChart
              values={insights.secondsPerDay}
              labels={insights.dayLabels}
            />
          </div>
        </div>
      </div>

      <p className="font-sans text-xs text-quanta-muted">
        Envie d&apos;aller plus loin ?{" "}
        <Link
          href="/"
          className="text-quanta-cyan transition-quanta hover:text-quanta-violet-2"
        >
          Lancez une nouvelle analyse
        </Link>
        .
      </p>
    </section>
  );
}
