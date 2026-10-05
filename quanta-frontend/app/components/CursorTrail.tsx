"use client";

import { useEffect, useRef } from "react";

/**
 * Traînée du curseur — une seule ligne dorée fine et continue, comme un
 * fil tendu derrière le pointeur. Rendue sur canvas plein écran :
 *
 * - Le ruban est une polyligne de positions échantillonnées ; chaque
 *   segment relie deux échantillons consécutifs, donc jamais de points
 *   détachés, même en mouvement brusque.
 * - Chaque échantillon vieillit et s'estompe individuellement : la
 *   longueur visible du fil correspond exactement à sa durée de vie —
 *   la ligne s'efface d'un bout à l'autre, sans disparition brutale.
 * - Un petit halo lumineux marque la tête du fil (côté curseur).
 *
 * Canvas décoratif (pointer-events-none), sous le header. Boucle rAF
 * arrêtée dès que le fil est éteint ; désactivée sur tactile
 * (pointer: fine requis) et sous prefers-reduced-motion.
 */

const MAX_POINTS = 260; // ~2 s de fil à 120 pts/s
const LIFE = 2; // s — durée de vie d'un échantillon = longueur du fil
const SAMPLE_SPACING = 12; // px de course du pointeur → 1 échantillon
const GOLD = { r: 201, g: 168, b: 76 }; // quanta-gold #C9A84C
const CHAMPAGNE = { r: 232, g: 213, b: 163 }; // quanta-gold-2 #E8D5A3

/** Profil d'estompage : la ligne meurt en douceur sur toute sa durée. */
function fade(t: number): number {
  // t=0 tête (fraîche) → t=1 queue (la plus ancienne).
  if (t < 0.7) {
    // Plateau lumineux puis descente douce vers la queue.
    return 0.85 - (t / 0.7) * 0.3;
  }
  const k = (t - 0.7) / 0.3;
  return 0.55 * (1 - k) * (1 - k);
}

export function CursorTrail() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    if (
      !window.matchMedia("(pointer: fine)").matches ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(window.innerWidth * dpr);
      canvas.height = Math.round(window.innerHeight * dpr);
    };
    resize();
    window.addEventListener("resize", resize, { passive: true });

    interface Point {
      x: number;
      y: number;
      age: number;
    }
    const points: Point[] = [];
    let last: { x: number; y: number } | null = null;
    let raf = 0;
    let running = false;
    let lastTime = performance.now();

    const onPointerMove = (event: PointerEvent) => {
      const x = event.clientX;
      const y = event.clientY;
      if (last === null) {
        last = { x, y };
        points.push({ x, y, age: 0 });
        wake();
        return;
      }
      // Interpolation : des échantillons réguliers même en geste rapide,
      // pour un fil continu sans cassure.
      const step = SAMPLE_SPACING;
      let dx = x - last.x;
      let dy = y - last.y;
      let dist = Math.hypot(dx, dy);
      while (dist >= step) {
        const k = step / dist;
        last = { x: last.x + dx * k, y: last.y + dy * k };
        dx = x - last.x;
        dy = y - last.y;
        dist = Math.hypot(dx, dy);
        points.push({ x: last.x, y: last.y, age: 0 });
        if (points.length > MAX_POINTS) {
          points.shift();
        }
        wake();
      }
    };

    const wake = () => {
      if (!running && !document.hidden) {
        running = true;
        lastTime = performance.now();
        raf = requestAnimationFrame(tick);
      }
    };

    const tick = (now: number) => {
      const dt = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (points.length > 0) {
        for (const p of points) {
          p.age += dt;
        }
        // Le fil vivant : les échantillons plus vieux que LIFE se retirent.
        while (points.length > 0 && points[0].age >= LIFE) {
          points.shift();
        }
        if (points.length >= 2) {
          ctx.lineCap = "round";
          ctx.lineJoin = "round";
          for (let i = 1; i < points.length; i += 1) {
            const prev = points[i - 1];
            const cur = points[i];
            const tPrev = prev.age / LIFE;
            const tCur = cur.age / LIFE;
            const alpha = (fade(tPrev) + fade(tCur)) / 2;
            if (alpha <= 0.01) {
              continue;
            }
            // La teinte glisse or → champagne vers la tête du fil.
            const headiness = 1 - tCur;
            const r = Math.round(GOLD.r + (CHAMPAGNE.r - GOLD.r) * headiness * 0.55);
            const g = Math.round(GOLD.g + (CHAMPAGNE.g - GOLD.g) * headiness * 0.55);
            const b = Math.round(GOLD.b + (CHAMPAGNE.b - GOLD.b) * headiness * 0.55);
            ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(prev.x * dpr, prev.y * dpr);
            ctx.lineTo(cur.x * dpr, cur.y * dpr);
            ctx.stroke();
          }
          // Halo discret sur la tête du fil.
          const head = points[points.length - 1];
          const headAlpha = fade(points[points.length - 1].age / LIFE);
          if (headAlpha > 0.05) {
            const grad = ctx.createRadialGradient(
              head.x * dpr,
              head.y * dpr,
              0,
              head.x * dpr,
              head.y * dpr,
              14 * dpr,
            );
            grad.addColorStop(0, `rgba(${CHAMPAGNE.r}, ${CHAMPAGNE.g}, ${CHAMPAGNE.b}, ${0.35 * headAlpha})`);
            grad.addColorStop(1, "rgba(232, 213, 163, 0)");
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(head.x * dpr, head.y * dpr, 14 * dpr, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        raf = requestAnimationFrame(tick);
      } else {
        running = false;
      }
    };

    const onVisibility = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else {
        wake();
      }
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-30 h-full w-full"
    />
  );
}
