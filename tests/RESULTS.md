# Résultats des tests manuels — pipeline `run_base_compute_pipeline`



Date : 2026-06-15 (validation finale)  

Commande : `python -m tests.test_<cas>` depuis la racine du repo  

Fichier testé : `app/compute/compute.py` (v2 final)



## Statut : VALIDÉ



`compute.py` est **définitivement validé** — prêt pour `test_selector.py`.



Dernier correctif : `_is_likely_id_column` distingue hints **forts** (`id`, `identifiant`, `uuid`, `guid`, `matricule` → nom seul suffit) et hints **ambigus** (`code` → exige ≥ 95 % d'unicité).



---



## Synthèse (8 datasets)



| Dataset | Script | Crash ? | `id` dans `id_cols` ? | Notes |

|---------|--------|---------|------------------------|-------|

| `clean.csv` | `test_clean` | Non | Oui | OK |

| `missing_15pct.csv` | `test_missing_15pct` | Non | Oui | OK |

| `outliers_extreme.csv` | `test_outliers_extreme` | Non | Oui | OK |

| `region_likert.csv` | `test_region_likert` | Non | Oui | Reclassification OK |

| `small_sample.csv` | `test_small_sample` | Non | Oui | `winsorisation_non_appliquee` |

| `large_sample.csv` | `test_large_sample` | Non | Oui | `Dataset transversal standard` |

| `with_duplicates.csv` | `test_with_duplicates` | Non | **Oui** (corrigé) | Plus de winsorisation/normalité sur `id` |

| `mixed_categorical.csv` | `test_mixed_categorical` | Non | Oui | OK |



**Aucun des 8 scripts ne plante.** Régression : `skipped` partout (comportement attendu).



---



## Validation finale — `with_duplicates.csv`



```

id_cols = ['id']

numeric_cols = ['age', 'salary']          # 'id' absent

audit_log outliers : age, salary uniquement  # pas 'id'

normality : age, salary uniquement           # pas 'id'

```



## Non-régression — `region_likert.csv`



```

id_cols = ['id']

cat_cols = ['code_region', 'satisfaction']

reclassified_as_categorical = { code_region: n_unique=5, satisfaction: n_unique=5 }

```



---



## Correctifs v2 — historique



| Fix | Description | Statut |

|-----|-------------|--------|

| #1 | Colonne `id` exclue des calculs continus | **Validé** (y compris datasets avec doublons) |

| #2 | Faux « Série temporelle » sur `years_exp` | **Validé** |

| #3 | Garde-fou catégoriel sur petit n (seuil 10 + `n >= 2*n_unique`) | **Validé** |

| #4 | Winsorisation désactivée si n < 30 | **Validé** |

| #5 | Hints forts vs ambigus dans `_is_likely_id_column` | **Validé** |



---



## Erreurs (exceptions)



Aucune exception sur les 8 scripts.



---



## Relancer les tests compute



```bash

cd QUANTA

python -m tests.test_with_duplicates   # validation finale du fix id+doublons

python -m tests.test_region_likert     # non-régression reclassification

python -m tests.test_clean

python -m tests.test_missing_15pct

python -m tests.test_outliers_extreme

python -m tests.test_small_sample

python -m tests.test_large_sample

python -m tests.test_mixed_categorical

```



---



# Résultats des tests manuels — sélecteur `select_and_run_test`



Date : 2026-06-16 (validation finale)  

Commande : `python -m tests.test_selector_<cas>` depuis la racine du repo  

Fichier testé : `app/compute/test_selector.py` (v1 final)



## Statut : VALIDÉ — DÉFINITIVEMENT CLOS



`test_selector.py` est **définitivement validé** — prêt pour `orchestrator.py`.

Les 6 scripts passent sans exception. `select_and_run_test()` garantit nativement la sérialisation JSON : `validation_issues` est converti en `list[dict]` et les types numpy sont normalisés avant retour (wrapper `_json_safe` autour de `_select_and_run_test_impl`).



---



## Synthèse (6 scénarios)



| Scénario | Script | Dataset | Test choisi | Crash ? | JSON OK ? |

|----------|--------|---------|-------------|---------|-----------|

| 2 groupes, variable normale | `test_selector_2groups_normal` | `ts_2groups_normal.csv` | t-test de Student (variances égales) | Non | Oui |

| 2 groupes, variable non-normale | `test_selector_2groups_nonnormal` | `ts_2groups_nonnormal.csv` | Mann-Whitney U | Non | Oui |

| 3+ groupes (normal) | `test_selector_multigroup` | `mixed_categorical.csv` | ANOVA à un facteur | Non | Oui |

| 3+ groupes (non-normal) | `test_selector_multigroup` | `mixed_categorical.csv` | Kruskal-Wallis | Non | Oui |

| Association Chi-deux | `test_selector_association` | `mixed_categorical.csv` | Chi-deux d'indépendance | Non | Oui |

| Association Fisher 2x2 | `test_selector_association` | `ts_assoc_fisher.csv` | Fisher exact | Non | Oui |

| Régression logistique | `test_selector_logistic` | `ts_logistic_binary.csv` | Régression logistique binaire | Non | Oui |

| Cas piège (colonne absente) | `test_selector_trap` | `mixed_categorical.csv` | `descriptive_only` + `validation_issues` | Non | Oui |

| Cas piège (colonne `id`) | `test_selector_trap` | `mixed_categorical.csv` | `descriptive_only` + `validation_issues` | Non | Oui |



---



## Détail par scénario



### 1 — Comparaison 2 groupes, variable normale (`ts_2groups_normal.csv`)



```

action_executed = compare_groups_2

test            = t-test de Student (variances égales)

Levene p        = 0.8981 (variances égales)

p_value         = 1e-06

```



### 2 — Comparaison 2 groupes, variable non-normale (`ts_2groups_nonnormal.csv`)



```

action_executed = compare_groups_2

test            = Mann-Whitney U (non-paramétrique)

normalité       = rejetée (delai ~ exponentiel)

p_value         = 0.0

```



### 3 — Comparaison 3+ groupes (`mixed_categorical.csv`)



**ANOVA (salaire ~ department)**



```

action_executed = compare_groups_multi

test            = ANOVA à un facteur (variances égales)

p_value         = 0.858154

posthoc         = None (ANOVA non significative — comportement attendu)

```



**Kruskal-Wallis (age ~ department)**



```

action_executed = compare_groups_multi

test            = Kruskal-Wallis (non-paramétrique)

p_value         = 0.321681

posthoc         = None (Kruskal non significatif — comportement attendu)

```



> Note : Tukey HSD et Dunn ne sont déclenchés que si p < 0.05. Sur ces données, les comparaisons globales ne sont pas significatives — le post-hoc reste `None`, ce qui est statistiquement correct.



### 4 — Association catégorielle



**Chi-deux (genre × department)**



```

action_executed     = association

test                = Chi-deux d'indépendance

min_expected_count  = 7.80 (≥ 5)

p_value             = 0.285917

```



**Fisher exact (exposition × maladie, table 2×2)**



```

action_executed     = association

test                = Fisher exact (table 2x2, effectifs attendus < 5)

min_expected_count  = 4.50 (< 5)

p_value             = 0.069779

```



### 5 — Régression logistique (`ts_logistic_binary.csv`)



```

action_executed = regression_logistic

target          = diabete (Oui/Non)

predictors      = [age, imc]

n_obs           = 200

pseudo_R2       = 0.1646

```



### 6 — Cas piège (validation intention)



**Colonne inexistante (`revenu_annuel`)**



```

action_executed    = descriptive_only

validation_issues  = 1 (target_col halluciné)

result.status      = skipped

audit_log          = validation_intention + fallback_action

```



**Colonne identifiant (`id`)**



```

action_executed    = descriptive_only

validation_issues  = 1 (id dans id_cols)

result.status      = skipped

```



Aucun crash, aucun choix silencieux.



---



## Sérialisation JSON



**Résolu côté source (v1 final).** `select_and_run_test()` applique `_json_safe()` avant tout retour : `ValidationIssue` → `dict`, numpy scalars → types natifs Python. L'orchestrateur et l'API FastAPI peuvent appeler `json.dumps(result)` directement, sans helper de conversion local. Les tests vérifient cette garantie via `json.dumps(output)` brut dans `tests/_print_selector.py`.



---



## Comportements notables (non bloquants)



| Observation | Impact |

|-------------|--------|

| Post-hoc absent quand p ≥ 0.05 | Comportement attendu (Tukey/Dunn conditionnels) |

| Welch ANOVA utilise `f_oneway` en approximation | Documenté dans le code ; Games-Howell en post-hoc si Levene significatif |



---



## Datasets dédiés créés pour test_selector



| Fichier | Usage |

|---------|-------|

| `ts_2groups_normal.csv` | 2 groupes A/B, score normal |

| `ts_2groups_nonnormal.csv` | 2 groupes, délai exponentiel (non-normal) |

| `ts_logistic_binary.csv` | Cible binaire diabète + prédicteurs age/imc |

| `ts_assoc_fisher.csv` | Table 2×2 petits effectifs pour Fisher exact |



---



## Relancer les tests test_selector



```bash

cd QUANTA

python -m tests.test_selector_2groups_normal

python -m tests.test_selector_2groups_nonnormal

python -m tests.test_selector_multigroup

python -m tests.test_selector_association

python -m tests.test_selector_logistic

python -m tests.test_selector_trap

```



---



# Résultats des tests manuels — orchestrateur `run_full_analysis`



Date : 2026-06-17  

Commande : `python -m tests.test_orchestrator_<cas>` depuis la racine du repo  

Fichier testé : `app/orchestrator.py` (v2 plafond de niveau confiance)



## Statut : VALIDÉ



Les 6 scripts passent sans exception. `run_full_analysis()` assemble compute + test_selector, fusionne les `audit_log`, résout les délégations OLS/corrélation, calcule le score de confiance, et garantit la sérialisation JSON via `_json_safe()` final.



---



## Synthèse (6 scénarios)



| Scénario | Script | Dataset | Résultat clé | Crash ? | JSON OK ? |

|----------|--------|---------|--------------|---------|-----------|

| Pipeline compare_groups | `test_orchestrator_compare_groups` | `ts_2groups_normal.csv` | Student, score=100 | Non | Oui |

| Délégation OLS | `test_orchestrator_delegation_ols` | `clean.csv` | `delegation_ols` + réutilisation R² | Non | Oui |

| Délégation corrélation | `test_orchestrator_delegation_correlation` | `clean.csv` | `delegation_correlation` + r réutilisé | Non | Oui |

| Score confiance dégradé + plafonds n | `test_orchestrator_confidence_degraded` | `clean.csv` vs `small_sample.csv` + `clean_n95.csv` | 98.0 → 94.0, n=25 plafonné Faible, n=95 plafonné Modéré | Non | Oui |

| Cas piège bout-en-bout | `test_orchestrator_trap` | `mixed_categorical.csv` | `descriptive_only` + issues | Non | Oui |

| Fichier invalide | `test_orchestrator_corrupt_file` | `corrupt.xyz` | `status=failed`, `error` présent | Non | Oui |



---



## Détail par scénario



### 1 — Pipeline standard (`ts_2groups_normal.csv`)



```

status            = ok

action_executed   = compare_groups_2

test              = t-test de Student (variances égales)

confidence_score  = 100.0 (Élevé)

audit_log         = [outliers, synthese, selection_test]

```



### 2 — Délégation OLS (`clean.csv`, target=income)



```

action_executed   = regression_ols

inference.R2      = 0.0297 (identique à regression_base)

audit_log         = ... + delegation_ols (reutilisation_resultat_existant)

```



### 3 — Délégation corrélation (`clean.csv`, age × income)



```

action_executed   = correlation

inference.r       = -0.0553 (identique à correlation_base.pairs)

audit_log         = ... + delegation_correlation (reutilisation_resultat_existant)

```



### 4 — Score de confiance dégradé



```

clean.csv (n=100)       : score_global = 98.0, niveau Élevé, niveau_brut_avant_plafond = None

small_sample.csv (n=25) : score_global = 94.0, niveau Faible, niveau_brut_avant_plafond = Élevé

clean_n95.csv (n=95)    : score_global = 97.8, niveau Modéré, niveau_brut_avant_plafond = Élevé

points_de_vigilance     : mention du petit n + mention explicite du plafonnement appliqué

```



> Nouveau comportement validé : le score numérique pondéré reste transparent (`score_global` inchangé), mais le `niveau` affiché applique désormais un plafond indépendant de la moyenne pour éviter un niveau trop optimiste sur petits échantillons.



### 5 — Cas piège bout-en-bout



Colonne inexistante (`revenu_annuel`) et identifiant (`id`) : `action_executed=descriptive_only`, `validation_issues` documentées, `inference.status=skipped`, aucun crash.



### 6 — Fichier invalide



Extension non supportée (`corrupt.xyz`) : `{"status": "failed", "error": "Format non supporté : xyz"}` sans exception levée.



> Note : un fichier `.csv` avec contenu garbage peut être parsé par pandas sans erreur — le test utilise une extension non supportée pour garantir l'échec contrôlé.



---



## Sérialisation JSON



Garantie native dans `orchestrator.py` via `_json_safe()` sur la réponse assemblée finale. Les tests appellent `json.dumps(result)` directement (helper `tests/_print_orchestrator.py`).



---



## Relancer les tests orchestrator



```bash

cd QUANTA

python -m tests.test_orchestrator_compare_groups

python -m tests.test_orchestrator_delegation_ols

python -m tests.test_orchestrator_delegation_correlation

python -m tests.test_orchestrator_confidence_degraded

python -m tests.test_orchestrator_trap

python -m tests.test_orchestrator_corrupt_file

```


