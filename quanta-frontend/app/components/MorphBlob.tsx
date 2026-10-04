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
 * chaque étape donne au maillage une personnalité distincte.
 * Registre « goutte liquide » : basses fréquences (grosses houles lentes),
 * amplitudes contenues — la silhouette reste un cercle presque parfait
 * qui ondule, jamais un tissu froissé.
 */
const STEP_PARAMS: Array<{
  amp: number;
  freq: number;
  speed: number;
  mix: number;
}> = [
  { amp: 0.07, freq: 1.2, speed: 0.25, mix: 0.7 }, // Réception
  { amp: 0.1, freq: 1.4, speed: 0.35, mix: 0.7 }, // Diagnostic
  { amp: 0.09, freq: 1.8, speed: 0.45, mix: 0.75 }, // Nettoyage
  { amp: 0.12, freq: 1.1, speed: 0.3, mix: 0.6 }, // Sélection des tests
  { amp: 0.16, freq: 1.6, speed: 0.55, mix: 0.85 }, // Calculs
  { amp: 0.09, freq: 2.0, speed: 0.45, mix: 0.8 }, // Vérification
  { amp: 0.13, freq: 1.3, speed: 0.4, mix: 0.55 }, // Interprétation
  { amp: 0.04, freq: 1.0, speed: 0.15, mix: 0.15 }, // Finalisation
];

const DONE_PARAMS = { amp: 0.02, freq: 1.0, speed: 0.1, mix: 0.12 };
const ERROR_PARAMS = { amp: 0.18, freq: 2.4, speed: 0.9, mix: 0.0 };

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
  /* Deux octaves : grosses houles liquides + shimmer discret.
     Somme normalisée par son amplitude max (1 + 0.15) → n ∈ [-1, 1] garanti,
     donc le rayon reste borné et la caméra peut cadrer sans jamais rogner. */
  float n = snoise(dir * uFreq + t * 0.7);
  n += 0.15 * snoise(dir * uFreq * 2.2 - t * 1.3);
  n /= 1.15;
  vNoise = n;
  vec3 pos = position;
  float angle = position.y * uTwist + t * 0.15;
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
uniform float uMix2;
varying float vNoise;
varying vec3 vNormalV;
varying vec3 vViewDir;
void main() {
  float fres = pow(1.0 - abs(dot(normalize(vNormalV), normalize(vViewDir))), 2.0);
  /* uMix2 = valeur LISSÉE en CPU (voir mixSmooth) : la couleur glisse
     en douceur d'une étape à l'autre, jamais de saut. */
  float k = clamp(uMix2 * (vNoise * 0.5 + 0.5), 0.0, 1.0);
  vec3 base = mix(uColorA, uColorB, k);
  vec3 col = base * (0.20 + 0.9 * fres) + vec3(1.0, 0.95, 0.82) * fres * 0.30;
  /* Corps un peu plus plein : goutte liquide plutôt que voile */
  float alpha = 0.18 + 0.74 * fres;
  gl_FragColor = vec4(col, alpha);
}
`;

/* Maillage polygonal discret par-dessus la surface — très discret :
   il structure la matière sans jamais évoquer un tissu. */
const FRAG_WIRE = `
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform float uMix2;
varying float vNoise;
varying vec3 vNormalV;
varying vec3 vViewDir;
void main() {
  vec3 col = mix(uColorA, uColorB, clamp(uMix2 * (vNoise * 0.5 + 0.5), 0.0, 1.0));
  float alpha = 0.02 + 0.06 * max(vNoise, 0.0);
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
    // FOV serré (38°) : perspective douce, la sphère lit « ronde » sans distorsion
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 10);
    camera.position.z = 4.1;

    // Détail 24 : lignes du maillage plus douces (effet liquide, pas tissue)
    const geometry = new THREE.IcosahedronGeometry(1.05, 24);
    const uniforms = {
      uTime: { value: 0 },
      uAmp: { value: 0.3 },
      uFreq: { value: 2 },
      uSpeed: { value: 0.5 },
      uTwist: { value: 0.25 },
      uMix: { value: 0.7 },
      uMix2: { value: 0.7 },
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

    /* Cadrage garanti : la caméra recule juste assez pour que même le pic
       de déformation maximal (+ fil de fer) reste ENTIER dans le cadre,
       quelle que soit la proportion du conteneur. Jamais de coupe carrée. */
    const noiseCeiling = 1.0; // n ∈ [-1, 1] après normalisation dans le shader
    const maxAmp = Math.max(
      ...STEP_PARAMS.map((p) => p.amp),
      DONE_PARAMS.amp,
      ERROR_PARAMS.amp,
    );
    const maxRadius = (1.05 + noiseCeiling * maxAmp) * 1.012; // × échelle du fil

    const setSize = () => {
      const w = container.clientWidth || 280;
      const h = container.clientHeight || 280;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      const halfV = Math.tan((camera.fov * Math.PI) / 360);
      const fitVertical = maxRadius / halfV;
      const fitHorizontal = maxRadius / (halfV * camera.aspect);
      camera.position.z = Math.max(fitVertical, fitHorizontal) + 0.22;
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

    /* Lissage exponentiel indépendant par uniforme : chaque étape impose
       sa CIBLE (vitesse/vigueur), mais la valeur suit un glide — la
       transition entre deux étapes est une métamorphose continue, pas
       un saut de paramètres. facteur dt*rate borné pour rester stable
       même à fps instable. */
    const lerp = (u: { value: number }, target: number, dt: number, rate = 1.6) => {
      const k = 1 - Math.exp(-rate * Math.min(dt, 0.1));
      u.value += (target - u.value) * k;
    };

    const applyTargets = (dt: number) => {
      const params = errorRef.current
        ? ERROR_PARAMS
        : doneRef.current
          ? DONE_PARAMS
          : (STEP_PARAMS[Math.min(stepRef.current, STEP_PARAMS.length - 1)] ??
            STEP_PARAMS[0]);
      /* Décalage des vitesses de glide (stagger) : l'amplitude et la
         fréquence évoluent légèrement différemment — la surface se
         déforme de façon organique au lieu d'interpoler en bloc. */
      lerp(uniforms.uAmp, params.amp, dt, 1.4);
      lerp(uniforms.uFreq, params.freq, dt, 1.1);
      lerp(uniforms.uSpeed, params.speed, dt, 1.8);
      lerp(uniforms.uMix2, params.mix, dt, 1.3);
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
      // Respiration infinitésimale : vie « liquide » sans casser le cercle
      group.scale.setScalar(1 + Math.sin(uniforms.uTime.value * 0.5) * 0.008);
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
