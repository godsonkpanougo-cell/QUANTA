"use client";

import { useEffect, useRef } from "react";

/**
 * Poussière d'or — fines particules qui s'échappent du curseur en
 * mouvement, en écho au CursorGlow. Canvas plein écran, decoratif
 * (pointer-events-none), sous le header. La boucle rAF ne tourne que
 * quand des particules sont vivantes ; désactivée sur tactile
 * (pointer: fine requis) et sous prefers-reduced-motion.
 */

interface DustParticle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  age: number;
  life: number;
  size: number;
  champagne: boolean;
}

const MAX_PARTICLES = 220;
const EMISSION_STEP = 12; // px de course du pointeur → 1 particule
const MAX_PER_EVENT = 3;
const FRAME = 1 / 60;

export function GoldDust() {
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

    const particles: DustParticle[] = [];
    let last: { x: number; y: number } | null = null;
    let carry = 0;
    let raf = 0;
    let running = false;

    const spawn = (x: number, y: number, dx: number, dy: number) => {
      if (particles.length >= MAX_PARTICLES) {
        particles.shift();
      }
      particles.push({
        x,
        y,
        vx: -dx * 0.05 + (Math.random() - 0.5) * 0.4,
        vy: -dy * 0.05 - 0.1 + (Math.random() - 0.5) * 0.4,
        age: 0,
        life: 0.65 + Math.random() * 0.75,
        size: 0.7 + Math.random() * 1.6,
        champagne: Math.random() < 0.3,
      });
    };

    const tick = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let i = particles.length - 1; i >= 0; i -= 1) {
        const p = particles[i];
        p.age += FRAME;
        if (p.age >= p.life) {
          particles.splice(i, 1);
          continue;
        }
        p.x += p.vx;
        p.y += p.vy;
        p.vx *= 0.965;
        p.vy *= 0.965;
        const k = 1 - p.age / p.life;
        ctx.beginPath();
        ctx.fillStyle = p.champagne
          ? `rgba(232, 213, 163, ${0.75 * k})`
          : `rgba(201, 168, 76, ${0.8 * k})`;
        ctx.arc(
          p.x * dpr,
          p.y * dpr,
          p.size * dpr * (0.55 + 0.45 * k),
          0,
          Math.PI * 2,
        );
        ctx.fill();
      }
      if (particles.length > 0) {
        raf = requestAnimationFrame(tick);
      } else {
        running = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
    };

    const wake = () => {
      if (!running && !document.hidden) {
        running = true;
        raf = requestAnimationFrame(tick);
      }
    };

    const onPointerMove = (event: PointerEvent) => {
      if (last !== null) {
        const dx = event.clientX - last.x;
        const dy = event.clientY - last.y;
        carry += Math.hypot(dx, dy);
        let emitted = 0;
        while (carry >= EMISSION_STEP && emitted < MAX_PER_EVENT) {
          carry -= EMISSION_STEP;
          emitted += 1;
          spawn(event.clientX, event.clientY, dx, dy);
        }
        if (emitted > 0) {
          wake();
        }
      }
      last = { x: event.clientX, y: event.clientY };
    };

    const onVisibility = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (particles.length > 0) {
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
