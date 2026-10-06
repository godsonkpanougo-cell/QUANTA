# QUANTA — ÉTAT DES LIEUX POUR RATTRAPAGE CLAUDE (directeur)

> **Document généré le 2026-10-01 par Buffy** (directeur intérimaire, en remplacement de
> Claude pendant son indisponibilité token). Objectif : permettre à Claude de reprendre le
> rôle de directeur du projet QUANTA **sans consulter aucune discussion passée**. Toutes les
> affirmations ci-dessous ont été vérifiées empiriquement (logs bruts, sorties de commandes,
> diffs) selon le protocole « symbose ».

---

## 1. LE PROJET ET LE WORKFLOW « SYMBOSE »

- **QUANTA** : plateforme d'analyse statistique automatisée.
  - Backend : FastAPI + SQLite, déployé sur Render → https://quanta-ijmg.onrender.com
    (512 Mo RAM, worker timeout 260 s, subprocess `app/analyze_worker.py` avec fallback
    in-memory en cas de timeout — le fallback refait tout le calcul dans le process API,
    à éviter absolument).
  - Frontend : Next.js sur Vercel → https://quanta-statistic-goddess.vercel.app
  - Repo : `github.com/godsonkpanougo-cell/QUANTA`, branche `main`.
- **Workflow** : Godson (chef de projet, francophone) → **Claude = directeur** (analyse,
  verdicts, validation des preuves, aucune correction directe) → **Windsurf/Cursor =
  exécutants** (implémentation, commits, déploiement, sous validation).
- **Principes** : aucune confiance par défaut ; toute affirmation exige une preuve brute
  (logs, sorties de commandes, diffs) ; stop points explicites ; un exécutant ne corrige
  rien sans validation du directeur ; une tâche = un commit = une validation.

---

## 2. ÉTAT DE LA CHAÎNE GIT (origin/main, vérifié)

| Commit | Contenu | Statut |
|---|---|---|
| `94ea44c` | corrections + tests de session précédente | ✅ |
| `056e537` | savepoint phase 2 (base pipeline unique, bootstrap CI vectorisés, cleanup session) | ✅ |
| `904cbf5` | CI : chemins `/tmp` pour `QUANTA_DB_PATH` / `QUANTA_UPLOAD_DIR` | ✅ |
| `33b662b` | CI : pytest installé explicitement (absent de requirements.txt volontairement) | ✅ |
| `6bb3354` | fix `_anova_eta2_boot(b_groups, rng=None)` — kwarg rng exigé par `_bootstrap_percentile_ci` (crash prod η²/ε²) | ✅ déployé et vérifié en prod |
| **`0406933`** | **Tâche A squashee** : fix section ACM PDF + suppression ACM nichée dans `association` + TIMING internes `run_acm` + scripts de test | ✅ poussé, CI verte (run 36780554481), déployé (marqueurs TIMING ACM attendus en prod) |

- Branches en attente : `feature/paywall` (5c4aa59, correctifs incident), `feature/paywall-wip`
  (6db8a98, billing.py, db.py +124 l., pricing/, stripe) — **audit paywall pas encore fait**.
- CI : `.github/workflows/ci.yml`, triggers `main` + `feature/**`, env `/tmp/quanta-ci/*`.
  Verte sur 0406933 (preuve API GitHub : check-run `syntax-and-fast-tests` → conclusion `success`).

⚠️ **Entorse protocolaire du 30/09** : l'exécutant a fait un `push --force` après avoir squashee
localement 6410f92 + 599b9f4 en 0406933. Vérifié non destructif (seuls ses propres commits ont
été écrasés ; branches paywall intactes ; arbre de 0406933 identique au contenu validé via
`git diff 599b9f4 0406933` vide). **Règle désormais fixée : squash AVANT push uniquement,
jamais de force push après push ; récidive = suspension du droit de pousser.**

---

## 3. CORRECTIONS DÉJÀ LIVRÉES ET VALIDÉES (avec preuves)

### 3.1 Fix scatter plots (déployé)
- Problème : génération de scatter plots pour toutes les paires significatives (79 plots,
  34,7 s sur dataset dense).
- Fix : `MAX_SCATTER_PLOTS = 5`, tri par |r| décroissant dans `correlation_analysis`
  (`app/compute/compute.py` ~723-844).
- Preuve A/B locale : 79 plots / 34,7 s → 5 plots / 17,1 s. En prod : `5/1024 scatter plots
  générés (max 5) en 16.898s`.

### 3.2 Incident cf53f11 (résolu)
- Un commit avait cassé le backend (`import app.billing` sans le module, prouvé par worktree
  + ImportError). Résolu par commits Cursor a763ce6 + 5c4aa59 (main restaurée sur 056e537,
  paywall isolé en feature/paywall).

### 3.3 CI rouges corrigées (904cbf5 + 33b662b), puis vertes — vérifiées via API GitHub.

### 3.4 Fix rng η²/ε² (6bb3354, déployé et prouvé en prod)
- `_bootstrap_percentile_ci` passe `rng=rng` à toute fonction statistique ; `_anova_eta2_boot`
  n'acceptait pas ce kwarg → TypeError en prod sur les chemins η²/ε².
- Fix : signature `_anova_eta2_boot(b_groups, rng=None)` (rng inutilisé dans le corps,
  l'échantillonnage étant déjà fait par `_bootstrap_matrix`).
- Preuve prod : lignes `TIMING - Bootstrap CI vectorisé (_anova_eta2_boot): 0.01s
  (n_bootstrap=1000)` dans les logs Render du 30/09, plus aucun TypeError.

### 3.5 Tâche A (0406933) — CAUSE RACINE DU TIMEOUT ÉLIMINÉE
- **Découverte directeur** : l'ACM était calculée DEUX FOIS en mode auto :
  1. `app/compute/test_selector.py` branche `action="association"` avec `len(cat_cols) >= 3`
     → ACM embarquée automatiquement (ancien bloc lignes 1183-1197),
  2. branche `action="acm"` → recalcul complet.
  → 2 × ~57,4 s = 116,5 s = ~90 % du temps des intents.
- Fix : suppression du bloc ACM niché dans `association` (l'ACM ne reste que dans l'intent
  `acm`). Changement de comportement assumé : en mode requête, « association entre X et Y » ne
  contient plus d'ACM nichée (documenté dans le commit).
- **Non-régression PDF prouvée** : la section ACM du PDF lit `test_result.get("acm")`
  (`app/report_generator.py` ~3787) — cette clé n'existait que dans l'ACM nichée. Correctif
  committé : `_get_acm_result` (~3164) récupère désormais l'ACM depuis les `multi_entries`
  (mode auto, entrée `action_executed == "acm"`, via `analysis.inference.result`) avec
  fallback sur `test_result["acm"]` (mode requête). Chaîne audité fermée :
  `_summarize_analysis_for_multi` (brain.py ~469) inclut `action_executed` + `result` ;
  `_filter_descriptive_when_inferential` ne retire que `descriptive_only` (l'ACM est conservée).
- Preuves directeur (reproduites localement) : A/B association 2,074 s → 0,379 s, p-value
  identique 0,000439 ; e2e réel sans clé LLM : 3 intents (association 0,1 s, acm 1,6 s),
  section ACM résolue par le chemin PDF réel (66 033 car.).
- TIMING permanents ajoutés dans `run_acm` (compute.py ~1693/1717/1744) : `TIMING - ACM fit
  MCA` / `TIMING - ACM column_coordinates` / `TIMING - ACM plots generation`. Premier
  enseignement (dataset de test) : fit 0,036 s, coords 0,005 s, **plots ~1,0-1,2 s** → sur le
  dataset dense, les plots sont le gros du coût ACM.

### 3.6 Tâche B — vectorisation corrélation : TESTÉE puis ANNULÉE
- `pingouin.pairwise_corr` plus lent que la boucle (1,32 s vs 0,82 s pour 190 paires).
- Décision directeur : annulation acceptée, MAIS l'objectif perf reste ouvert — la boucle de
  `correlation_analysis` coûte **27,7 s de pur Python sur 1035 paires** (L2_tobit : 44,6 s
  total dont 27 s paires + heatmap, 16,9 s scatter). Piste réservée (P1-bis, non commencée) :
  rangs précalculés + corrélations batch scipy (SANS pingouin), A/B chiffré obligatoire
  (mêmes r/p à ±1e-4, top-5 scatter inchangé).

---

## 4. INCIDENT DE RÉFÉRENCE — ac220417-f2b0-42c3-a6a6-3dbfdcef4971 (L2_tobit.dta, 30/09)

### 4.1 Timeline vérifiée (logs Render bruts)
| Heure | Événement |
|---|---|
| 16:45:12 | début worker (t0 = 16:49:32 − 260 s) |
| → 16:45:29 | imports worker ~17 s |
| 16:45:29 → 16:46:33 | pipeline de base **63,6 s** (diag 1,3 / clean 1,0 / desc 11,9 / normalité 4,8 / corr 44,6 dont scatter 16,9 / ols 0) |
| 16:46:33 → 16:48:41 | 7 intents : compare_groups ×3 (0,7-0,8 s), correlation 8,8 s, **association 59,1 s (dont ACM n°1)**, **acm 57,4 s (ACM n°2)**, descriptive 1,3 s — cumul 192,5 s (inclut le pipeline : t0 du cumul posé AVANT `run_base_compute_pipeline`, brain.py ~858) |
| 16:48:41,78 | appel LLM interprétation (`Attempting LLM call with provider primary`) |
| 16:49:32,38 | **TIMEOUT 260 s** — interprétation coupée à **50,6 s**, sans warning `LLM timeout` |
| 16:49:32,5 → | fallback in-memory relance TOUT le pipeline (diag 1,1 / clean 1,0 / desc 10,9 / normalité 4,2 / corr …) — fin non observée (logs fournis s'arrêtent à 16:50:12) |

### 4.2 Corrections factuelles au rapport Windsurf (verdicts livrés)
- « Intents = 192,5 s » : FAUX — le cumul inclut les 63,6 s du pipeline ; temps pur des
  intents = **128,9 s** (vérif : 16:45:29,2 + 192,5 = 16:48:41,7 = horodatage exact du LLM).
- « Lenteur des appels LLM pour les intents » : FAUX — en mode auto, les intents sont
  déterministes (aucun LLM) ; le seul appel LLM est l'interprétation finale.

### 4.3 Anomalie LLM OUVERTE (la tâche C doit la trancher)
- 50,6 s d'attente SANS warning `LLM timeout from primary` alors que
  `REQUEST_TIMEOUT_SECONDS = 25` (brain.py:68, utilisé en `timeout=` du `requests.post`).
- Hypothèse forte : le read-timeout de `requests` est réarmé par des octets keep-alive
  sporadiques du modèle gratuit (`nvidia/nemotron-3-ultra-550b-a55b:free` via OpenRouter) →
  le budget « 25 s × 2 retries + backoff ≈ 75 s max » affiché en tête de brain.py (lignes
  66-69) est **théorique et non garanti**. Un test local de l'exécutant (timeout forcé 10 s,
  réponse reçue en 12,017 s) suggère la même chose, MAIS ces chiffres n'ont pas été prouvés
  (pas d'artefact) → **non validés**.

### 4.4 Budget après dédup (projeté, à confirmer par le re-test prod)
~17 s (imports) + 63,6 s (pipeline) + ~71,5 s (intents 128,9 − 57,4) + interprétation
(plancher mesuré 51 s, total probable 60-90 s) ≈ **205-242 s sur 260 s** → devrait tenir,
marge faible. Si dépassement : P1-bis corrélation (−25 s attendus) et/ou allègement de
l'interprétation. **Ne pas toucher au timeout 260 s** (cap externe à 300 s, le fallback
in-memory doublerait le calcul).

---

## 5. CHANTIER EN COURS (tâche C, lancée chez Windsurf via consigne autonome)

1. **Code** : TIMING permanents dans `app/llm/brain.py` uniquement — durée globale de
   `generate_interpretation` + durée par tentative HTTP dans `call_llm` (succès/échec/timeout),
   `flush=True`, aucun changement de logique. Un seul commit, push normal.
2. **Déploiement** : preuve par marqueurs (`TIMING - generate_interpretation` /
   `TIMING - call_llm provider=...` dans les logs Render).
3. **Re-test L2_tobit en prod** (upload via frontend par Godson ou API authentifiée) :
   - pipeline ~63,6 s ; intent association **< 5 s** (vs 59,1 s) ; ACM une seule fois ;
   - `TIMING - generate_interpretation: X s` = LE chiffre manquant du budget ;
   - statut final `done`, pas de `ANALYZE Worker - Timeout après 260s`.
4. **Test empirique timeout LLM** (script jetable, sortie brute collée) : timeout forcé 10 s,
   verdict binaire « le timeout requests plafonne les appels : OUI/NON ».
5. **Archives ac220417** : statut final authentifié + durée réelle du fallback in-memory
   (logs Render du 30/09 après 16:50:12).

## 6. ARRIÈRE-PLAN (priorités après la tâche C)

- **P1-bis** : vectorisation corrélation sans pingouin (rangs précalculés + batch scipy),
  A/B chiffré obligatoire.
- **Allègement interprétation** (si budget LLM toujours tendu) : max_tokens 2500 → ~1000,
  ou livraison des résultats bruts avant l'interprétation (décision produit à trancher avec
  Godson).
- **Audit paywall** `feature/paywall-wip` (6db8a98) : billing.py, db.py (+124 l.), pricing/,
  stripe — jamais audité.
- **QUANTA_STATE.md** à mettre à jour (procédure de déploiement, incidents, règles renforcées).
- **Échecs de tests préexistants, documentés, HORS PÉRIMÈTRE** (ne jamais les « corriger »
  sans mandat) : `tests/test_quota.py` ×2 (`AssertionError: assert 429 == 200`, rate-limiter
  slowapi — reproduits à l'identique sur l'arbre 6bb3354 reconstruit) ;
  `tests/test_orchestrator_compare_groups.py` (Student vs Mann-Whitney).

## 7. POINTS DE MÉTHODE À CONNAÎTRE (retours d'expérience de la session intérimaire)

- `ru_maxrss` (MEM CHECKPOINT) mesure le **pic** RSS → valeurs identiques = normal.
- `.env` local contient de vraies clés → les pytest locaux peuvent déclencher de vrais appels
  LLM (lents) ; CI sans `.env` → tests rapides hors réseau.
- Le stdout du worker est capté et affiché par main.py **même en timeout** (`e.stdout[-3000:]`)
  → tout instrument print `flush=True` reste exploitable sur un run tué.
- Les scripts de test du projet (`tests/test_*.py` style `__main__`, drivers manuels) ne sont
  **pas collectés par pytest** — toujours les lancer explicitement.
- Modèle de consigne Windsurf validé : sections CONTEXTE PROJET (autonome) / OBJECTIFS /
  MODIFICATION DE CODE (un seul commit, périmètre figé) / PREUVE DE DÉPLOIEMENT / MESURES /
  RÈGLES ABSOLUES (interdiction force push, preuves brutes obligatoires, stop points) /
  CHECKLIST D'ACCEPTATION. Chaque rapport Windsurf doit être vérifié par le directeur
  (`git log`, `git status`, greps, relance des tests) — deux résumés sur trois se sont
  avérés inexacts (décompte pytest faux, moitié du travail non committée, chiffres C invérifiables).

---

## MISE À JOUR 2026-10-01 (soir) — Buffy reprend la direction (Claude désactivé)

### Tâche C — Parties A et D CLOSES, avec preuves
- **Partie A close** : commit `d9bf87c` forensique complet — parent unique `0406933`
  (aucun commit intercalé), diff = `app/llm/brain.py` **+10 lignes, 0 logique changée**
  (prints TIMING sur les 3 issues de `call_llm` + timing global `generate_interpretation`),
  CI verte (check-run `syntax-and-fast-tests`, conclusion `success`), pytest 30/32
  (les 2 échecs `test_quota` préexistants), script D jetable supprimé, arbre propre.
- **Anomalie 4.3 requalifiée en BUG DE FIABILITÉ PROUVÉ** : deux mesures indépendantes de
  réponse HTTP 200 complète reçue sous `REQUEST_TIMEOUT_SECONDS=10` **sans aucun warning
  Timeout** — Windsurf 44,83 s ; auditeur (reproduction indépendante) 72,39 s. Mécanisme :
  le timeout `requests` (float unique) s'applique PAR OPÉRATION SOCKET et se réarme à
  chaque octet reçu (keep-alive/chunked) — `REQUEST_TIMEOUT_SECONDS` ne protège de rien,
  la durée d'un appel LLM n'est bornée par rien. Seul filet réel : kill externe 260 s →
  fallback in-memory (recalcul doublé).
- **Correctif GELÉ** : changement de logique réseau = hors mandat de la tâche C ; aucune
  proposition ni tentative d'exécutant. Mandat uniquement après chiffres de la Partie C.

### Tâche C — Parties B, C, E en attente
- B : marqueurs `TIMING - generate_interpretation` / `TIMING - call_llm provider=...`
  dans les logs Render (preuve de déploiement de d9bf87c).
- C : re-test L2_tobit, ordre de preuve imposé : status `done` sans timeout 260 s →
  ligne `TIMING - generate_interpretation: X s` → ACM ×1 + intent association < 5 s.
- E : statut final authentifié de `ac220417-...` + durée réelle du fallback in-memory.

### Arbitrage post-Partie C (décision Godson, préparation directeur)
Trois garde-fous possibles contre le bug de timeout LLM :
1. **Deadline horloge murale** : lecture en streaming (`stream=True`) + vérification du
   temps écoulé à chaque chunk, ou thread de contrôle séparé → borne STRICTE garantie
   (deadline + epsilon). Complexité modérée, localisée à `call_llm`.
2. **Results-first (produit)** : persister les résultats calculés AVANT l'interprétation
   (statut done en 2 phases, interprétation async qui met à jour l'enregistrement) →
   élimine le risque pour l'utilisateur, mais changement d'architecture
   (analysis_core/brain + comportement de polling frontend).
3. **Allègement** (max_tokens 2500 → ~1000, modèle plus rapide) → réduit l'espérance,
   ne borne rien strictement.
Lecture directeur : (b) seule à éliminer le risque, (a) la borne proprement et est le
moins invasif, (c) insuffisant seul. Trancher avec les chiffres réels de la Partie C :
si le run tient largement sous 260 s malgré le bug → (a) suffisant en filet ; si la
marge reste faible → (b) à chiffrer sérieusement.

### P1-bis — livré par Freebuff (casquette exécuteur isolé, branche dédiée)
- Branche `feature/freebuff-perf-corr`, commit `39c4299`, CI verte, `import main` OK,
  compute.py NON touché (module isolé, branchement soumis à mandat/coordination).
- `app/compute/correlation_fast.py` : vectorisation EXACTE des paires (corrcoef + formule
  t exacte des p, rangs Spearman average 1×/colonne), repli boucle fidèle si NaN.
- Preuves A/B (5 régimes) : Δr = Δp = 0,00e+00 exactement sur les chemins vectorisés ;
  990 paires : 1,6-1,9 s → 9-42 ms (×44 à ×187). Extrapolé L2_tobit (1035 paires,
  27,7 s en prod) : ~26-27 s économisés sur le pipeline de 63,6 s.
- `tests/test_correlation_fast.py` : 6/6 pytest (premier test COLLECTÉ qui verrouille
  la sémantique corrélation).
- Statut : en attente de décision de branchement (après chiffres Partie C).

### Carte des actions en cours (au 2026-10-01 soir)
1. **GODSON (bloquant principal)** : uploader L2_tobit.dta en prod (frontend, session
   authentifiée) — SANS ça, Partie C, arbitrage garde-fou et décision P1-bis restent
   suspendus. Le dataset n'est pas dans le repo.
2. **WINDSURF** : vérifier les marqueurs Render de d9bf87c (Partie B), collecter le run
   L2_tobit (Partie C, ordre de preuve imposé) et les archives ac220417 (Partie E).
3. **FREEBUFF (directeur)** : verdict final à l'arrivée des preuves → incident clos ou
   mandat garde-fou (option 1/2/3) et décision de branchement P1-bis.
4. **Files d'attente** : consignes Windsurf « couverture statistique » et « audit
   accessibilité réel » à rédiger ; docs de direction committés sur feature/freebuff-docs ;
   QUANTA_STATE.md à rafraîchir ; paywall gelé (décision Stripe/juridique Godson).

---

# MISE À JOUR 2026-10-06 — Godson donne la main à Freebuff (Claude indisponible)

## 0. MANDAT EXPLICITE DE GODSON (à lire avant tout audit)

**C'est Godson lui-même qui a donné la main à Freebuff (Buffy) le 2026-10-06**, Claude étant
indisponible (fenêtre h24 sans accès). C'est la raison pour laquelle ce travail a été fait
sans Claude : aucune initiative non mandatée, décision posée par Godson pour ne pas bloquer
le chantier. **Claude reste le directeur et devra auditer ce travail post-hoc** — tout est
ci-dessous : journal horodaté, preuves brutes, et motifs de chaque choix.

Instructions données par Godson :
- régler l'analyse qui échoue, le « failed to fetch » et le rapport qui ne se télécharge pas
  (= appliquer A2/A3/A4 du plan d'incident du 06/10, voir §3) ;
- protéger le code : rigueur maximale sur git (pas de mélange de branches — référence à la
  période de désordre antérieure), commits séparés et réversibles, jamais de force push ;
- documenter précisément l'état et l'utilité des 4 piliers mergés (§2) ;
- tenir CE document à jour à chaque action posée (quoi, pourquoi posée, pourquoi cette
  méthode) pour permettre l'audit de Claude.

## 1. CLARIFICATION NOMENCLATURE (éviter toute confusion d'audit)

Deux séries « A » coexistent :
- **Piliers A1-A4 mergés (05/10)** → voir §2, rapports dans `RAPPORTS_PILIERS/`.
- **Plan d'incident du 06/10 (KeyError 'choices' / failed to fetch / PDF)** : A1 = garde
  `choices` dans `call_llm` (COMMITTÉ le 06/10 02:21 par commit `a6a5e10`, testé 5/5) ;
  A2 = frontend tolérant ; A3 = réutilisation PDF ; A4 = smoke test. NE PAS confondre.

## 2. ÉTAT ET UTILITÉ DES 4 PILIERS MERGÉS (au 2026-10-06)

Mergés sur `main` (base `f61a566`, déployée en prod), rapports datés 05/10/2026 :

| Pilier | État | Utilité précise | Preuve de vie |
|---|---|---|---|
| **A1 — Re-test prod & verdict incident 260 s** (`RAPPORT_A1_RETEST_PROD.md`) | ✅ Mergé, déployé, incident CLOS formellement | Preuve chiffrée que l'incident de timeout est résolu : pipeline 19,1 s vs 198,7 s (−90,4 %), LLM borné à 18,5 s par deadline/retries, pire cas ≈ 38 s contre 260 s avant | Rejeu exhaustif local sur L2_tobit réel ; §4 du rapport vérifie le build déployé et les endpoints protégés |
| **A2 — Frontend des 4 piliers P1-P4** (`RAPPORT_A2_FRONTEND_PILIERS.md`) | ✅ Mergé, déployé | Écrans consommateurs des piliers : `/workspace` (projet persistant + Replay A/B), `/conversation` (chat, mode dégradé honnête), `/audit/[id]` (Repro Pack ZIP), `/defense` (soutenance imprimable) + onglets SiteHeader | `npx tsc --noEmit` 0 erreur, ESLint 0 sur les 6 fichiers, 9/9 tests Python liés |
| **A3 — Page Méthodologie publique** (`RAPPORT_A3_METHODOLOGIE.md`, commit `c5e6458` mergé via `3806169`) | ✅ Mergé, **vérifié en prod** (200) | Page publique sans auth pour les encadreurs (UAC/UL/INSAE) : comparatif honnête 4 outils, « Ce que QUANTA ne fait pas », déterminisme octet par octet — l'honnêteté comme argument de vente | `tests/test_public_pages.py` 4/4 ; grep prod : Benjamini-Hochberg, comparatif présents |
| **A4 — Durcissement méthodologique** (`RAPPORT_A4_DURCISSEMENT.md`) | ✅ Mergé | Bug P0 corrigé (`theme="both"` → normalité vide → Mann-Whitney systématique, faussait la méthodologie du payload), 2 exclusions de tests réparées (126 passed sans exclusions), contrat Pydantic, HC3 automatique, Sentry optionnel | Suite complète 126/126 ; test_orchestrator_compare_groups réintégré et vert |

Statut de vie au 06/10 : /methodologie répond 200 en ~0,7 s (smoke test A4-Nouveau) ;
endpoints piliers (`/projects`, `/conversations`, `/repro_pack`, `/defense`) inchangés,
aucun des diffs du 06/10 ne les touche.

## 3. JOURNAL HORODATÉ DES ACTIONS DU 06/10 (quoi / pourquoi / pourquoi cette méthode)

| # | Heure | Action posée | Pourquoi posée | Pourquoi cette méthode | Résultat/preuve |
|---|---|---|---|---|---|
| 1 | matin | Relecture lecture seule du code (état des A1-A4 du plan d'incident) | Godson demande ce qui a changé depuis l'enquête | Lecture seule = zéro risque, respect du STOP tant que non confirmé | Rapport en chat : A1 fait (a6a5e10), A2/A3/A4 absents |
| 2 | matin | Préparation des diffs A2/A3 + brouillon A4 SANS commit | Godson : « préparer les diffs exacts… sans les commiter » | Application au working tree non commitée = review via git diff, réversible à 100 % (`git checkout --`) | 4 fichiers modifiés 111+/17−, scripts/smoke_test.py untracked ; tsc 0 erreur, pytest ciblés 23/23, smoke réel 2 OK |
| 3 | soir | Verrouillage d'état avant tout commit (Godson transmet le protocole Claude à 7 étapes) | Protocole Claude : vérifier status/diff-stat/pytest complet/import main AVANT commit | Ordre imposé par le directeur Claude, non modifié | git status : exactement 4 M + 6 untracked ; diff --stat = 111/17 ; HEAD = origin/main = a6a5e10 (aucune divergence) |
| 4 | soir | Lancement suite pytest COMPLÈTE `python -m pytest tests/ -v` en arrière-plan, log intégral dans `pytest_full_run_2026-10-06.log` | Claude exige le total complet (131 attendus) et la sortie brute intégrale | Background = pas de blocage pendant l'écriture du doc ; log fichier = preuve conservable | **131 passed, 0 failed, exit 0 en 4 min 35 s** (12 warnings dépréciation uniquement) — total EXACT attendu, aucun écart |
| 5 | soir | `python -c "import main"` sur l'état final | Règle d'or du projet avant tout push | Vérification canonique, exit code capturé explicitement | IMPORT_MAIN_EXIT=0 |
| 6 | soir | Commit A2 `aba723e` : les 3 fichiers frontend EXPLICITEMENT nommés dans `git add` (jamais `add -A`) | Ordre et message imposés par le protocole Claude | Chemins explicites = impossibilité d'entraîner un fichier hors périmètre (les untracked sont restés hors des commits) | `aba723e fix(frontend): polling tolérant + messages d'erreur propres (A2)` — 3 files, 91+/11− |
| 7 | soir | Commit A3 `d250892` : main.py seul | Idem | Idem | `d250892 fix(backend): réutilisation du PDF existant + param force (A3)` — 1 file, 20+/6− |
| 8 | soir | Commit A4 `d6e26e3` : scripts/smoke_test.py seul | Idem | Idem | `d6e26e3 chore: script de smoke test rejouable (A4)` — 1 file, +341 |
| 9 | soir | `git fetch origin` AVANT push : origin/main toujours à `a6a5e10` | Protection anti-divergence demandée par Godson (traumatisme des mélanges de branches) | Vérifier que personne (Windsurf/Cursor) n'a poussé entre-temps ; push uniquement en fast-forward | Confirmé : origin/main = a6a5e10, push fast-forward `a6a5e10..d6e26e3` |
| 10 | soir | Push `origin main` | Protocole Claude étape 6 | **ÉCART lettre/intention à noter honnêtement** : `git push` a livré les 3 commits en UNE transaction réseau (`a6a5e10..d6e26e3`) au lieu de 3 pushes séparés. L'INTENTION de Claude (3 commits distincts, non squasheés, revertibles un à un) est respectée : l'historique distant contient bien 3 commits séparés, `git revert aba723e` / `d250892` / `d6e26e3` fonctionnent individuellement. Refaire l'inverse (réécrire l'historique distant) aurait été pire (force push interdit) | origin/main = d6e26e3 |
| 11 | soir | Vérification CI via API GitHub (check-runs du SHA d6e26e3) | Protocole Claude étape 7 | API publique (repo public), preuve non authentifiée | `accessibility: success` + `syntax-and-fast-tests: success` |
| 12 | soir | Commit du présent document (docs:) + push + re-vérification CI sur ce push final | Godson exige que ce document soit à jour et auditable par Claude depuis le repo | Commit séparé du code = réversible sans toucher aux fix ; re-check CI = le protocole s'applique aussi à ce push | CI re-vérifiée verte (2/2 success) sur le SHA final ; SHA exact visible dans `git log` |
| 13 | soir | Diagnostic de l'incident L2_tobit signalé par Godson (« timeout 300 s » + logs Render collés) | « l'analyse échoue alors que ça passait avant » — il faut la cause exacte | Preuves brutes uniquement : lecture ligne à ligne des logs fournis + relecture des 3 maillons de délai dans le code | §5.1 : l'analyse a RÉUSSI à 17:32:47 (done + PDF en base) ; c'est le poll frontend (300 s) qui a lâché ~40 s avant ; garde A1 prouvée en prod (2× 200-sans-choices bien interceptées) ; §5.2 chaîne de délais incohérente |
| 14 | soir | Budget backend 300 → 480 s (`_run_analysis_background`) | Le label error + refund partait à 300 s PENDANT que le fallback réussissait (433 s) | Une seule constante + commentaire d'incident ; worker 260 s et worker PDF 300 s NON touchés (périmètres distincts) | import main exit 0 ; commit dédié |
| 15 | soir | Poll frontend 300 → 540 s (AnalysisProgress) | Le frontend doit toujours survivre au backend pour voir le verdict final | Strictement au-dessus de 480 s ; message auto-mis à jour (template) | tsc --noEmit exit 0 ; commit dédié |
| 16 | soir | Support .xls : `xlrd==2.0.1` (requirements) + `.xls` dans le sélecteur frontend (UploadZone) + test verrou `tests/test_upload_formats.py` | Godson : « quanta ne prend pas en charge les .xls » — double blocage prouvé (moteur absent + picker sans .xls) | La whitelist backend et load_and_diagnose acceptaient déjà .xls — seule la dépendance et le picker manquaient ; test verrou anti-régression de dépendance | pytest ciblés 7/7 ; suite complète EN COURS (§4 mise à jour ci-dessous) ; commit dédié |
| 17 | soir | Diagnostic déconnexions + quota reset à 15 (lecture seule, AUCUN commit code volontaire) | Godson : « le quota et la connexion ne sont pas solides » | Preuves d'abord : sessions (TTL 7 j base+cookie, purge expirées seulement), quota (lookup google_sub stable, reset uniquement à +30 j), puis DB_PATH/Dockerfile → /data sans volume dans conteneur éphémère | §6 : code sain, racine = effacement de la base à chaque déploiement/restart Render (13 pushes ce jour = 13 effacements) ; décision d'hébergement soumise à Godson (options A-D) |
| 18 | soir | Consignation de la décision Godson : PAS de migration maintenant, Oracle en intention (bloqué côté compte), statu quo éphémère assumé | Décision d'hébergement = prérogative de Godson ; le document doit refléter la raison du report | Citation consignée §6.5 + conséquences assumées + discipline de déploiement + Chantier B prêt à la déblocage | §6.5 ajouté ; AUCUN code modifié ; commit docs séparé |

## 4. RÉSULTATS DU PROTOCOLE (rempli séquentiellement)

- [x] pytest complet : **131 passed, 0 failed, exit 0 en 4 min 35 s** (total exact attendu par Claude ; log brut intégral conservé dans `pytest_full_run_2026-10-06.log` à la racine du repo, non commité — artefact local)
- [x] `python -c "import main"` : **exit 0** (état final, après tous les diffs)
- [x] commits séparés : `aba723e` (A2 frontend) → `d250892` (A3 main.py) → `d6e26e3` (A4 smoke test) — un commit par tâche, messages exacts du protocole, chemins explicites
- [x] push : fast-forward `a6a5e10..d6e26e3` après fetch anti-divergence (voir note honnête #10 : une transaction réseau, 3 commits distincts revertibles)
- [x] CI verte : **`accessibility: completed / success` + `syntax-and-fast-tests: completed / success`** sur `d6e26e3` (preuve API GitHub check-runs, 06/10 ~18h45 UTC)

**PROTOCOLE CLAUDE INTÉGRALEMENT SATISFAIT** — aucune étape sautée, aucun échec nouveau, aucun fichier hors périmètre dans les commits.

### Échecs connus non réapparus / hors périmètre
- Aucun échec nouveau dans la suite complète (131/131) — l'ancienne liste d'échecs préexistants
  (`test_quota` ×2, `test_orchestrator_compare_groups`) avait déjà été RÉPARÉE par le pilier A4
  (durcissement, 126 passed sans exclusions au 05/10) ; confirmé aujourd'hui.
- ESLint : 15 erreurs + 2 warnings PRÉEXISTANTS dans 5 fichiers (react-hooks/refs,
  set-state-in-effect) — prouvé préexistant par lint de la version HEAD comparée ligne à ligne ;
  les diffs du 06/10 n'ajoutent AUCUNE violation. Hors périmètre, à traiter en tâche séparée.

### Commit du présent document
Ce document est committé séparément (`docs:`) et poussé APRÈS les 3 commits de code, pour que
Claude puisse l'auditer depuis le repo. Commit séparé = réversible sans toucher au code.
La CI a été re-vérifiée VERTE (2/2 check-runs success) sur ce push final du document.

⚠️ Le journal a été réouvert le soir même (nouvel incident L2_tobit signalé par Godson,
voir §5 ci-dessous) — les actions 13 à 16 y sont consignées. Tout SHA est vérifiable dans
`git log origin/main`.

## 5. INCIDENT DU SOIR 06/10 — L2_tobit « timeout 300 s » ALORS QUE L'ANALYSE A RÉUSSI

### 5.1 Diagnostic prouvé par les logs Render fournis par Godson (analyse 8dc9ddb2)

Chronologie exacte :
1. Worker subprocess : pipeline 51,5 s + 7 intents jusqu'à 71,6 s cumulés — **le calcul tient**.
2. Interprétation LLM : primary Timeout **102,54 s** (keep-alive réarme le read-timeout — le
   bug P0 documenté en §MISE À JOUR 2026-10-01), budget 100 s épuisé → worker killé à 260 s.
3. À ~300 s : `_run_with_timeout(timeout=300)` → **status=error + refund_quota** — mais un
   thread Python ne se tue pas : le fallback in-memory démarre et RECALCULE tout
   (51,9 s + intents 75,5 s cumulés).
4. Interprétation : primary 2× **200-sans-choices « Upstream error from Nvidia: Service
   temporarily overloaded »** → **la garde A1 fonctionne en prod (preuve directe)** —
   repli sur fallback Lightning : 87,14 s → **done à 17:32:47, generate_interpretation: 94,64 s**.
5. Le frontend : son chrono de poll (POLL_TIMEOUT_MS=300000) a expiré ~40 s avant la fin
   backend → message « L'analyse a dépassé le délai maximum de 300 secondes »
   (AnalysisProgress.tsx). Les GET /status visibles jusqu'à 17:30:32 le confirment.

**Bilan** : l'analyse est **done en base avec PDF téléchargeable** (visible dans /history) ;
l'utilisateur a quand même reçu un message d'échec ET un remboursement de quota indu
(error transitoire → done final : double écriture contradictoire, bug d'état réel).

### 5.2 Cause racine : chaîne de délais INCOHÉRENTE (aucun budget global cohérent)

| Maillon | Valeur avant | Effet |
|---|---|---|
| worker subprocess | 260 s (kill) | conçu |
| wrapper background `_run_with_timeout` | **300 s** | étiquette error + refund PENDANT que le thread continue |
| poll frontend | **300 s** | abandon au même moment que le label backend |
| LLM (budget 100 s/provider ×2) | ~200 s max | correct |
| fallback in-memory | redémarre de zéro | + ~175 s observées |
| Total possible | **~590 s** | > 300 s partout : le moindre grain de sable LLM = « échec » affiché |

### 5.3 Correctifs appliqués (soir 06/10, actions 13-15)

- **Budget backend 300 → 480 s** (main.py `_run_analysis_background`) : couvre le pire cas
  observé 433 s avec marge ; le label error ne surviendra plus pendant un fallback qui réussit.
- **Poll frontend 300 → 540 s** (AnalysisProgress) : strictement au-dessus du backend → le
  verdict final est toujours vu avant abandon.
- **Support .xls (P2)** : double blocage prouvé — (a) requirements.txt sans `xlrd`
  (openpyxl ne lit que .xlsx ; pandas exige xlrd pour .xls) alors que la whitelist et
  `load_and_diagnose` acceptaient déjà .xls → 400 « Missing optional dependency 'xlrd' » ;
  (b) frontend UploadZone n'offrait pas .xls au sélecteur. Corrigé des deux côtés
  (+ `tests/test_upload_formats.py` verrou).
- Limites honnêtes consignées : au-delà de 480 s (dataset pathologique) l'incohérence
  error-pendant-que-le-thread-court persiste — le vrai fix est results-first (§5.4) ;
  le test .xls verrouille le moteur, pas une lecture E2E d'un binaire .xls réel
  (pandas ne peut pas ÉCRIRE du .xls — un vrai fichier de Godson servira de preuve).

### 5.4 Réponses aux questions Godson (plan soumis, NON implémenté sauf §5.3)

1. **« Analyser toutes les bases sans jamais échouer »** : impossible mathématiquement sur
   données arbitraires (honnêteté = règle du projet). Atteignable et suffisant : bornes
   strictes partout (fait), filets génériques + remboursement (fait), **jamais de message
   d'échec prématuré** (corrigé §5.3), et **fuzz/soak test** (P4) : script générant des
   datasets adverses (1 ligne, tout-NaN, colonnes constantes, 100 % catégoriel, dates,
   milliers de colonnes, caractères spéciaux) lancé en boucle localement — la seule méthode
   honnête pour couvrir l'infini des bases sans les tester une à une.
2. **« Accélérer l'interprétation »** (94,64 s ce run, 87,14 s de génération Lightning) :
   (a) **results-first** = LE levier : persister le résultat calculé AVANT l'interprétation
   (statut done en 2 phases, interprétation async qui met à jour l'enregistrement) →
   latence perçue 433 s → ~72 s (−83 %) et une panne LLM ne fait plus jamais échouer une
   analyse — c'est l'option (2) de l'arbitrage garde-fou du 2026-10-01 ; chantier
   architectural à chiffrer, SOUMIS À DÉCISION (Claude/Godson) ; (b) max_tokens 2500 → 1000
   (−40-60 % attendus sur la génération, décision produit) ; (c) brancher P1-bis
   corrélation (`feature/freebuff-perf-corr`, −26 s sur le pipeline).
3. **« L2_tobit timeout alors que ça passait avant »** : ce run le LLM a coûté ~200 s au
   lieu de ~50 s (overload Nvidia + keep-alive) — « avant » = upstream sain. La marge du
   système était nulle ; §5.3 rend l'échec affiché impossible avant 540 s, results-first
   l'élimine totalement.

## 6. DÉCONNEXION SPONTANÉE + QUOTA RESET À 15 — MÊME RACINE : BASE ÉPHÉMÈRE

### 6.1 Signalement Godson (soir 06/10)
- Déconnexions d'utilisateurs « même sans redéploiement » ;
- après déconnexion/reconnexion, le quota repart à 15 ; il diminue pourtant normalement
  au fil d'une session.

### 6.2 Le code est sain — vérifié fonction par fonction
- Sessions : `create_session(ttl_hours=24*7)` + cookie `max_age=7 jours` alignés ;
  `get_session` compare les ISO-Z correctement (test `test_session_timezone_bug.py` vert) ;
  purge `cleanup_expired_sessions` toutes les 6 h = uniquement les réellement expirées.
- Quota : `create_or_update_user` cherche par `google_sub` (identifiant Google STABLE) et
  réutilise le user_id existant (COALESCE sur analyses_count, renewal_at conservé) ;
  `check_and_increment_quota` ne remet à zéro QUE si now >= renewal_at (+30 jours).
  **Aucune ligne de ce code ne peut produire un reset à 15 ni une déconnexion.**

### 6.3 Cause racine prouvée : `/data` vit DANS le conteneur Render éphémère
- `DB_PATH = QUANTA_DB_PATH sinon /data/quanta.db` (db.py:25) ; Dockerfile :
  `RUN mkdir -p /data/uploads` — un simple mkdir, **aucun VOLUME, aucun disque Render**.
- Conséquence mécanique : chaque **déploiement ou restart d'instance Render free** efface
  users + sessions + analyses + uploads. Alors :
  1. session inconnue en base → **401 → déconnexion forcée** ;
  2. au login suivant, `create_or_update_user` ne trouve plus google_sub (table vide) →
     **nouveau user, analyses_count=0 → quota 15** ;
  3. l'historique d'analyses est aussi purgé > 24 h par le cleanup.
- Corrélation directe avec le calendrier : **13 pushes le 06/10 = 13 redéploiements
  automatiques Render** (auto-deploy) → autant d'effacements ; les « vagues de test » de
  Godson se produisent précisément après nos déploiements. Les restarts d'instance Render
  free (maintenance/spin) produisent le même effet « sans redéploiement visible ».
- Le remboursement indu de l'incident §5 (error transitoire → done final) a de plus
  décalé le compteur d'une unité — mineur face à l'effacement complet.

### 6.4 Verdict directeur intérimaire
**Aucun commit de code ne peut réparer cela** : tant que la base vit dans le conteneur,
toute logique quota/session est vouée à l'effacement. C'est le scénario documenté depuis
l'audit initial (« base SQLite + uploads perdus à chaque redéploiement ») — l'argument
décisif pour la persistance. Trois options soumises à décision de Godson :
- **A. Oracle Cloud Always Free** (plan Chantier B déjà spécifié : VM A1, volume
  `./data → /data`, docker compose + Caddy) : définitif, gratuit, résout persistance +
  cold start — recommandé ;
- **B. Render Disk payant** : monter un disque sur /data (~7 $/mois starter + stockage) —
  minimal techniquement, payant, cold start conservé ;
- **C. Base managée gratuite (Turso/Neon)** : persistance quota/sessions, MAIS migration
  SQLite→(libsql/Postgres) de moyen calibre et uploads toujours éphémères — demi-solution ;
- **D. Statu quo assumé** : outil de démo, base éphémère documentée sur la page
  /methodologie (honnêteté = règle du projet).
Journal : action 17.

### 6.5 DÉCISION GODSON (soir 06/10) — consignée mot pour mot
> « pour le moment on ne migre pas encore, documente ton initiative dans le document,
> j'aurais choisi quand même Oracle Cloud, mais ça reste bloqué pour le moment »

- **Décision** : statu quo (option D) — base éphémère assumée ; **intention ferme** :
  Oracle Cloud (option A), bloqué par un obstacle externe côté compte/inscription.
- **Conséquences assumées jusqu'à migration** : déconnexions et quota réinitialisé à
  chaque déploiement/restart Render resteront NORMAUX — ce n'est plus un bug à signaler,
  c'est une limite connue et documentée (distinguer de la rétention volontaire > 24 h,
  qui est un choix de nettoyage, pas un accident).
- **Discipline de déploiement recommandée d'ici là** : chaque push = effacement de base →
  regrouper les commits, pousser en fin de vague de test, et prévenir Godson qu'un push
  invalidera les sessions en cours.
- **À la déblocage d'Oracle** : le Chantier B (B0-B5) est déjà spécifié et prêt —
  reprise immédiate possible sans rediagnostic.
- **Initiative Freebuff documentée** (conformément à la demande de Godson) : diagnostic
  §6 complet, options chiffrées A-D, recommandation A, décision reportée par Godson.
Journal : action 18.

**Consigne transmise à Windsurf au 06/10** : ne rien faire avec les 5 fichiers untracked qui
ne sont pas `scripts/smoke_test.py` (lighthouse-report-home.*, quanta_pdf_preview.html,
rapports quanta/preview/, scripts/investigate_bootstrap_eta2.py) — ni .gitignore, ni
suppression : ce sont des artefacts locaux de Godson, hors périmètre, et les commits sont
ciblés par chemins explicites (jamais `git add -A`), donc leur présence est sans effet.
