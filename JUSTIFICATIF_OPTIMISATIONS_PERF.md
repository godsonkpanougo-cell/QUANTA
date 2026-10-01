# JUSTIFICATIF DES OPTIMISATIONS DE PERFORMANCE — Freebuff (2026-10-02)

> Contexte : incident de budget worker (260 s) sur L2_tobit.dta. Après la déduplication
> ACM (commit `0406933`, −57 s réels confirmés en prod), le run `0090a4af-6b54-49f5-
> b1d1-14e610cc4037` a **encore dépassé les 260 s** : 63,0 s de pipeline + 135,7 s
> d'intents = **198,7 s avant l'appel LLM**, interprétation coupée à ~108 s.
> **Mise à jour 2026-10-02** : Godson a fourni le dataset réel `L2_tobit.dta` — les
> deux optimisations ont été validées **sur ces données réelles** puis **branchées**
> dans `compute.py` (mandat « travaille dessus jusqu'à corriger le problème »).

---

## 0. Preuves sur le dataset RÉEL (2026-10-02) — script `scripts/ab_l2_tobit_real.py`

Fichier : `L2_tobit.dta` (235 Ko, Stata), copié dans `data/uploads/` (**gitignore,
jamais commité — données utilisateur**). Chargé via le chemin prod exact
`load_and_diagnose` (upload_validation.py).

### Profil réel reproduit
| Mesure | Valeur |
|---|---|
| shape | **301 lignes × 121 colonnes** |
| numeric_cols | **52** → **1326 paires** (prod loggait 1035 sur une variante du fichier) |
| cat_cols | **68** |
| id_cols | 1 (`NUMID`, bien exclue des calculs) |
| reclassifiées numérique→catégoriel (garde-fou) | 15 |
| **Modalités ACM réelles** | **565** (et non 180 comme estimé le 01/10 !) |

### A/B corrélation (avant branchement) — boucle prod vs `correlation_fast`
| Méthode | Δr max | Δp max | Paires significatives | Top-5 scatter | Gain boucle |
|---|---|---|---|---|---|
| Spearman | **0.00e+00** | 0.00e+00 | **1025/1025 identiques** | identiques | 2,475 s → 0,051 s (**×48**) |
| Pearson | **0.00e+00** | 1.00e-05 (arrondi) | **843/843 identiques** | identiques | 2,412 s → 0,015 s (**×156**) |

### A/B ACM (avant branchement) — `_generate_acm_plot` prod vs `build_acm_plot`
- 565 modalités réelles : plots prod **11,075 s** vs fast **0,900 s** (**×12,3 local**)
- 565 × 19,6 ms local = 11,1 s ✓ cohérence interne ; prod 55,3 s ÷ 565 = 98 ms/modalité
  → **ratio Render/local réel ≈ 5× sur ce poste** (le ×16 du 01/10 était une borne
  haute fondée sur l'hypothèse erronée de 180 modalités).

### Budget projeté Render (pipeline statistique seul, extrapolation ×16 borne haute)
- Avant optimisations : **~265 s** (dépassement du cap 260 s reproduit ✓)
- Après optimisations : **~25 s** (gain ~240 s) — et avec le ratio réel 5× :
  plots ACM 55,3 → ~11 s, paires corrélation 27,7 → ~0,5-1 s, **gain total prod
  attendu ≈ 70-90 s** sur les 198,7 s avant LLM → interprétation dispose de
  ~130 s au lieu de ~60 s.

---

## 1. Branchement EFFECTUÉ (2026-10-02, branche `feature/freebuff-perf-corr`)

Mandat : « je t'envoie le fichier du tobit et tu travailles dessus jusqu'à corriger
le problème » — correction appliquée après preuves §0, en 3 points de compute.py :

1. **Imports** (compute.py ~L59) : `compute_correlation_pairs`,
   `build_acm_plot_fast`, `contributions_rank_map`, `_ACM_MAX_LABELED`.
2. **`correlation_analysis`** : la boucle paires (~753-790) est remplacée par
   `compute_correlation_pairs(df, numeric_cols, method)` + TIMING
   `correlation pairs (<path>)`. `p_matrix` vient du module (arrondi 5) avec
   diagonale reforée à 1.0 (non-régression payload : la prod initialisait
   `np.ones` et ne touchait que i<j). Heatmap et scatter top-5 inchangés.
3. **`run_acm`** : appelle `_build_acm_plot_fast(..., contributions_map=
   _contributions_rank_map(acm.column_contributions_))` — top 25 modalités
   étiquetées par contribution (dim1+dim2), reste en nuage gris vectorisé.
4. **`_generate_acm_plot`** : délègue à `acm_plot_fast` (signature inchangée —
   report_generator.py L3224 n'a pas besoin de modification). L'ancienne
   implémentation est conservée sous `_generate_acm_plot_legacy` pour les A/B.

### Non-régression du BRANCHEMENT (re-test §0 après branchement)
| Vérification | Résultat |
|---|---|
| Corrélation branchée vs réplique exacte de l'ANCIENNE boucle (spearman) | Δr=0, Δp=0, **1025/1025 paires sig identiques**, top-5 identiques, Δp_matrix hors diag 5e-06 |
| idem pearson | Δr=0, Δp=1e-05, **843/843 identiques**, top-5 identiques |
| ACM branchée : hash PNG plan | **`b5cf9bca5f7b` identique** prod (run_acm branché) vs fast direct |
| `TIMING - ACM plots generation` (run_acm branché, local) | **11,075 s → 1,160 s** (×9,5) |
| Payload JSON (pairs/p_matrix/modalities_coords) | inchangé (formats et arrondis prod) |

### Garde-fous
- `python -m pytest tests/` : **42/42 passed** (exclusions préexistantes hors
  périmètre : test_quota ×2 slowapi, test_orchestrator_compare_groups) ;
- `python -c "import main"` : **OK** (obligatoire avant push) ;
- CI GitHub : triggers `feature/**` — verte requise avant toute proposition de merge.

---

## 2. P1-bis — corrélation vectorisée (commit `39c4299`)

**Problème** : boucle Python dans `compute.correlation_analysis` (~753-790) : pour chacune
des paires, `dropna()` ×2 + `index.intersection()` + indexation pandas + scipy —
27,7 s en prod.

**Cause de la lenteur** : coûts pandas par itération (≈28 ms/paire), pas scipy lui-même.

**Design** (`app/compute/correlation_fast.py`) :
- SANS NaN dans les colonnes : matrice `np.corrcoef` + formule t exacte des p-values
  (identique à l'implémentation interne de scipy, écart ~1e-12) ; rangs Spearman
  `rankdata(average)` calculés UNE fois par colonne au lieu de 1326 fois.
- AVEC NaN : repli boucle fidèle (dropna par paire + scipy par paire) — une vectorisation
  naïve serait mathématiquement FAUSSE (listwise deletion ≠ intersection par paire).
- Sorties : mêmes clés, mêmes arrondis (r 4 déc., p 5 déc.), mêmes champs
  decision/strength/direction, même tri des paires significatives.

**Preuves synthétiques** : A/B 5 régimes (`scripts/ab_correlation_fast.py`) Δr=Δp=0
exact sur les chemins vectorisés, ×44-187 ; A/B données réelles L2_tobit §0 ;
`tests/test_correlation_fast.py` 6/6.

## 3. Plots ACM — plafonnement par contribution (`app/compute/acm_plot_fast.py`)

**Problème** : `TIMING - ACM plots generation: 55.301s` en prod (run 0090a4af) sur
61 s d'intent acm — le fit MCA ne prend que 4,99 s.

**Cause racine** : boucle par modalité — `ax.scatter` + `ax.annotate` (les artistes
les plus coûteux de matplotlib) + scan O(k) de préfixe — sur CPU Render bridé.
**Révisé le 02/10 avec le fichier réel : 565 modalités (pas 180), ratio Render/local
mesuré ≈ 5× (98 ms/modalité prod vs 19,6 ms local).**

**Design** :
- Sous le plafond (≤ 25 modalités) : rendu **byte-à-byte identique** à la prod ;
- Au-delà : top 25 modalités **par contribution** (dim1+dim2 du DataFrame prince,
  conversion `contributions_rank_map`) gardent scatter + étiquette ; le reste est
  dessiné en **une seule commande scatter vectorisée** (gris, sans étiquette) ;
- Titre suffixé `— top 25/565 modalités` (transparence visuelle) ;
- **Le payload JSON (modalities_coords) reste complet** : seuls les rendus changent.

**Preuves synthétiques** : parité bytes sous plafond (`78f5c3a9304f`, A/B synthétique
et `tests/test_acm_plot_fast.py` 7/7) ; données réelles §0 : ×12,3 local et **hash
identique après branchement** (`b5cf9bca5f7b`).

**Changement visuel assumé (validation produit Godson)** : au-delà de 25 modalités, le
plan n'étiquette plus tout — un plan à 565 étiquettes est de toute façon illisible ;
le choix top-N par contribution améliore la lisibilité ET la perf. Le cap (25) est
paramétrable.

## 4. Ce qui reste (coordination Windsurf / validation Godson)

1. Re-test prod L2_tobit après merge sur main : attendre
   `TIMING - ACM plots generation < 15 s` et
   `TIMING - correlation pairs (vectorized) < 2 s` ; budget avant LLM attendu
   ~120-130 s (vs 198,7 s).
2. Merge `feature/freebuff-perf-corr` → main à valider par le directeur/Windsurf
   (compute.py partagé — le diff est localisé : imports, ~15 lignes correlation,
   ~10 lignes run_acm, _generate_acm_plot délégante).
3. Validation produit du plan ACM plafonné (top 25/565) par Godson.
4. Bug timeout LLM (partie D, PROUVÉ : REQUEST_TIMEOUT_SECONDS=25 ne plafonne
   rien — 44,8 s et 72,4 s mesurés sous timeout=10) : correctif séparé, gelé en
   attente de l'arbitrage C.

## 5. Preuves brutes de référence

- Run prod 0090a4af (logs Render 01/10) : dédup ACM confirmée (association 0,3 s vs
  59,1 s ; ACM ×1), plots 55,3 s, timeout 260 s réitéré.
- A/B corrélation synthétique : 5/5 régimes identiques, gains 44-187×.
- A/B ACM plots synthétique : parité bytes sous plafond (180 modalités : 3,38 s vs 0,98 s).
- **A/B données réelles L2_tobit (02/10) : verdict global OK** — corrélation Δr=0
  (1025 sig spearman / 843 sig pearson, top-5 identiques), ACM 565 modalités
  ×12,3, hash plan identique après branchement, budget projeté ~265 s → ~25 s
  (borne haute ×16).
- pytest : **42/42** (13 tests dédiés P1-bis : 6 corrélation + 7 ACM) ; `import main` OK.
