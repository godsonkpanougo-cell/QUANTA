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
