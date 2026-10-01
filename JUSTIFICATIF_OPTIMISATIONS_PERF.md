# JUSTIFICATIF DES OPTIMISATIONS DE PERFORMANCE — Freebuff (2026-10-01)

> Contexte : incident de budget worker (260 s) sur L2_tobit.dta. Après la déduplication
> ACM (commit `0406933`, −57 s réels confirmés en prod), le run `0090a4af-6b54-49f5-
> b1d1-14e610cc4037` a **encore dépassé les 260 s** : 63,0 s de pipeline + 135,7 s
> d'intents = **198,7 s avant l'appel LLM**, interprétation coupée à ~108 s. L'arbitrage
> exige donc d'attaquer les deux plus gros postes restants, sans changer un seul chiffre
> statistique. Ce document justifie les deux prototypes livrés sur la branche
> `feature/freebuff-perf-corr` (aucun branchement dans l'app sans mandat).

---

## 1. État des goulots après la dédup ACM (mesures prod, run 0090a4af)

| Poste | Durée prod | Statut |
|---|---|---|
| correlation_analysis (paires Python) | 27,7 s (45,6 s total) | P1-bis prêt (§2) |
| **ACM plots generation** | **55,3 s** (sur 61 s d'intent) | prototype prêt (§3) |
| descriptive_stats | 10,9-13,1 s | non profilé (3e poste) |
| interprétation LLM | non bornée (bug timeout prouvé : 44,8 s / 72,4 s mesurés) | arbitrage séparé |
| ACM fit MCA | 4,99 s | OK, ne pas toucher |
| normality + cleaning + diagnosis | ~6,5 s | OK |

Budget avant LLM après application de §2+§3 : **~139 s** (+ imports ~17 s) → interprétation
disposant de ~100-120 s au lieu de 61 s → incident closable.

## 2. P1-bis — corrélation vectorisée (commit `39c4299`)

**Problème** : boucle Python dans `compute.correlation_analysis` (~753-790) : pour chacune
des 1035 paires, `dropna()` ×2 + `index.intersection()` + indexation pandas + scipy —
27,7 s en prod.

**Cause de la lenteur** : coûts pandas par itération (≈28 ms/paire), pas scipy lui-même.

**Design** (`app/compute/correlation_fast.py`, isolé) :
- SANS NaN dans les colonnes : matrice `np.corrcoef` + formule t exacte des p-values
  (identique à l'implémentation interne de scipy, écart ~1e-12) ; rangs Spearman
  `rankdata(average)` calculés UNE fois par colonne au lieu de 1035 fois.
- AVEC NaN : repli boucle fidèle (dropna par paire + scipy par paire) — une vectorisation
  naïve serait mathématiquement FAUSSE (listwise deletion ≠ intersection par paire).
- Sorties : mêmes clés, mêmes arrondis (r 4 déc., p 5 déc.), mêmes champs
  decision/strength/direction, même tri des paires significatives.

**Preuves (A/B 5 régimes, script `scripts/ab_correlation_fast.py`)** :
- Δr = Δp = **0,00e+00 exactement** sur les 3 chemins vectorisés (pearson 990 paires,
  spearman, asymétrique) ; fallback NaN exact ; paires significatives identiques au tri.
- Gain : 1,6-1,9 s → 9-42 ms (**×44 à ×187**).
- `tests/test_correlation_fast.py` : 6/6.

## 3. Plots ACM — plafonnement par contribution (prototype `39c4299+`)

**Problème** : `TIMING - ACM plots generation: 55.301s` en prod (run 0090a4af) sur
61 s d'intent acm — le fit MCA ne prend que 4,99 s.

**Cause racine** (`compute.py` `_generate_acm_plot` ~1825-1845) : boucle par modalité —
`ax.scatter` + `ax.annotate` (les artistes les plus coûteux de matplotlib) + scan O(k)
de préfixe — sur CPU Render bridé (~16× plus lent que local, mesuré : 19 ms/modalité
local vs ~307 ms/modalité prod).

**Design** (`app/compute/acm_plot_fast.py`, isolé) :
- Sous le plafond (≤ 25 modalités) : rendu **byte-à-byte identique** à la prod ;
- Au-delà : top 25 modalités **par contribution** (dim1+dim2 du DataFrame prince,
  conversion `contributions_rank_map`) gardent scatter + étiquette ; le reste est
  dessiné en **une seule commande scatter vectorisée** (gris, sans étiquette) ;
- Titre suffixé `— top 25/180 modalités` (transparence visuelle) ;
- **Le payload JSON (modalities_coords) reste complet** : seuls les rendus changent.

**Preuves (A/B `scripts/ab_acm_plot.py`)** :
- Sous plafond : hash PNG **identique** prod vs fast (`78f5c3a9304f`) — parité byte-à-byte ;
- 180 modalités : prod 3,38 s vs fast 0,98 s (×3,5 local) — sur Render (×16), ~55 s → ~12 s ;
- `tests/test_acm_plot_fast.py` : 7/7 (incluant la parité bytes).

**Changement visuel assumé (validation produit requise)** : au-delà de 25 modalités, le
plan n'étiquette plus tout — un plan à 100+ étiquettes est de toute façon illisible ;
le choix top-N par contribution améliore la lisibilité ET la perf. Le cap (25) est
paramétrable.

## 4. Plan de branchement (mandat requis — compute.py est partagé)

1. `compute.correlation_analysis` : remplacer le bloc boucle (~753-790) par
   `compute_correlation_pairs(...)` + TIMING avant/après. ~10 lignes.
2. `compute.run_acm` : passer `contributions_rank_map(acm.column_contributions_)` à
   `build_acm_plot` en remplacement de `_generate_acm_plot` (+ paramètre max_labeled).
3. Re-test prod L2_tobit : attendre `TIMING - ACM plots generation < 15 s` et
   `correlation_analysis (total) < 25 s` ; pipeline attendu ~36 s.
4. Coordination : brancher UNIQUEMENT quand Windsurf n'édite pas compute.py (règle
   REPARTITION_OUTILS.md) et après validation du changement visuel par Godson.

## 5. Preuves brutes de référence

- Run prod 0090a4af (logs Render 01/10) : dédup ACM confirmée (association 0,3 s vs
  59,1 s ; ACM ×1), plots 55,3 s, timeout 260 s réitéré.
- A/B corrélation : 5/5 régimes identiques, gains 44-187×.
- A/B ACM plots : parité bytes sous plafond, ×3,5 local (×~16 attendu sur Render).
- pytest : 13/13 (6 corrélation + 7 ACM), 6,4 s.
