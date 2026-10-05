"use client";

import { useEffect, useRef } from "react";

/**
 * Traînée du curseur — étoile filante : une lique ultra fluide qui ne
 * se casse jamais en segments. Trois clés du rendu :
 *
 * 1. Échantillonnage TEMPOREL (à chaque frame) et non au déplacement :
 *    les virages serrés et les arrêts produisent autant de points que
 *    les lignes droites — la courbe garde une densité constante.
 * 2. Un seul chemin par frame avec dégradé continu d'alpha et
 *    d'épaisseur : aucun raccord entre segments, donc aucune bande.
 * 3. Blending additif (« lighter ») : les chevauchements s'additionnent
 *    en lumière au lieu de dessiner des jonctions plus sombres.
 *
 * Physique : la tête poursuit le curseur avec un ressort amorti
 * (interpolation indépendante du framerate) — elle glisse, ne saute
 * jamais, même quand la souris téléporte. Le corps suit la tête :
 * trajectoire lissée deux fois, d'où l'élégance d'une comète.
 *
 * Canvas décoratif (pointer-events-none), sous le header. Boucle rAF
 * arrêtée quand la comète est éteinte ; désactivée sur tactile
 * (pointer: fine requis) et sous prefers-reduced-motion.
 */

const TAIL_POINTS = 44; // longueur de la comète (en points de courbe)
const RETRACT_STEP = 0.018; // s par point à la retraite → mort en ~0,8 s
const GOLD = { r: 201, g: 168, b: 76 }; // quanta-gold #C9A84C
const CHAMPAGNE = { r: 232, g: 213, b: 163 }; // quanta-gold-2 #E8D5A3

/** Alpha continu le long de la queue — jamais de rupture de pente. */
function tailAlpha(t: number): number {
  // t=0 tête → t=1 bout de queue. Sans palier : dérivée continue.
  return Math.pow(1 - t, 1.7) * 0.9;
}

/** Épaisseur continue : comète fine qui s'effile en aiguille. */
function tailWidth(t: number): number {
  return 0.4 + 1.1 * Math.pow(1 - t, 2.2);
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

    const target = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
    const head = { ...target };
    const headV = { x: 0, y: 0 };
    /* Historique de positions de la tête (le corps de la comète). */
    const trail: { x: number; y: number }[] = [];
    let raf = 0;
    let running = false;
    let settleClock = 0;
    let lastTime = performance.now();

    const wake = () => {
      if (!running && !document.hidden) {
        running = true;
        lastTime = performance.now();
        raf = requestAnimationFrame(tick);
      }
    };

    const onPointerMove = (event: PointerEvent) => {
      target.x = event.clientX;
      target.y = event.clientY;
      wake();
    };

    const tick = (now: number) => {
      let dt = (now - lastTime) / 1000;
      lastTime = now;
      if (dt > 0.05) {
        dt = 0.05; // onglet repris : pas de saut
      }

      /* 1 — Ressort amorti : la tête glisse vers le curseur.
         Indépendant du framerate (compensation exponentielle). */
      const stiffness = 260;
      const damping = 22;
      const ax = (target.x - head.x) * stiffness - headV.x * damping;
      const ay = (target.y - head.y) * stiffness - headV.y * damping;
      headV.x += ax * dt;
      headV.y += ay * dt;
      head.x += headV.x * dt;
      head.y += headV.y * dt;

      /* 2 — Le corps enregistre la tête à chaque frame : densité
         constante, virages aussi bien servis que les lignes droites. */
      const lastPt = trail[trail.length - 1];
      if (!lastPt || Math.hypot(head.x - lastPt.x, head.y - lastPt.y) > 0.35) {
        trail.push({ x: head.x, y: head.y });
        if (trail.length > TAIL_POINTS) {
          trail.shift();
        }
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      /* 3 — Un seul chemin continu : dégradé d'alpha et d'épaisseur
         dessinés dans la même passe, blending additif. */
      const n = trail.length;
      if (n >= 2) {
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        for (let i = 1; i < n; i += 1) {
          /* trail[n-1] = tête (t=0) → trail[0] = bout de queue (t≈1). */
          const tMid = (n - i - 0.5) / n;
          const p0 = trail[i - 1];
          const p1 = trail[i];
          const alpha = tailAlpha(tMid);
          if (alpha < 0.015) {
            continue;
          }
          // Teinte : champagne à la tête → or vers la queue.
          const k = 0.55 * (1 - tMid);
          const r = Math.round(GOLD.r + (CHAMPAGNE.r - GOLD.r) * k);
          const g = Math.round(GOLD.g + (CHAMPAGNE.g - GOLD.g) * k);
          const b = Math.round(GOLD.b + (CHAMPAGNE.b - GOLD.b) * k);
          ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
          ctx.lineWidth = tailWidth(tMid) * dpr;
          ctx.beginPath();
          ctx.moveTo(p0.x * dpr, p0.y * dpr);
          ctx.lineTo(p1.x * dpr, p1.y * dpr);
          ctx.stroke();
        }

        /* Halo de la tête : la « étoile » de l'étoile filante.
           Il s'éteint avec la comète quand le mouvement cesse. */
        const headAlpha = tailAlpha(0) * (n / TAIL_POINTS);
        const hx = head.x * dpr;
        const hy = head.y * dpr;
        const grad = ctx.createRadialGradient(hx, hy, 0, hx, hy, 16 * dpr);
        grad.addColorStop(0, `rgba(243, 231, 198, ${0.5 * headAlpha})`);
        grad.addColorStop(0.35, `rgba(${CHAMPAGNE.r}, ${CHAMPAGNE.g}, ${CHAMPAGNE.b}, ${0.22 * headAlpha})`);
        grad.addColorStop(1, "rgba(232, 213, 163, 0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(hx, hy, 16 * dpr, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalCompositeOperation = "source-over";
      }

      /* La comète vit tant que la tête n'est pas posée sur le curseur.
         Posée : la queue se rétracte à vitesse constante (horloge,
         indépendante du framerate) — l'étoile filante meurt en ~0,8 s
         au lieu de rester figée à l'écran. */
      const settled =
        Math.hypot(target.x - head.x, target.y - head.y) < 0.5 &&
        Math.hypot(headV.x, headV.y) < 5;
      if (settled) {
        settleClock += dt;
        while (settleClock >= RETRACT_STEP && trail.length > 0) {
          settleClock -= RETRACT_STEP;
          trail.shift();
        }
      } else {
        settleClock = 0;
      }
      if (!settled || trail.length > 0) {
        raf = requestAnimationFrame(tick);
      } else {
        running = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
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
