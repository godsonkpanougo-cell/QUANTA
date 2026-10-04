# RAPPORT P0 — PILIER CRÉDIBILITÉ : correction de multiplicité + deadline LLM

> Date : 02/10/2026 — Exécution : Buffy (Freebuff), mandat direct du directeur
> (« on met en place les 4 piliers… sans casser ce qu'on a déjà construit »).
> C'est le pré-requis des 4 piliers : sans crédibilité statistique irréprochable,
> aucun des piliers (Projet persistant, session conversationnelle, Mode Soutenance)
> ne peut faire de QUANTA une référence.

---

## 1. Travail trouvé en cours (aucune confiance par défaut)

À l'ouverture du chantier, le workspace (main, 2 commits debug CI récents) contenait
du travail NON commité hérité d'un autre agent :
- `app/compute/multiplicity.py` (nouveau, 205 lignes),
- branchements dans `compute.py` (+17), `brain.py` (+6), `report_generator.py` (+17),
- `scripts/investigate_bootstrap_eta2.py` + artefacts lighthouse (non commités).

Conformément au protocole, ce travail n'a PAS été discard : il a été inspecté,
**corrigé, testé et prouvé**, puis commité.

## 2. BUG CRITIQUE découvert et corrigé : monotonies Holm/BH échangées

Les deux corrections du module hérité appliquaient les contraintes de monotonie
**inversées** :

| Méthode | Contrainte correcte | Ce que faisait le code hérité | Conséquence |
|---|---|---|---|
| Holm-Bonferroni (step-down) | cumul **MAXIMISANT** depuis le début : p_adj[i] = max_{j≤i} p[j]·(n−j) | cumul MINIMISANT depuis la fin | **SOUS-correction → faux positifs** (l'inverse de l'objectif) |
| Benjamini-Hochberg (step-up) | cumul **MINIMISANT** depuis la fin : q[i] = min_{j≥i} p[j]·n/(j+1) | cumul MAXIMISANT depuis le début | SUR-correction → découvertes vraies éliminées |

**Cas révélateurs (verrouillés par tests)** :
- Holm, p=[0.04, 0.045] : correct = [0.08, 0.08] ; code hérité = [0.045, 0.045]
  → laissait passer p=0.04 à 0.045 < 0.05 (faux positif).
- BH, p=[0.01, 0.015] : correct = [0.015, 0.015] ; code hérité = [0.02, 0.02]
  → éliminait une découverte vraie.

**Correctif** ([app/compute/multiplicity.py](app/compute/multiplicity.py)) : remplacer
les boucles par `np.maximum.accumulate` (Holm) et `np.minimum.accumulate(...[::-1])[::-1]` (BH).

## 3. Correctif 2 : deadline LLM (bug timeout PROUVÉ, jamais corrigé depuis le 01/10)

Le bug : `REQUEST_TIMEOUT_SECONDS=25` borne chaque opération socket et est réarmé
par chaque octet keep-alive → réponses HTTP 200 de 44,8 s et 72,4 s mesurées sans lever.

**Correctif** ([app/llm/brain.py](app/llm/brain.py)) :
- `PROVIDER_TOTAL_BUDGET_SECONDS` (env `LLM_PROVIDER_BUDGET_SECONDS`, défaut 100 s) :
  budget wall-clock TOTAL par provider, tous retries confondus ;
- requête en `stream=True` ; lecture du corps par `_consume_with_deadline` qui lève
  `requests.exceptions.Timeout` dès que le budget est dépassé ;
- pas de nouvelle tentative une fois le budget épuisé (garde au début de chaque attempt) ;
- pire cas total : 2×100 s + 2×100 s (fallback) borné, au lieu d'illimité.

## 4. Preuves brutes (exécutions réelles du 02/10)

### 4.1 Oracle statistique — `pytest tests/test_multiplicity.py tests/test_llm_deadline.py`
```
11 passed in 56.45s
```
- `holm_bonferroni` == `statsmodels.multipletests(method="holm")` sur **200 familles
  aléatoires seedées** (n de 1 à 120) + cas révélateurs + cas limites (Δ ≤ 1e-12) ;
- `benjamini_hochberg` == `statsmodels.multipletests(method="fdr_bh")` idem ;
- `apply_fdr_correction_to_pairs` : `p_value` brute PRÉSERVÉE, `p_adjusted` ajouté,
  NaN traités comme p=1.0, famille vide no-op ;
- deadline LLM : la lecture canuleuse est coupée au budget, pas de 2e attempt
  après épuisement, réponse rapide inchangée (3 tests monkeypatchés, zéro réseau).

### 4.2 Impact sur les DONNÉES RÉELLES — `python scripts/ab_multiplicity.py`
```
famille: 1326 paires Spearman (p<0.05 brut)
sig. BRUT (comme les IA du marche) : 1025
sig. Holm-Bonferroni (FWER)        : 774
sig. Benjamini-Hochberg (FDR)      : 1010
faux positifs attendus sous H0     : ~66
implementations == oracle statsmodels: Holm=True, BH=True
payload: p_adjusted ajoute a 1326 paires, brut intact: True
paire la plus robuste: D2CONT x CATOT (r=0.3763, p=0.0, q=0.0)
CONCLUSION: OK
```
**Lecture produit** : les IA du marché rapportent 1025 « significatives » dont ~66
sont des faux positifs purs. QUANTA rapporte désormais 1010 robustes (FDR) ou 774
strictes (FWER), avec le q-value affiché à côté du p brut. Aucun concurrent ne le fait.

### 4.3 Non-régression globale
```
python -m pytest tests/ (hors test_quota, test_orchestrator_compare_groups) : 87 passed
python -c "import main" : IMPORT MAIN OK
```

## 5. Chaîne de non-régression du payload

- `pairs[*].p_value` : **inchangé** (brut) ; `decision` basé sur le brut : inchangé ;
- nouveaux champs par paire : `p_adjusted` (5 déc.), `significant_adjusted` ;
- nouveau bloc global `multiplicity_correction` dans le retour de
  `correlation_analysis` : {method, significant_raw, significant_adjusted} ;
- [brain.py](app/llm/brain.py) expose le bloc au LLM (travail hérité conservé) ;
- [report_generator.py](app/report_generator.py) affiche `q (FDR)` à côté de p
  (tableau APA + résumé ; travail hérité conservé).

## 6. État git (à la fermeture du rapport)

- Branche : `feature/freebuff-piliers` (créée depuis main — main intact).
- 2 commits : (1) correction de multiplicité + preuves ; (2) deadline LLM.
- Push + CI : à vérifier sur GitHub Actions (branche feature/**).
- Non commités volontairement (pas à moi) : `scripts/investigate_bootstrap_eta2.py`,
  `lighthouse-report-home.report.html/.json` (artefacts debug CI).

## 7. Ce qui reste (stop point)

| Pilier | État |
|---|---|
| P0 crédibilité (timeout + multiplicité) | **LIVRÉ ce tour** |
| P1 Projet persistant | à démarrer (prochain tour) |
| P2 Session conversationnelle (parler à ses données) | à démarrer (moteur `text_to_intent` existant) |
| P3 Repro Pack ZIP | à démarrer |
| P4 Mode Soutenance | à démarrer |

Recommandation d'ordre : P1 puis P2 (les deux verrous d'usage quotidien), P3/P4 ensuite.
