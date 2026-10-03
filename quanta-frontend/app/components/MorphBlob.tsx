"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

export interface MorphBlobProps {
  /** Index de l'étape courante du pipeline (0-7) — pilote la morphologie */
  step: number;
  /** Analyse terminée : la forme se cristallise, calme et dorée */
  done?: boolean;
  /** Erreur : la forme devient agitée et repasse à l'or */
  error?: boolean;
}

/**
 * Paramètres de déformation par étape du pipeline :
 * chaque étape donne au maillage une personnalité distincte
 * (respiration lente, vagues de nettoyage, agitation des calculs,
 * cristallisation finale dorée).
 */
const STEP_PARAMS: Array<{
  amp: number;
  freq: number;
  speed: number;
  mix: number;
}> = [
  { amp: 0.22, freq: 1.6, speed: 0.35, mix: 0.7 }, // Réception
  { amp: 0.34, freq: 2.2, speed: 0.55, mix: 0.7 }, // Diagnostic
  { amp: 0.28, freq: 3.4, speed: 0.85, mix: 0.75 }, // Nettoyage
  { amp: 0.45, freq: 1.3, speed: 0.5, mix: 0.6 }, // Sélection des tests
  { amp: 0.55, freq: 2.7, speed: 1.15, mix: 0.85 }, // Calculs
  { amp: 0.26, freq: 4.2, speed: 1.0, mix: 0.8 }, // Vérification
  { amp: 0.5, freq: 1.9, speed: 0.7, mix: 0.55 }, // Interprétation
  { amp: 0.1, freq: 1.2, speed: 0.22, mix: 0.15 }, // Finalisation
];

const DONE_PARAMS = { amp: 0.05, freq: 1.0, speed: 0.12, mix: 0.12 };
const ERROR_PARAMS = { amp: 0.4, freq: 3.0, speed: 1.6, mix: 0.0 };

/* Bruit simplex 3D (Ashima Arts / Stefan Gustavson — MIT) */
const NOISE_GLSL = `
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 10.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
      i.z + vec4(0.0, i1.z, i2.z, 1.0))
      + i.y + vec4(0.0, i1.y, i2.y, 1.0))
      + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.5 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 105.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}
`;

const VERTEX_SHADER = `
uniform float uTime;
uniform float uAmp;
uniform float uFreq;
uniform float uSpeed;
uniform float uTwist;
varying float vNoise;
varying vec3 vNormalV;
varying vec3 vViewDir;
${NOISE_GLSL}
void main() {
  vec3 dir = normalize(position);
  float t = uTime * uSpeed;
  float n = snoise(dir * uFreq + t * 0.7);
  n += 0.35 * snoise(dir * uFreq * 2.3 - t);
  vNoise = n;
  vec3 pos = position;
  float angle = position.y * uTwist + t * 0.4;
  float c = cos(angle);
  float s = sin(angle);
  pos.xz = mat2(c, -s, s, c) * pos.xz;
  pos += normal * n * uAmp;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  vNormalV = normalize(normalMatrix * normal);
  vViewDir = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}
`;

/* Surface translucide : corps de verre, lueur sur les bords (fresnel) */
const FRAG_SOLID = `
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform float uMix;
varying float vNoise;
varying vec3 vNormalV;
varying vec3 vViewDir;
void main() {
  float fres = pow(1.0 - abs(dot(normalize(vNormalV), normalize(vViewDir))), 2.0);
  float k = clamp(uMix * (vNoise * 0.5 + 0.5), 0.0, 1.0);
  vec3 base = mix(uColorA, uColorB, k);
  vec3 col = base * (0.20 + 0.9 * fres) + vec3(1.0, 0.95, 0.82) * fres * 0.30;
  float alpha = 0.14 + 0.72 * fres;
  gl_FragColor = vec4(col, alpha);
}
`;

/* Maillage polygonal discret par-dessus la surface */
const FRAG_WIRE = `
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform float uMix;
varying float vNoise;
varying vec3 vNormalV;
varying vec3 vViewDir;
void main() {
  vec3 col = mix(uColorA, uColorB, clamp(uMix * (vNoise * 0.5 + 0.5), 0.0, 1.0));
  float alpha = 0.05 + 0.13 * max(vNoise, 0.0);
  gl_FragColor = vec4(col, alpha);
}
`;

export function MorphBlob({ step, done = false, error = false }: MorphBlobProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Support WebGL dérivé une fois pour toutes (composant monté côté client)
  const [failed] = useState(() => {
    if (typeof document === "undefined") {
      return false;
    }
    try {
      const probe = document.createElement("canvas");
      return !(probe.getContext("webgl2") || probe.getContext("webgl"));
    } catch {
      return true;
    }
  });

  // Dernières props lues par la boucle rAF (jamais pendant le render)
  const stepRef = useRef(step);
  const doneRef = useRef(done);
  const errorRef = useRef(error);
  const staticRenderRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    stepRef.current = step;
    doneRef.current = done;
    errorRef.current = error;
  }, [step, done, error]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    let renderer: THREE.WebGLRenderer;
    try {
      // antialias ne peut être défini qu'à la construction (contrainte WebGL)
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "low-power",
      });
    } catch {
      // Contexte refusé malgré la sonde — rien à afficher, le conteneur reste vide.
      return;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.setAttribute("role", "img");
    renderer.domElement.setAttribute(
      "aria-label",
      "Sphère 3D animée symbolisant l'étape de l'analyse en cours",
    );
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 10);
    camera.position.z = 3.1;

    // Géométrie partagée entre la surface et le maillage (un seul buffer GPU)
    const geometry = new THREE.IcosahedronGeometry(1.05, 32);
    const uniforms = {
      uTime: { value: 0 },
      uAmp: { value: 0.3 },
      uFreq: { value: 2 },
      uSpeed: { value: 0.5 },
      uTwist: { value: 0.6 },
      uMix: { value: 0.7 },
      uColorA: { value: new THREE.Color("#C9A84C") },
      uColorB: { value: new THREE.Color("#00D4FF") },
    };

    const solidMat = new THREE.ShaderMaterial({
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAG_SOLID,
      uniforms,
      transparent: true,
      depthWrite: false,
    });
    const wireMat = new THREE.ShaderMaterial({
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAG_WIRE,
      uniforms,
      transparent: true,
      depthWrite: false,
      wireframe: true,
    });

    const group = new THREE.Group();
    group.add(new THREE.Mesh(geometry, solidMat));
    const wire = new THREE.Mesh(geometry, wireMat);
    wire.scale.setScalar(1.012);
    group.add(wire);
    scene.add(group);

    const setSize = () => {
      const w = container.clientWidth || 280;
      const h = container.clientHeight || 280;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    setSize();
    const resizeObserver = new ResizeObserver(setSize);
    resizeObserver.observe(container);

    // Pause hors écran
    let inView = true;
    const intersectionObserver = new IntersectionObserver(
      ([entry]) => {
        inView = entry.isIntersecting;
      },
      { threshold: 0.05 },
    );
    intersectionObserver.observe(container);

    // Inclinaison douce vers le curseur
    const mouse = { x: 0, y: 0 };
    const onMouseMove = (event: MouseEvent) => {
      mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
      mouse.y = (event.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener("mousemove", onMouseMove, { passive: true });

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const lerp = (u: { value: number }, target: number, dt: number) => {
      u.value += (target - u.value) * Math.min(1, dt * 2.8);
    };

    const applyTargets = (dt: number) => {
      const params = errorRef.current
        ? ERROR_PARAMS
        : doneRef.current
          ? DONE_PARAMS
          : (STEP_PARAMS[Math.min(stepRef.current, STEP_PARAMS.length - 1)] ??
            STEP_PARAMS[0]);
      lerp(uniforms.uAmp, params.amp, dt);
      lerp(uniforms.uFreq, params.freq, dt);
      lerp(uniforms.uSpeed, params.speed, dt);
      lerp(uniforms.uMix, params.mix, dt);
    };

    const clock = new THREE.Clock();
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (!inView || document.hidden) {
        return;
      }
      const dt = Math.min(clock.getDelta(), 0.05);
      uniforms.uTime.value += dt;
      applyTargets(dt);
      group.rotation.y += dt * 0.18;
      group.rotation.x += (mouse.y * 0.28 - group.rotation.x) * 0.04;
      group.rotation.z += (mouse.x * 0.16 - group.rotation.z) * 0.04;
      renderer.render(scene, camera);
    };

    const renderStatic = () => {
      applyTargets(1);
      uniforms.uTime.value = 3;
      renderer.render(scene, camera);
    };

    if (reduced) {
      renderStatic();
    } else {
      raf = requestAnimationFrame(loop);
    }
    staticRenderRef.current = renderStatic;

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      window.removeEventListener("mousemove", onMouseMove);
      staticRenderRef.current = null;
      geometry.dispose();
      solidMat.dispose();
      wireMat.dispose();
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, []);

  // Rendu statique (mouvement réduit) : une image par changement d'étape
  useEffect(() => {
    staticRenderRef.current?.();
  }, [step, done, error]);

  if (failed) {
    /* Repli CSS si WebGL indisponible */
    return (
      <div
        aria-hidden
        className="relative flex size-56 items-center justify-center"
      >
        <div className="absolute inset-0 animate-pulse rounded-full bg-[radial-gradient(circle,rgba(201,168,76,0.25),transparent_65%)]" />
        <div className="size-36 rounded-full border border-quanta-gold/40" />
      </div>
    );
  }

  return <div ref={containerRef} className="size-full" />;
}
