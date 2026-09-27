# QUANTA — État Actuel du Système
*Dernière mise à jour : 26 septembre 2026 (réécriture après audit complet du code)*

Document de référence pour les sessions de développement. Décrit **ce qui existe et fonctionne aujourd'hui**, pas la vision produit ni les specs futures. Les limitations sont assumées. Toute valeur citée ici a été vérifiée dans le code source à la date de mise à jour.

---

## 1. Vue d'ensemble

- **Ce qu'est QUANTA** : un moteur d'analyse statistique doctoral-level qui transforme un fichier de données + une requête (optionnelle) en résultats chiffrés déterministes, interprétation textuelle structurée, et rapport PDF signable.
- **Promesse centrale** : « Tu déposes ta base. Tu reçois un rapport que tu peux signer. » — séparation stricte **COMPUTE** (calcule) → **BRAIN** (interprète seulement) → **REPORT** (met en page).
- **Authentification** : OAuth Google obligatoire (Authlib 1.8.0) + sessions en base + **quota mensuel de 15 analyses par utilisateur** (remboursé si l'analyse finit en erreur).
- **Stack technique (versions exactes vérifiées dans requirements.txt, sept. 2026)** :

| Couche | Technologie | Version |
|--------|-------------|---------|
| Runtime | Python | 3.12 (Dockerfile `python:3.12-slim` ; runtime.txt `python-3.12.0`) |
| API | FastAPI | 0.137.0 |
| Serveur | uvicorn | 0.49.0 |
| Validation | pydantic | 2.13.4 |
| Data | pandas | ≥1.4.1, <3.0.0 (donc 2.x) |
| Numérique | numpy | 2.4.6 |
| Stats | scipy | 1.17.1 |
| Stats modèles | statsmodels | 0.14.6 |
| ANOVA Welch | pingouin | 0.6.1 |
| Post-hoc | scikit-posthocs | 0.14.0 |
| ACP / ACM | prince | 0.13.1 |
| Graphiques | matplotlib / seaborn | 3.11.0 / 0.13.2 |
| Excel | openpyxl | 3.1.5 |
| SPSS | pyreadstat | 1.3.5 |
| PDF | WeasyPrint | 69.0 (+ fpdf2, pypdf) |
| OAuth | Authlib | 1.8.0 |
| Rate limiting | slowapi | 0.1.9 |
| Logging | structlog | 24.1.0 |
| Scheduler | APScheduler | 3.10.4 |
| HTTP LLM | requests | 2.32.4 |
| Frontend | Next.js | 16.2.9 |
| UI | React | 19.2.4 |
| CSS | Tailwind CSS | 4.x |
| Motion | framer-motion | ^12.42.0 |
| Persistance | SQLite (stdlib) | fichier `quanta.db` (WAL) |

---

## 2. Architecture des fichiers

Chemins relatifs à la racine du dépôt. Lignes ≈ comptage physique (indicatif).

### Racine
- `main.py` — API FastAPI : auth protégée, upload (filename sanitizé + whitelist extension), analyze async, status, history, quota, cancel, report PDF (`?theme=dark|light`), audit_trail horodaté, cleanup APScheduler (fichiers + analyses + sessions > 24h) — dépend de `db`, `app.compute`, `app.orchestrator`, `app.llm.brain`, `app.report_generator`, `app.analysis_core`
- `db.py` — persistance SQLite (users, sessions, uploads, analyses) — stdlib `sqlite3` uniquement, WAL, lock global, migrations au démarrage, fonctions `_internal` réservées aux workers de confiance
- `requirements.txt` — pin des dépendances Python
- `.env.example` — modèle de configuration LLM + OAuth
- `QUANTA_STATE.md` — ce document
- `DESIGN_BRIEF.md` — contrat visuel frontend (pas le moteur stats)
- `NOTES.md` — notes historiques (encodage cassé, non normatif)
- `QUANTA_STATISTICAL_COVERAGE_MATRIX.md` — audit de couverture statistique (37 méthodes, 28 validées)
- `legacy/` — code historique **lecture seule** (référence, ne pas modifier)

### `app/`
- `app/orchestrator.py` — pipeline bout-en-bout : compute → test_selector → délégation → puissance statsmodels → score de confiance ; `auto_intent` (mode autonome) ; `run_full_analysis(..., base_pipeline=)` accepte un pipeline pré-calculé réutilisé entre intents
- `app/analysis_core.py` — **logique d'analyse partagée** entre le worker subprocess et le fallback in-memory (annulation vérifiée avant chaque intent, audit trail unique) ; `CancelledAnalysis` levée si annulé
- `app/analyze_worker.py` — subprocess d'analyse (délègue à analysis_core) ; erreurs persistées via `db.update_analysis_internal`
- `app/pdf_worker.py` — subprocess génération PDF (WeasyPrint isolé en mémoire)
- `app/auth.py` — OAuth Google : `/auth/google`, `/auth/callback` (rate limité 20/min), `/auth/logout`, `/auth/me` ; cookie httpOnly+secure+SameSite=None, 7 jours
- `app/report_generator.py` — HTML → PDF WeasyPrint (thèmes dark/light) — lit le résultat assemblé, ne recalcule rien ; génération chunked (sections → PDFs fusionnés via pypdf)
- `app/compute/compute.py` — chargement, diagnostic, nettoyage, descriptives, normalité, corrélation, OLS, charts, scripts R/Stata, **`compute_statistical_power`**, ACP, ACM
- `app/compute/test_selector.py` — arbre de décision + tests d'inférence + post-hoc (Tukey / Dunn / Games-Howell) + **IC bootstrap vectorisés** (Cohen's d, r bisériel, η², ε², V de Cramér — RNG local, plus d'effet de bord `np.random.seed` global)
- `app/compute/upload_validation.py` — chargement léger (pandas seul) pour /upload : encodages, séparateurs, IDs, texte libre, décimales FR
- `app/llm/brain.py` — `text_to_intent`, `generate_interpretation`, anti-hallucination, Skeptic Engine, `analyze_with_brain` ; **mode autonome : pipeline de base calculé 1× pour N intents**

### Frontend `quanta-frontend/`
- `app/page.tsx` — point d'entrée Next (délègue à `HomePage`)
- `app/components/HomePage.tsx` — orchestration UI upload → analyse → résultats
- `app/components/UploadZone.tsx` — drag & drop fichier
- `app/components/AnalysisProgress.tsx` — polling `/status` (timeout 5 min)
- `app/components/AnalysisResults.tsx` — résultats + **deux téléchargements PDF** (Dark / Académique)
- `app/components/ConfidenceScore.tsx` — score de confiance
- `app/components/AuthButton.tsx` — connexion/déconnexion Google
- `app/history/` — historique des analyses (UI)
- `public/sample_data.csv` — dataset d'exemple (50 lignes)

### Tests `tests/`
- ~95 scripts autonomes (pas de pytest conventionnel pour la plupart) ; quelques-luns executables via pytest (`test_cache`, `test_cancel_analysis`, `test_quota`, ...)
- `scripts/` — générateurs de datasets de test + 3 scripts de performance (bootstrap CI, endpoints, intents)

---

## 3. Les Organes actifs

### Organe 01 — Intake Engine (`app/compute/upload_validation.py` → `load_and_diagnose`)

- **Formats acceptés** : CSV, Excel (`.xls`/`.xlsx`), Stata (`.dta`), SPSS (`.sav` via pyreadstat) — whitelist stricte dans `/upload`
- **Limites API** (dans `main.py`) : **25 Mo**, **100 000 lignes**
- **Encodages gérés** : cascade `utf-8` → `utf-8-sig` → `cp1252` → `latin-1` (filet de sécurité)
- **Séparateurs détectés** : virgule, point-virgule, tabulation, pipe (par cohérence du nombre de colonnes)
- **Virgule décimale française** : oui — `_try_convert_french_decimal()` si ≥ 90 % des valeurs convertibles
- **Détection de colonnes** : numériques vs catégorielles (garde-fou cardinalité < 10 sur n ≥ 10 ET n ≥ 2×n_unique), IDs exclus (hints forts/ambigus + unicité), texte libre isolé (ratio d'unicité > 50 %), dates, type de dataset heuristique
- **Sanitisation** : `/upload` neutralise le nom de fichier (basename, caractères, longueur 255) avant écriture — protection path traversal

### Organe 02 — Cleaning Core (`clean_dataframe`)

**Statut : PARTIEL (~70 %)**

- Copie défensive, détection + log des doublons **sans suppression**, imputation médiane (<5 %)/moyenne (5-20 %)/suppression colonne (>20 %), mode pour catégorielles (<20 %), winsorisation 1-99 % seulement si n ≥ 30, `audit_log` structuré
- Pas encore : validation utilisateur avant transformation, imputation avancée (MICE/KNN), suppression doublons sous contrôle, UI de revue, export dataset nettoyé

### Organe 03 — Statistical Brain (`test_selector.py` + `orchestrator.py`)

**Tests implémentés (avec conditions)** : t-Student / t-Welch / Mann-Whitney (2 groupes), t pairé / Wilcoxon (appariés), ANOVA + Tukey / Welch ANOVA + Games-Howell / Kruskal-Wallis + Dunn (k groupes), Chi-deux / Fisher exact (association), Pearson / Spearman (corrélation, déléguée compute), OLS (délégué), logistique binaire, ACM (prince, ≥3 catégorielles), ACP (prince, ≥3 numériques avec variance), `descriptive_only` en repli.

- **Tailles d'effet + IC bootstrap 95 % vectorisés** : Cohen's d, r rang bisériel, η², ε², V de Cramér (1000 réplications, seed reproductible, RNG local)
- **Post-hoc** : format unifié `posthoc: {method, comparisons[...]}` ou `null` si p ≥ 0.05
- **Puissance statistique** : TTestIndPower / FTestAnovaPower / GofChisquarePower ; champs `power`, `power_interpretation`, `n_required`
- **Garde-fous** : max 30 groupes et min 5 obs/groupe pour multi-groupes ; chi-deux avec avertissement si effectifs attendus < 5 ; repli Games-Howell→Tukey documenté
- **Score de confiance** : qualite_donnees 20 %, respect_conditions 25 %, coherence 20 %, taille 15 %, stabilite 20 % ; plafonné à 95 ; n<30 → niveau max « Faible », n<100 → « Modéré »
- **Mode autonome** (`auto_intent`) : compare_groups (≤3 targets) + corrélation + association + ACM (≥3 cat) + descriptif ; **le pipeline de base (chargement/nettoyage/normalité/corrélations/charts) est calculé UNE fois et réutilisé pour tous les intents** (optimisation sept. 2026 : évite jusqu'à ~6× recalcul)

### Organe 04 — Interpretation Layer (`app/llm/brain.py`)

- **Provider principal** : Groq, `PRIMARY_MODEL` (défaut `llama-3.3-70b-versatile`)
- **Fallback** : OpenRouter, `FALLBACK_MODEL` (défaut `meta-llama/llama-3.1-8b-instruct:free`)
- Timeout 25 s, 2 retries/provider, backoff 3 s ; **jamais d'exception** si LLM down → `llm_available: false` + résultats bruts
- **Anti-hallucination** : nombres du texte généré comparés aux sources (±1 % / ±0.01), détection zéros de tête (`025,02`)
- **Skeptic Engine** : alertes sur incohérence conclusions/p-values ; ne bloque jamais
- **Règle d'or** : le LLM ne calcule jamais ; il cite / reformule

### Organe 05 — Report Forge (`app/report_generator.py`)

- WeasyPrint 69.0, thèmes dark/light ; génération **chunked** (sections rendues séparément, fusionnées avec pypdf) avec repli PDF léger (fpdf2) en cas d'échec/timeout
- Sections : page de garde (SHA256, versions moteur), présentation des données, descriptives APA, analyse (H₀/H₁, APA, post-hoc, puissance, IC bootstrap, ACM/ACP), interprétation (+ Skeptic), limites, résumé, Défense Scientifique, annexes A (R/Stata), C (bibliographie), D (Colab), E (audit journal)
- Graphiques limités dans les sections volumineuses ; les PDFs régénérés à la demande (ancien PDF supprimé avant régénération)

### Organe 06 — API & Persistance (`main.py` + `db.py`)

**Endpoints (~10 + 4 auth) :**

| Méthode | Route | Rôle |
|---------|-------|------|
| GET | `/health` | santé service |
| POST | `/upload` | fichier → diagnostic léger + `file_id` (auth) |
| POST | `/analyze` | analyse async → `analysis_id` (auth, quota, cache, rate limit 5/min) |
| GET | `/status/{analysis_id}` | polling pending/running/done/error/cancelled |
| GET | `/history` | dernières analyses (auth) |
| GET | `/quota` | quota mensuel restant (auth) |
| POST | `/analyses/{id}/cancel` | annulation (worker vérifie avant chaque intent) |
| GET | `/report/{id}?theme=dark\|light` | PDF binaire (done uniquement) |
| GET | `/auth/google`, `/auth/callback` | flow OAuth (callback rate limité 20/min) |
| POST | `/auth/logout`, GET `/auth/me` | session |

- **Persistance** : SQLite `quanta.db` (`QUANTA_DB_PATH`, défaut `/data/quanta.db`) — tables `users`, `sessions`, `uploads`, `analyses` ; fichiers physiques dans `/data/uploads` (`QUANTA_UPLOAD_DIR`)
- **Migrations** : au démarrage (users : colonnes quota ; analyses : file_hash) — transaction explicite pour la recréation de `users`
- **Cache** : `find_cached_analysis` par (user, file_hash, query) — hit = résultat dupliqué sans consommer de quota
- **Quota** : 15 analyses/30 jours glissants, incrément atomique, **remboursé automatiquement si le statut final est `error`** (point unique dans `_run_analysis_background.finally`)
- **Annulation** : `/cancel` écrit `cancelled` ; vérifié avant chaque intent dans analysis_core (worker ET fallback)
- **Cleanup APScheduler** (toutes les 6 h) : fichiers > 24 h, analyses > 24 h (`list_analyses_internal`/`delete_analysis_internal`), sessions expirées
- **Rate limiting** : upload 10/min, analyze 5/min (par user_id si session, sinon IP), auth 20/min
- **CORS** : `ALLOWED_ORIGINS` (défaut `http://localhost:3000`) ; pas de headers CORS manuels dans /report (incompatibles avec allow_credentials)

---

## 4. Interface Frontend (`quanta-frontend/`)

- Next.js 16.2.9 (App Router) + React 19.2.4 + Tailwind 4
- Composants : `HomePage`, `UploadZone`, `AnalysisProgress` (poll 5 min), `AnalysisResults` (dual PDF), `ConfidenceScore`, `AuthButton`
- Pages : accueil, `history` (historique), `preview`
- Design system (globals.css) : void `#0A0A0F`, surface `#13131A`, elevated `#1C1C26`, or `#C9A84C`, cyan `#00D4FF` ; Space Grotesk / Geist / JetBrains Mono
- **Prérequis** : `NEXT_PUBLIC_API_URL` (ex. `http://127.0.0.1:8000`)
- Déploiement : Vercel (`vercel.json`) ; attention `.env.production` historique en UTF-16 (à remplacer par UTF-8)

---

## 5. Tests

- Scripts autonomes sous `python -m tests.<nom>` depuis la racine ; ex. : `test_selector_2groups_normal`, `test_selector_2groups_nonnormal`, `test_selector_multigroup`, `test_selector_association`, `test_selector_paired`, `test_cramers_v_ci`, `test_compute_statistical_power`, `test_orchestrator_*`, `test_brain_*` (live/no-key), `test_cache`, `test_cancel_analysis`, `test_quota`, `test_auth_isolation`, `test_french_excel_export`
- `test_quota` : 2 échecs connus (rate limit slowapi 429 avant le 15e appel) — à exécuter avec limites désactivées ou contournés dans la CI
- `test_orchestrator_compare_groups` : échec connu (attend Student/Welch sur un dataset qui produit Mann-Whitney — décalage dataset/test préexistant)
- `tests/RESULTS.md` : validations manuelles chronologiques
- `QUANTA_STATISTICAL_COVERAGE_MATRIX.md` : 37 méthodes implémentées, 28 validées, 7 partielles, 10 absentes (clustering, séries temporelles, survie, bootstrap/permutation génériques)

---

## 6. Ce qui fonctionne de bout en bout

- Upload multi-format avec diagnostic + filename sanitizé + whitelist extension
- Auth Google + sessions persistées + quota mensuel atomique avec remboursement sur erreur
- Analyse async (worker subprocess, fallback in-memory) avec annulation effective sur les deux chemins
- Mode autonome sans query avec **pipeline de base réutilisé entre intents**
- Post-hoc automatiques ; IC bootstrap des tailles d'effet (vectorisés)
- Rapport PDF dark/académique (chunked + repli léger)
- Défense Scientifique + annexes A/C/D/E ; scripts R/Stata/Colab
- Persistance SQLite WAL survivant aux redémarrages ; cache par utilisateur
- Cleanup périodique : fichiers, analyses, sessions
- Robustesse CSV francophones (encodage / séparateur / décimale)

---

## 7. Ce qui est partiellement implémenté

| Élément | Avancement | Commentaire |
|---------|-----------|-------------|
| Cleaning Core | ~70 % | Automatique + audit ; pas de consentement utilisateur |
| Rapport académique complet | ~90 % | Manque méthodo narrative séparée |
| Mode multi-tests autonome | ~85 % | Interprétation primaire = test le plus significatif |
| Frontend produit | ~75 % | Flux + auth + historique ; pas de settings/export |
| Tests pytest normalisés | ~40 % | Majorité de scripts manuels ; test_quota à réparer |
| ACM côté tests | partiel | Implémentée, fichier .py de test manquant |

---

## 8. Ce qui n'est pas encore implémenté

- File d'attente lourde (Celery/Redis) — BackgroundTasks + subprocess suffisent à la charge actuelle
- Accord utilisateur explicite avant cleaning / suppression doublons
- Export dataset nettoyé
- Tests inférentiels avancés (ANOVA factorielle, modèles mixtes, survival, bayésien)
- Clustering, séries temporelles, analyse de survie
- Affichage UI dédié de `skeptic_engine_alert`
- Internationalisation (UI FR hardcodée)
- CI GitHub Actions (proposée ; à créer `.github/workflows/tests.yml`)

---

## 9. Variables d'environnement requises

Fichier `.env` à la racine (jamais commit). Modèle : `.env.example`.

| Variable | Rôle | Défaut |
|----------|------|--------|
| `PRIMARY_API_KEY` | Clé LLM principal (Groq) | — |
| `PRIMARY_BASE_URL` | Base URL OpenAI-compat | `https://api.groq.com/openai/v1` |
| `PRIMARY_MODEL` | Modèle principal | `llama-3.3-70b-versatile` |
| `FALLBACK_API_KEY` | Clé secours (OpenRouter) | — |
| `FALLBACK_BASE_URL` | Base URL secours | `https://openrouter.ai/api/v1` |
| `FALLBACK_MODEL` | Modèle secours | `meta-llama/llama-3.1-8b-instruct:free` |
| `ALLOWED_ORIGINS` | Origines CORS, séparées par virgules | `http://localhost:3000` |
| `QUANTA_DB_PATH` | Chemin base SQLite | `/data/quanta.db` |
| `QUANTA_UPLOAD_DIR` | Répertoire uploads | `/data/uploads` |
| `GOOGLE_CLIENT_ID` | OAuth Google client ID | — |
| `GOOGLE_CLIENT_SECRET` | OAuth Google secret | — |
| `GOOGLE_REDIRECT_URI` | Callback OAuth (ex. https://...onrender.com/auth/callback) | — |
| `FRONTEND_URL` | URL frontend post-login | `http://localhost:3000` |
| `SESSION_SECRET_KEY` | Clé signature session (requis en prod ; warning sinon) | vide |

> Déploiement Railway : volume monté sur `/data` (base + uploads). Le volume est configuré côté tableau Railway, pas dans `railway.toml`.
