"use client";

import { useEffect, useRef } from "react";

/**
 * Traînée du curseur — étoile filante v4 « ruban continu, embrasée par
 * la vitesse ».
 *
 * La v2 dessinait la queue en segments successifs : si fluides soient
 * les échantillons, chaque raccord restait visible (bandes, perles) dès
 * que le geste forçait des virages serrés. La v3 change de méthode :
 *
 * - Échantillonnage TEMPOREL : la tête poursuit le curseur en ressort
 *   amorti et un point d'historique est ajouté à chaque frame — densité
 *   constante, même dans les mouvements brusques.
 * - Lissage Catmull-Rom (centripète) : le centre du ruban est une
 *   courbe unique dérivée des points bruts ; les virages deviennent des
 *   arcs, jamais des coudes.
 * - La SILHOUETTE du ruban est construite en un seul polygone : pour
 *   chaque échantillon de la courbe, deux points décalés
 *   perpendiculairement à l'axe, épaisseur croissante vers la tête,
 *   puis remplissage d'un trait — un seul draw call, donc
 *   mathématiquement aucun segment ni raccord visible.
 * - Couleur : dégradé or → champagne projeté le long de l'axe du
 *   ruban (axes principaux), recalculé par frame.
 * - Blending additif + halo radial doux sur la tête.
 * - RÉACTIVITÉ À LA VITESSE : la vitesse du geste pilote un facteur
 *   d'embrasement (attaque rapide, extinction lente — comme un métal
 *   chauffé). Il allonge la queue (12 → 46 points), augmente la
 *   luminosité du dégradé, l'épaisseur du ruban et le rayon du halo :
 *   geste vif = étoile filante éblouissante, geste posé = lueur discrète.
 *
 * Mort douce : le curseur posé, la queue se rétracte (~0,8 s) par
 * décalage d'historique. Tactile et prefers-reduced-motion : rien.
 */

const HISTORY_MAX = 46; // points bruts conservés (≈ 0,38 s de vol)
const CURVE_SUBDIV = 5; // subdivisions Catmull-Rom entre deux points
const WIDTH_HEAD = 1.6; // px — demi-épaisseur au niveau de la tête
const WIDTH_TAIL = 0.25; // px — demi-épaisseur au bout de la queue
const RETRACT_STEP = 0.018; // s par point retiré à la mort → ~0,8 s
/* ── Embrasement : pilotage par la vitesse ── */
const TAIL_MIN = 12; // points de queue au repos
const SPEED_FULL = 2200; // px/s — geste considéré à pleine vitesse
const ATTACK = 12; // embrase vite (s^-1)
const DECAY = 2.2; // s'éteint lentement (s^-1)
const GOLD = { r: 201, g: 168, b: 76 }; // quanta-gold #C9A84C
const CHAMPAGNE = { r: 232, g: 213, b: 163 }; // quanta-gold-2 #E8D5A3
const HEADGLOW = "243, 231, 198"; // champagne clair pour le halo

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
    const history: { x: number; y: number }[] = [];
    let raf = 0;
    let running = false;
    let settleClock = 0;
    let lastTime = performance.now();
    /* 0 = repos, 1 = geste éblouissant. Attaque rapide, queue lente. */
    let speedFactor = 0;
    let prevTargetX = target.x;
    let prevTargetY = target.y;

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

    /** Spline Catmull-Rom centripète : retourne `subdiv` points entre
     *  p1 et p2 (p0, p3 = voisines), jamais de rebond. */
    const catmullRom = (
      p0: { x: number; y: number },
      p1: { x: number; y: number },
      p2: { x: number; y: number },
      p3: { x: number; y: number },
      subdiv: number,
    ): { x: number; y: number }[] => {
      const out: { x: number; y: number }[] = [];
      for (let i = 0; i < subdiv; i += 1) {
        const t = i / subdiv;
        const t2 = t * t;
        const t3 = t2 * t;
        out.push({
          x:
            0.5 *
            (2 * p1.x +
              (-p0.x + p2.x) * t +
              (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 +
              (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3),
          y:
            0.5 *
            (2 * p1.y +
              (-p0.y + p2.y) * t +
              (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 +
              (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3),
        });
      }
      return out;
    };

    const tick = (now: number) => {
      let dt = (now - lastTime) / 1000;
      lastTime = now;
      if (dt > 0.05) {
        dt = 0.05;
      }

      /* 1 — Ressort amorti sur la tête (framerate-indépendant). */
      const stiffness = 300;
      const damping = 26;
      const ax = (target.x - head.x) * stiffness - headV.x * damping;
      const ay = (target.y - head.y) * stiffness - headV.y * damping;
      headV.x += ax * dt;
      headV.y += ay * dt;
      head.x += headV.x * dt;
      head.y += headV.y * dt;

      /* 1bis — Vitesse du geste (la main, pas le ressort) : embrase
         vite, s'éteint lentement. Les téléportations du pointeur sont
         plafonnées pour ne pas créer de pic artificiel. */
      const gestSpeed = Math.min(
        Math.hypot(target.x - prevTargetX, target.y - prevTargetY) / dt,
        4000,
      );
      prevTargetX = target.x;
      prevTargetY = target.y;
      const raw = Math.min(gestSpeed / SPEED_FULL, 1);
      /* Attaque rapide (montée), extinction lente (descente). */
      const rate = raw > speedFactor ? ATTACK : DECAY;
      speedFactor += (raw - speedFactor) * Math.min(1, dt * rate);
      speedFactor = Math.min(1, Math.max(0, speedFactor));

      /* 2 — Historique temporel : un point par frame. */
      const lastPt = history[history.length - 1];
      if (!lastPt || Math.hypot(head.x - lastPt.x, head.y - lastPt.y) > 0.4) {
        history.push({ x: head.x, y: head.y });
        if (history.length > HISTORY_MAX) {
          history.shift();
        }
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      /* 3 — Courbe unique Catmull-Rom. La vitesse de l'embrasement
         allonge la queue : on ne donne à la spline que les
         `tailCount` points les plus récents de l'historique. */
      const curve: { x: number; y: number }[] = [];
      const tailCount = Math.round(
        TAIL_MIN + (HISTORY_MAX - TAIL_MIN) * speedFactor,
      );
      const used = history.slice(Math.max(0, history.length - tailCount));
      const n = used.length;
      if (n >= 2) {
        curve.push(used[n - 1]); // la tête fait partie de la courbe
        for (let i = 0; i < n - 1; i += 1) {
          const p1 = used[n - 1 - i];
          const p2 = used[n - 2 - i];
          const p0 = used[Math.max(0, n - i - 3)];
          const p3 = n - i - 4 >= 0 ? used[n - i - 4] : p2;
          curve.push(...catmullRom(p0, p1, p2, p3, CURVE_SUBDIV));
        }

        /* 4 — Silhouette : un seul polygone épaisseur variable. */
        const left: { x: number; y: number }[] = [];
        const right: { x: number; y: number }[] = [];
        const m = curve.length;
        for (let i = 0; i < m; i += 1) {
          const p = curve[i];
          const prev = curve[Math.max(0, i - 1)];
          const next = curve[Math.min(m - 1, i + 1)];
          // Tangente centrée puis normale : direction lisse du ruban.
          const tx = next.x - prev.x;
          const ty = next.y - prev.y;
          const len = Math.hypot(tx, ty) || 1;
          const nx = -ty / len;
          const ny = tx / len;
          const t = i / (m - 1); // 0 tête → 1 queue
          /* L'embrasement gonfle légèrement le ruban (jusqu'à +35 %). */
          const widthScale = 1 + 0.35 * speedFactor;
          const half =
            (WIDTH_TAIL + (WIDTH_HEAD - WIDTH_TAIL) * Math.pow(1 - t, 1.6)) *
            widthScale *
            dpr;
          left.push({ x: p.x + nx * half, y: p.y + ny * half });
          right.push({ x: p.x - nx * half, y: p.y - ny * half });
        }

        /* Dégradé or → champagne le long de l'axe du ruban. */
        let minX = Infinity;
        let minY = Infinity;
        let maxX = -Infinity;
        let maxY = -Infinity;
        for (const p of curve) {
          minX = Math.min(minX, p.x);
          minY = Math.min(minY, p.y);
          maxX = Math.max(maxX, p.x);
          maxY = Math.max(maxY, p.y);
        }
        const cx = (minX + maxX) / 2;
        const cy = (minY + maxY) / 2;
        let sxx = 0;
        let syy = 0;
        let sxy = 0;
        for (const p of curve) {
          const dx = p.x - cx;
          const dy = p.y - cy;
          sxx += dx * dx;
          syy += dy * dy;
          sxy += dx * dy;
        }
        const angle = 0.5 * Math.atan2(2 * sxy, sxx - syy);
        const axisX = Math.cos(angle);
        const axisY = Math.sin(angle);
        let dotMin = Infinity;
        let dotMax = -Infinity;
        for (const p of curve) {
          const d = (p.x - cx) * axisX + (p.y - cy) * axisY;
          dotMin = Math.min(dotMin, d);
          dotMax = Math.max(dotMax, d);
        }

        /* L'embrasement augmente la luminosité aux deux premiers stops. */
        const headAlpha = 0.75 + 0.25 * speedFactor;
        const midAlpha = 0.55 + 0.3 * speedFactor;
        const grad = ctx.createLinearGradient(
          (cx + axisX * dotMin) * dpr,
          (cy + axisY * dotMin) * dpr,
          (cx + axisX * dotMax) * dpr,
          (cy + axisY * dotMax) * dpr,
        );
        grad.addColorStop(
          0,
          `rgba(${CHAMPAGNE.r}, ${CHAMPAGNE.g}, ${CHAMPAGNE.b}, ${headAlpha})`,
        );
        grad.addColorStop(
          0.45,
          `rgba(${GOLD.r}, ${GOLD.g}, ${GOLD.b}, ${midAlpha})`,
        );
        grad.addColorStop(1, `rgba(${GOLD.r}, ${GOLD.g}, ${GOLD.b}, 0)`);

        ctx.globalCompositeOperation = "lighter";
        ctx.beginPath();
        ctx.moveTo(left[0].x * dpr, left[0].y * dpr);
        for (let i = 1; i < left.length; i += 1) {
          ctx.lineTo(left[i].x * dpr, left[i].y * dpr);
        }
        for (let i = right.length - 1; i >= 0; i -= 1) {
          ctx.lineTo(right[i].x * dpr, right[i].y * dpr);
        }
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();
        /* Liseré : même dessin en trait, résout l'antialiasing de bord. */
        ctx.strokeStyle = grad;
        ctx.lineWidth = 0.6 * dpr;
        ctx.stroke();

        /* Halo de la tête — l'étoile de l'étoile filante. Il grandit
           et s'éblouit avec l'embrasement. */
        const h = curve[0];
        const hx = h.x * dpr;
        const hy = h.y * dpr;
        const glowR = (14 + 10 * speedFactor) * dpr;
        const glowA = 0.38 + 0.3 * speedFactor;
        const glow = ctx.createRadialGradient(hx, hy, 0, hx, hy, glowR);
        glow.addColorStop(0, `rgba(${HEADGLOW}, ${glowA})`);
        glow.addColorStop(
          0.4,
          `rgba(${CHAMPAGNE.r}, ${CHAMPAGNE.g}, ${CHAMPAGNE.b}, ${glowA * 0.4})`,
        );
        glow.addColorStop(1, `rgba(${CHAMPAGNE.r}, ${CHAMPAGNE.g}, ${CHAMPAGNE.b}, 0)`);
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(hx, hy, glowR, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalCompositeOperation = "source-over";
      }

      /* 5 — Mort douce : curseur posé → la queue se rétracte. */
      const settled =
        Math.hypot(target.x - head.x, target.y - head.y) < 0.5 &&
        Math.hypot(headV.x, headV.y) < 5;
      if (settled) {
        settleClock += dt;
        while (settleClock >= RETRACT_STEP && history.length > 0) {
          settleClock -= RETRACT_STEP;
          history.shift();
        }
      } else {
        settleClock = 0;
      }
      if (!settled || history.length > 0) {
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
