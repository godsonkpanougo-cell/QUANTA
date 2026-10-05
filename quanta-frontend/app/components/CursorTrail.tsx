"use client";

import { useEffect, useRef } from "react";

/**
 * Traînée du curseur — étoile filante v5 « ruban homogène ».
 *
 * La fluidité rigoureuse repose sur quatre garde-fous, chacun corrige
 * un défaut précis : les « sommets » (débords de spline), les
 * « coupures » de lumière et la rugosité de bord.
 *
 * 1. POINTS ÉQUIDISTANTS : l'historique est rééchantillonné à longueur
 *    d'arc constante (6px) avant tout calcul. Une spline nourrie de
 *    points irréguliers produit des ondulations parasites — les
 *    « sommets ».uniformément espacés, elle est géométriquement
 *    stable.
 * 2. LISSAGE CHAIKIN (borné) : deux passes de coupe d'angles donnent
 *    une courbe qui reste PAR DÉFINITION dans l'enveloppe des points
 *    d'entrée — aucune pointe ne peut dépasser la trajectoire
 *    physique, contrairement à Catmull-Rom sur nœuds denses.
 * 3. DÉGRADÉ ORIENTÉ : les extrémités sont attachées QUEUE → TÊTE
 *    (le dégradé suit le corps, jamais inversé par le sens du
 *    mouvement — la « coupure » de lumière disparaît).
 * 4. BORDS ANTIALIASÉS : la silhouette est une surface fermée par une
 *    pointe conique, dessinée sans contour additionnel (le liseré
 *    additif créait un double bord irrégulier).
 *
 * + Tête à ressort amorti (framerate-indépendant), échantillonnage
 *   temporel, réactivité à la vitesse (queue 12→46 pts, luminosité,
 *   épaisseur, halo), mort douce ~0,8 s, blending additif, désactivée
 *   sur tactile / prefers-reduced-motion.
 */

const HISTORY_MAX = 46; // points bruts conservés (≈ 0,38 s de vol)
const SPACING = 6; // px — distance constante entre points rééchantillonnés
const SMOOTH_PASSES = 2; // passes Chaikin
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

    /**
     * Rééchantillonnage à longueur d'arc constante : marche le long de
     * la polyligne et dépose un point tous les `spacing` px. Résultat :
     * des nœuds équidistants quelle que soit la densité d'échan‎tillons
     * d'entrée (dense aux inversions, lâche en ligne droite).
     */
    const resample = (
      pts: { x: number; y: number }[],
      spacing: number,
    ): { x: number; y: number }[] => {
      const out: { x: number; y: number }[] = [pts[0]];
      let acc = 0;
      for (let i = 1; i < pts.length; i += 1) {
        let ax = pts[i - 1].x;
        let ay = pts[i - 1].y;
        const bx = pts[i].x;
        const by = pts[i].y;
        let segLen = Math.hypot(bx - ax, by - ay);
        while (acc + segLen >= spacing) {
          const k = (spacing - acc) / segLen;
          const px = ax + (bx - ax) * k;
          const py = ay + (by - ay) * k;
          out.push({ x: px, y: py });
          ax = px;
          ay = py;
          segLen = Math.hypot(bx - ax, by - ay);
          acc = 0;
        }
        acc += segLen;
      }
      out.push(pts[pts.length - 1]);
      return out;
    };

    /**
     * Lissage Chaïkin : coupe chaque coin (0,25 / 0,75) et insère les
     * deux nouveaux points. Courbe GARANTIE dans l'enveloppe convexe
     * des entrées — le ruban ne peut ni déborder ni produire de
     * sommets, quel que soit l'enchevêtrement de la trajectoire.
     */
    const chaikin = (
      pts: { x: number; y: number }[],
    ): { x: number; y: number }[] => {
      if (pts.length < 3) {
        return pts;
      }
      const out: { x: number; y: number }[] = [pts[0]];
      for (let i = 0; i < pts.length - 1; i += 1) {
        const a = pts[i];
        const b = pts[i + 1];
        out.push({
          x: a.x * 0.75 + b.x * 0.25,
          y: a.y * 0.75 + b.y * 0.25,
        });
        out.push({
          x: a.x * 0.25 + b.x * 0.75,
          y: a.y * 0.25 + b.y * 0.75,
        });
      }
      out.push(pts[pts.length - 1]);
      return out;
    };

    const smoothWork: { x: number; y: number }[] = [];
    const leftWork: { x: number; y: number }[] = [];
    const rightWork: { x: number; y: number }[] = [];

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
         vite, s'éteint lentement. Téléportations plafonnées. */
      const gestSpeed = Math.min(
        Math.hypot(target.x - prevTargetX, target.y - prevTargetY) / dt,
        4000,
      );
      prevTargetX = target.x;
      prevTargetY = target.y;
      const raw = Math.min(gestSpeed / SPEED_FULL, 1);
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

      /* 3 — La vitesse allonge la queue : sous-ensemble récent. */
      const tailCount = Math.round(
        TAIL_MIN + (HISTORY_MAX - TAIL_MIN) * speedFactor,
      );
      const used = history.slice(Math.max(0, history.length - tailCount));

      if (used.length >= 2) {
        /* 3a — Équidistance puis lissage Chaïkin : la géométrie
           ne peut plus créer de sommets. */
        const even = resample(used, SPACING);
        smoothWork.length = 0;
        smoothWork.push(...even);
        for (let pass = 0; pass < SMOOTH_PASSES; pass += 1) {
          const smoothed = chaikin(smoothWork);
          smoothWork.length = 0;
          smoothWork.push(...smoothed);
        }
        const curve = smoothWork;

        /* 3b — Silhouette : un seul polygone épaisseur variable. */
        const m = curve.length;
        leftWork.length = 0;
        rightWork.length = 0;
        /* Plan de la queue (t=1) pour attacher le dégradé du bon côté. */
        const tailPt = curve[m - 1];
        const headPt = curve[0];
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
          /* Effilement : constant sur le dernier tiers, plus de
             bord plat — la pointe se ferme en aiguille. */
          const shave = Math.pow(1 - t, 1.6);
          const half =
            (WIDTH_HEAD *
              widthScale *
              (WIDTH_TAIL / WIDTH_HEAD +
                (1 - WIDTH_TAIL / WIDTH_HEAD) *
                shave)) *
            dpr;
          leftWork.push({ x: p.x + nx * half, y: p.y + ny * half });
          rightWork.push({ x: p.x - nx * half, y: p.y - ny * half });
        }
        const left = leftWork;
        const right = rightWork;

        /* 3c — Dégradé du bon côté : de la QUEUE (or, transparent)
           vers la TÊTE (champagne, lumineux). Les coins du
           rectangle d'axe tiennent compte de l'inclinaison. */
        const headAlpha = 0.78 + 0.22 * speedFactor;
        const midAlpha = 0.55 + 0.3 * speedFactor;
        const grad = ctx.createLinearGradient(
          tailPt.x * dpr,
          tailPt.y * dpr,
          headPt.x * dpr,
          headPt.y * dpr,
        );
        grad.addColorStop(0, `rgba(${GOLD.r}, ${GOLD.g}, ${GOLD.b}, 0)`);
        grad.addColorStop(0.55, `rgba(${GOLD.r}, ${GOLD.g}, ${GOLD.b}, ${midAlpha})`);
        grad.addColorStop(1, `rgba(${CHAMPAGNE.r}, ${CHAMPAGNE.g}, ${CHAMPAGNE.b}, ${headAlpha})`);

        ctx.globalCompositeOperation = "lighter";
        /* Surface unique : côté gauche aller, retour côté droit,
           pointe de queue FERMÉE en rejoignant le dernier point
           central (aiguille), aucun contour additionnel. */
        ctx.beginPath();
        ctx.moveTo(left[0].x * dpr, left[0].y * dpr);
        for (let i = 1; i < m; i += 1) {
          ctx.lineTo(left[i].x * dpr, left[i].y * dpr);
        }
        for (let i = m - 1; i >= 0; i -= 1) {
          ctx.lineTo(right[i].x * dpr, right[i].y * dpr);
        }
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();

        /* Halo de la tête — l'étoile de l'étoile filante. Il grandit
           et s'éblouit avec l'embrasement. */
        const hx = headPt.x * dpr;
        const hy = headPt.y * dpr;
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

      /* 4 — Mort douce : curseur posé → la queue se rétracte. */
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
