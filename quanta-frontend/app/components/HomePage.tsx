"use client";

import { useCallback, useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  animate,
  motion,
  useInView,
  useReducedMotion,
  useScroll,
  useTransform,
} from "framer-motion";
import { ArrowRight, FileWarning, Loader2, ShieldCheck } from "lucide-react";

import { AnalysisProgress } from "@/app/components/AnalysisProgress";
import { AnalysisResults } from "@/app/components/AnalysisResults";
import { UploadZone } from "@/app/components/UploadZone";
import { AuthButton } from "@/app/components/AuthButton";
import { LogoQ } from "@/app/components/LogoQ";
import { SiteHeader } from "@/app/components/SiteHeader";
import { SiteFooter } from "@/app/components/SiteFooter";
import { SplashScreen } from "@/app/components/SplashScreen";
import { Reveal } from "@/app/components/Reveal";
import { useAuth } from "@/app/context/AuthContext";

const QUERY_EXAMPLES = [
  "Comparer le revenu entre régions",
  "Analyser l'association genre × diplôme",
  "Prédire le salaire par l'expérience",
] as const;

const TRUST_METHOD_COUNT = 37;

const TRUST_ITEMS = [
  "Score de confiance calibré",
  "Rapport PDF signable",
] as const;

type Phase = "idle" | "uploading" | "analyzing" | "done" | "error";

interface UploadResponse {
  file_id: string;
}

interface AnalyzeResponse {
  analysis_id: string;
}


function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  }
  return baseUrl.replace(/\/$/, "");
}

async function parseErrorResponse(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") {
      return data.detail;
    }
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((entry) => {
          if (typeof entry === "object" && entry !== null && "msg" in entry) {
            return String((entry as { msg: unknown }).msg);
          }
          return String(entry);
        })
        .join(" ");
    }
  } catch {
    // ignore JSON parse errors
  }
  return `Erreur HTTP ${response.status}`;
}

/**
 * « 37 méthodes statistiques » — le compteur s'incrémente à l'entrée
 * dans le viewport (une seule fois). Au premier chargement de session,
 * il attend la fin du splash pour que l'incrément soit visible.
 */
function TrustStat() {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-24px" });
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!inView) {
      return;
    }
    let delay = 0.15;
    try {
      if (sessionStorage.getItem("quanta-splash-shown") !== "1") {
        delay = 4.2;
      }
    } catch {
      // sessionStorage indisponible : comptage immédiat.
    }
    const controls = animate(0, TRUST_METHOD_COUNT, {
      duration: 1.8,
      ease: [0.16, 1, 0.3, 1],
      delay,
      onUpdate: (v) => setValue(Math.round(v)),
    });
    return () => controls.stop();
  }, [inView]);

  return (
    <span ref={ref} className="tabular-nums text-quanta-gold">
      {value}
    </span>
  );
}

function HomePageContent() {
  const searchParams = useSearchParams();
  const { isAuthenticated, isLoading } = useAuth();
  const { scrollY } = useScroll();
  const reduceMotion = useReducedMotion();
  /* Parallaxe : le fond glisse plus lentement que le contenu. */
  const atmosphereY = useTransform(scrollY, [0, 1400], [0, 240]);
  const atmosphereOpacity = useTransform(scrollY, [0, 1000], [1, 0.45]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [result, setResult] = useState<unknown | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Au montage, vérifier si analysisId est présent dans l'URL
  useEffect(() => {
    const analysisIdParam = searchParams.get("analysisId");
    if (analysisIdParam) {
      setAnalysisId(analysisIdParam);
      setPhase("analyzing");
    }
  }, [searchParams]);

  const canAnalyze = selectedFile !== null;
  const isUploading = phase === "uploading";

  const resetAll = useCallback(() => {
    setPhase("idle");
    setAnalysisId(null);
    setResult(null);
    setErrorMessage(null);
    setSelectedFile(null);
    setQuery("");
  }, []);

  const retry = useCallback(() => {
    setPhase("idle");
    setAnalysisId(null);
    setResult(null);
    setErrorMessage(null);
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!selectedFile) {
      return;
    }

    try {
      setPhase("uploading");
      setErrorMessage(null);
      setResult(null);
      setAnalysisId(null);

      const baseUrl = getApiBaseUrl();

      const formData = new FormData();
      formData.append("file", selectedFile);

      const uploadResponse = await fetch(`${baseUrl}/upload`, {
        method: "POST",
        body: formData,
        credentials: "include",
      });

      if (uploadResponse.status === 401) {
        throw new Error("Connectez-vous pour continuer.");
      }
      if (!uploadResponse.ok) {
        throw new Error(await parseErrorResponse(uploadResponse));
      }

      const uploadData = (await uploadResponse.json()) as UploadResponse;
      const fileId = uploadData.file_id;

      const analyzeResponse = await fetch(`${baseUrl}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_id: fileId, query: query.trim() }),
        credentials: "include",
      });

      if (analyzeResponse.status === 401) {
        throw new Error("Connectez-vous pour continuer.");
      }
      if (analyzeResponse.status === 403) {
        // Quota dépassé
        const errorData = await analyzeResponse.json().catch(() => ({}));
        const renewalDate = errorData.detail?.match(/le (.+)$/)?.[1] || "prochainement";
        throw new Error(`Quota mensuel atteint. Renouvellement le ${renewalDate}.`);
      }
      if (!analyzeResponse.ok) {
        throw new Error(await parseErrorResponse(analyzeResponse));
      }

      const analyzeData = (await analyzeResponse.json()) as AnalyzeResponse;
      setAnalysisId(analyzeData.analysis_id);
      setPhase("analyzing");
      
      // Rafraîchir le quota après analyse réussie (via window.refreshQuota exposé par AuthButton)
      if (typeof window !== "undefined" && (window as { refreshQuota?: () => void }).refreshQuota) {
        void (window as { refreshQuota?: () => void }).refreshQuota?.();
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Une erreur est survenue pendant l'analyse.";
      setErrorMessage(message);
      setPhase("error");
    }
  }, [query, selectedFile]);

  const handleLoadSample = useCallback(async () => {
    try {
      setErrorMessage(null);
      const response = await fetch("/sample_data.csv");
      if (!response.ok) {
        throw new Error("Impossible de charger le fichier d'exemple.");
      }
      const blob = await response.blob();
      const file = new File([blob], "sample_data.csv", {
        type: "text/csv",
      });
      setSelectedFile(file);
      setQuery("Analyser automatiquement ce dataset");
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Impossible de charger le fichier d'exemple.";
      setErrorMessage(message);
      setPhase("error");
    }
  }, []);

  return (
    <div className="relative flex min-h-screen flex-col">
      <SplashScreen />
      <SiteHeader />

      {/* Atmosphère : points + halo or, hors flux (la pluie de symboles
          est un calque fixe global rendu par le layout). Parallaxe : le
          fond défile plus lentement que le contenu. */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden"
        style={
          reduceMotion
            ? undefined
            : { y: atmosphereY, opacity: atmosphereOpacity }
        }
      >
        <div className="bg-dots mask-fade-edges absolute inset-0" />
        <div className="bg-glow-gold absolute inset-0" />
      </motion.div>

      <main className="relative z-10 flex flex-1 flex-col items-center px-6 pb-20 pt-36">
        {/* ── Hero ─────────────────────────────────────────── */}
        <section className="flex flex-col items-center text-center">
          <p className="hud-label reveal text-quanta-muted">
            Moteur d&apos;analyse statistique
          </p>

          <motion.div
            initial={{ opacity: 0, scale: 0.82, rotate: -14 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            transition={{
              duration: 0.9,
              ease: [0.16, 1, 0.3, 1],
              delay: 2.8,
            }}
            className="mt-8"
          >
            <LogoQ size={64} animated durationMs={1000} delayMs={2800} />
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, letterSpacing: "0.5em" }}
            animate={{ opacity: 1, letterSpacing: "0.14em" }}
            transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 3.05 }}
            className="mt-6 bg-gradient-to-b from-quanta-gold-2 via-quanta-gold to-quanta-gold bg-clip-text pl-[0.14em] font-brand text-6xl font-extralight text-transparent sm:text-7xl lg:text-8xl"
          >
            QUANTA
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1], delay: 3.45 }}
            className="mt-6 max-w-md font-serif text-xl italic leading-relaxed text-quanta-secondary"
          >
            Tu déposes ta base. Tu reçois un rapport que tu peux signer.
          </motion.p>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 3.75 }}
            className="mt-10 flex flex-wrap items-center justify-center gap-x-5 gap-y-2"
          >
            <span className="flex items-baseline gap-1.5 font-sans text-[11px] uppercase tracking-[0.14em] text-quanta-muted">
              <TrustStat />
              <span>méthodes statistiques</span>
            </span>
            {TRUST_ITEMS.map((item) => (
              <span key={item} className="flex items-center gap-5">
                <span aria-hidden className="h-3 w-px bg-quanta-border-subtle" />
                <span className="font-sans text-[11px] uppercase tracking-[0.14em] text-quanta-muted">
                  {item}
                </span>
              </span>
            ))}
          </motion.div>
        </section>

        {/* ── Panneau principal ───────────────────────────── */}
        <section className="reveal reveal-2 mt-16 w-full max-w-xl space-y-6">
          {isLoading ? (
            <div className="flex min-h-[300px] items-center justify-center">
              <Loader2
                strokeWidth={1.5}
                className="size-6 animate-spin text-quanta-gold"
                aria-hidden
              />
            </div>
          ) : !isAuthenticated ? (
            /* Connexion requise */
            <Reveal>
            <div className="glass flex flex-col items-center gap-6 rounded-hero px-8 py-12 text-center">
              <div className="flex size-12 items-center justify-center rounded-full border border-quanta-border-active">
                <ShieldCheck
                  strokeWidth={1.5}
                  className="size-5 text-quanta-gold"
                  aria-hidden
                />
              </div>
              <div className="space-y-2">
                <p className="font-display text-xl font-light text-quanta-primary">
                  Session requise
                </p>
                <p className="mx-auto max-w-xs font-sans text-sm leading-relaxed text-quanta-secondary">
                  Une connexion Google est nécessaire pour déposer vos données
                  et suivre vos analyses.
                </p>
              </div>
              <AuthButton />
            </div>
            </Reveal>
          ) : (
            <>
              {phase === "analyzing" && analysisId ? (
                <Reveal>
                <AnalysisProgress
                  analysisId={analysisId}
                  onComplete={(res) => {
                    setResult(res);
                    setPhase("done");
                  }}
                  onError={(msg) => {
                    setErrorMessage(msg);
                    setPhase("error");
                  }}
                  onCancel={() => {
                    setPhase("idle");
                    setAnalysisId(null);
                  }}
                />
                </Reveal>
              ) : null}

              {phase === "done" && result !== null && analysisId ? (
                <Reveal>
                <AnalysisResults
                  result={result}
                  analysisId={analysisId}
                  onNewAnalysis={resetAll}
                />
                </Reveal>
              ) : null}

              {phase === "error" ? (
                <Reveal>
                <div className="glass flex flex-col items-center gap-5 rounded-hero px-8 py-10 text-center">
                  <FileWarning
                    strokeWidth={1.5}
                    className="size-8 text-quanta-warning"
                    aria-hidden
                  />
                  <p className="max-w-sm font-sans text-sm leading-relaxed text-quanta-primary">
                    {errorMessage ?? "Une erreur est survenue."}
                  </p>
                  <button
                    type="button"
                    onClick={retry}
                    aria-label="Réessayer l'analyse"
                    className="cursor-pointer rounded-quanta border border-quanta-border-subtle px-6 py-2.5 font-sans text-sm text-quanta-primary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan"
                  >
                    Réessayer
                  </button>
                </div>
                </Reveal>
              ) : null}

              {phase === "idle" || phase === "uploading" ? (
                <>
                  {/* 01 — Données */}
                  <Reveal delay={2.85}>
                  <div className="space-y-3">
                    <p className="hud-label pl-1 text-quanta-muted">
                      01 · Votre base de données
                    </p>
                    <UploadZone
                      selectedFile={selectedFile}
                      onFileSelect={setSelectedFile}
                    />
                    <div className="text-right">
                      <button
                        type="button"
                        onClick={() => {
                          void handleLoadSample();
                        }}
                        aria-label="Charger un fichier d'exemple"
                        className="cursor-pointer font-sans text-xs text-quanta-muted transition-quanta hover:text-quanta-cyan"
                      >
                        Pas de fichier ? Tester avec un exemple →
                      </button>
                    </div>
                  </div>
                  </Reveal>

                  {/* 02 — Intention */}
                  <Reveal delay={2.95}>
                  <div className="space-y-3">
                    <label
                      htmlFor="query-input"
                      className="hud-label block pl-1 text-quanta-muted"
                    >
                      02 · Requête — optionnel
                    </label>
                    <textarea
                      id="query-input"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      rows={3}
                      placeholder={
                        "Ex : comparer le revenu entre régions…\n" +
                        "Si vide, QUANTA choisit l'analyse automatiquement."
                      }
                      className="w-full resize-none rounded-quanta border border-quanta-border-subtle bg-quanta-elevated px-4 py-3 font-sans text-sm leading-relaxed text-quanta-primary transition-quanta placeholder:text-quanta-muted focus:border-quanta-cyan focus:shadow-[0_0_0_3px_rgba(0,212,255,0.08)] focus:outline-none"
                    />
                    <div className="flex flex-wrap gap-2 pt-1">
                      {QUERY_EXAMPLES.map((example) => (
                        <button
                          key={example}
                          type="button"
                          onClick={() => setQuery(example)}
                          aria-label={`Utiliser l'exemple : ${example}`}
                          className="cursor-pointer rounded-quanta border border-quanta-border-subtle px-3 py-1.5 font-sans text-xs text-quanta-secondary transition-quanta hover:border-quanta-cyan hover:text-quanta-cyan"
                        >
                          {example}
                        </button>
                      ))}
                    </div>
                  </div>
                  </Reveal>

                  {/* 03 — Exécution */}
                  <Reveal delay={3.05}>
                  <div className="flex justify-center pt-2">
                    <button
                      type="button"
                      disabled={!canAnalyze || isUploading}
                      onClick={() => {
                        void handleAnalyze();
                      }}
                      aria-label={
                        isUploading ? "Envoi en cours" : "Analyser le fichier"
                      }
                      className="group btn-sheen inline-flex cursor-pointer items-center justify-center gap-2.5 rounded-quanta bg-quanta-gold px-10 py-3.5 font-sans text-sm font-medium tracking-[0.04em] text-quanta-void shadow-[0_0_0_rgba(201,168,76,0)] transition-all duration-300 hover:bg-quanta-gold-2 hover:shadow-[0_0_36px_rgba(201,168,76,0.22)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:shadow-none"
                    >
                      {isUploading ? (
                        <>
                          <Loader2
                            strokeWidth={1.5}
                            className="size-4 animate-spin"
                            aria-hidden
                          />
                          Envoi en cours…
                        </>
                      ) : (
                        <>
                          Lancer l&apos;analyse
                          <ArrowRight
                            strokeWidth={1.5}
                            className="size-4 transition-transform duration-200 group-hover:translate-x-0.5"
                            aria-hidden
                          />
                        </>
                      )}
                    </button>
                  </div>
                  </Reveal>
                </>
              ) : null}
            </>
          )}
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

export function HomePage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center">
          <div className="flex items-center gap-2">
            <Loader2
              strokeWidth={1.5}
              className="size-6 animate-spin text-quanta-gold"
              aria-hidden
            />
            <span className="font-sans text-sm text-quanta-muted">
              Chargement...
            </span>
          </div>
        </main>
      }
    >
      <HomePageContent />
    </Suspense>
  );
}
