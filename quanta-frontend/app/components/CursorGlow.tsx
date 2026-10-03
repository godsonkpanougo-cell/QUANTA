"use client";

import { useEffect, useRef } from "react";

/**
 * Lumière ambiante qui suit le curseur — deux halos (or + cyan) en
 * mix-blend screen, interpolés en rAF pour un mouvement fluide.
 * Désactivée sur tactile et prefers-reduced-motion (via CSS).
 */
export function CursorGlow() {
  const glowARef = useRef<HTMLDivElement>(null);
  const glowBRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const glowA = glowARef.current;
    const glowB = glowBRef.current;
    if (!glowA || !glowB) {
      return;
    }

    let raf = 0;
    let mouse = { x: window.innerWidth / 2, y: window.innerHeight * 0.25 };
    const posA = { ...mouse };
    const posB = { ...mouse };

    const onMouseMove = (event: MouseEvent) => {
      mouse = { x: event.clientX, y: event.clientY };
    };

    const tick = () => {
      // Halo or : suit le curseur de près ; halo cyan : traîne loin derrière
      posA.x += (mouse.x - posA.x) * 0.09;
      posA.y += (mouse.y - posA.y) * 0.09;
      posB.x += (mouse.x - posB.x) * 0.035;
      posB.y += (mouse.y + 60 - posB.y) * 0.035;

      glowA.style.transform = `translate3d(${posA.x}px, ${posA.y}px, 0)`;
      glowB.style.transform = `translate3d(${posB.x}px, ${posB.y}px, 0)`;
      raf = requestAnimationFrame(tick);
    };

    window.addEventListener("mousemove", onMouseMove, { passive: true });
    raf = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div aria-hidden className="pointer-events-none">
      <div ref={glowBRef} className="cursor-glow-b" />
      <div ref={glowARef} className="cursor-glow-a" />
    </div>
  );
}
