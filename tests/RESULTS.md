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



---



# Résultats des tests manuels — couche LLM `brain.py`



Date : 2026-06-17  

Emplacement : `app/llm/brain.py`  

Commande : `python -m tests.test_brain_<cas>` depuis la racine du repo  

Configuration : `.env` (template `.env.example`) — clés non commitées



## Statut : VALIDÉ — DÉFINITIVEMENT CLOS (live Groq + repli sans clé)



Les 6 scripts passent sans exception. Tests live exécutés avec `PRIMARY_MODEL=llama-3.3-70b-versatile` (Groq). JSON exploitable en pratique sur `text_to_intent` et `generate_interpretation`. Repli sans clé toujours fonctionnel.



---



## Synthèse (6 scénarios)



| Scénario | Script | Clé API ? | Résultat clé | Crash ? | JSON OK ? |

|----------|--------|-----------|--------------|---------|-----------|

| text_to_intent live | `test_brain_text_to_intent_live` | Oui (Groq) | `compare_groups`, `income` × `code_region` | Non | Oui |

| text_to_intent sans clé | `test_brain_text_to_intent_no_key` | Non | `descriptive_only` | Non | Oui |

| generate_interpretation live | `test_brain_generate_interpretation_live` | Oui (Groq) | 3 niveaux OK, régressions déterministes OK | Non | Oui |

| generate_interpretation sans clé | `test_brain_generate_interpretation_no_key` | Non | `llm_available=false`, `raw_analysis.status=ok` | Non | Oui |

| analyze_with_brain E2E | `test_brain_analyze_e2e` | Oui (Groq) | ANOVA multi-régions + `formats_anormaux_detectes` (régression 025,02) | Non | Oui |

| json.dumps tous chemins | `test_brain_json_serializable` | Non | 3 payloads sérialisables | Non | Oui |



---



## Détail par scénario



### 1 — text_to_intent live (`region_likert.csv`)



```

Query   : "comparer le revenu entre régions"

action  = compare_groups

target  = income

group   = code_region

```



Qualité : **excellente**. Mapping sémantique correct (revenu → `income`, régions → `code_region`), pas d'hallucination de colonne. JSON strict exploitable du premier coup.



### 2 — text_to_intent sans clé



```

action = descriptive_only

target_col = None, group_col = None

```



Comportement attendu : échec LLM silencieux, jamais de crash.



### 3 — generate_interpretation live (`ts_2groups_normal.csv`)



```

llm_available = True

test sous-jacent = t-test de Student (variances égales)

niveau_technique / analytique / decisionnel = tous non vides

nombres_suspects_detectes = [] ou vraie hallucination live (ex. t=-7,3337 vs -5,2792 réel)

formats_anormaux_detectes = [] (sur cette exécution)

```



Correctifs anti-hallucination cumulés :

- **v2** : notation scientifique + tolérance float ±1% — faux positifs `-06,` résolus
- **v3** : champ séparé `formats_anormaux_detectes` pour zéro de tête suspect (`025,02`) — distinct des `nombres_suspects_detectes`

Régressions déterministes validées : `1e-06` non flaggé ; `-5,2792` (stat réelle, virgule FR) non suspect ; `-7,3337` reste suspect car absent des sources (vraie incohérence LLM possible en live, pas un faux positif de regex).



### 4 — generate_interpretation sans clé



```

llm_available = False

raw_analysis.status = ok

confidence_score présent dans raw_analysis

```



Règle d'or respectée : le pipeline statistique reste accessible sans interprétation textuelle.



### 5 — analyze_with_brain E2E (`region_likert.csv`)



```

intent.action_executed (orchestrator) = compare_groups_multi

test = ANOVA à un facteur (variances égales)

interpretation.llm_available = True

nombres_suspects_detectes = [] (sortie live variable)

formats_anormaux_detectes = [] (sortie live variable)

Régression unitaire : `025,02` → `formats_anormaux_detectes` (pas `nombres_suspects_detectes`)

```



Investigation `025,02` : **pas un faux positif regex** — valeur 25,02 absente des sources ANOVA (`eta_squared` réel ≈ 0.0814). Le zéro de tête signale une corruption de format (fusion probable). Classé désormais en `formats_anormaux_detectes` avec avertissement prioritaire « format anormal / fusion accidentelle ».



### 6 — Sérialisation JSON



`json.dumps()` OK sur intent, interpretation (repli), et résultat complet `analyze_with_brain`.



---



## Observations (non corrigées)



| Point | Note |

|-------|------|

| Qualité `text_to_intent` (Groq) | Très bonne sur le cas testé — JSON strict, colonnes validées, mapping sémantique correct |

| Qualité `generate_interpretation` (Groq) | Contenu statistiquement raisonnable sur t-test et ANOVA ; reformulations lisibles aux 3 niveaux |

| Faux positifs regex (t-test) | **Résolus** — `-06,` (notation scientifique) ne remonte plus |

| `-7,3337` en live | **Vraie hallucination LLM** possible (stat réelle = -5,2792) — correctement signalée dans `nombres_suspects_detectes`, pas un faux positif |

| `025,02` (ANOVA) | **Résolu** — classé en `formats_anormaux_detectes` (zéro de tête), avertissement dédié ; régression unitaire dans `test_brain_analyze_e2e` |

| Structure `anti_hallucination_check` | Deux listes : `nombres_suspects_detectes` + `formats_anormaux_detectes` |

| `satisfaction` reclassée catégorielle | Sur `region_likert.csv`, compute place `satisfaction` en `cat_cols` (Likert) — le LLM a correctement ignoré cette colonne pour « revenu entre régions » |

| Repli sans clé | Toujours fonctionnel (`descriptive_only` / `llm_available=false`) — règle d'or respectée |



---



## Relancer les tests brain



```bash

cd QUANTA

# Renseigner PRIMARY_API_KEY dans .env avant les tests live

python -m tests.test_brain_text_to_intent_live

python -m tests.test_brain_text_to_intent_no_key

python -m tests.test_brain_generate_interpretation_live

python -m tests.test_brain_generate_interpretation_no_key

python -m tests.test_brain_analyze_e2e

python -m tests.test_brain_json_serializable

```



---



# Résultats des tests manuels — API FastAPI `main.py`



Date : 2026-06-18  

Emplacement : `main.py` (racine du repo — `uvicorn main:app`)  

Commande : `python -m tests.test_api_<cas>` depuis la racine du repo  

Client de test : `fastapi.testclient.TestClient` (pas de serveur réseau requis)



## Statut : VALIDÉ



Les 9 scripts passent sans exception. Serveur local vérifié : `/docs` (Swagger) et `/openapi.json` exposent les 5 endpoints attendus.



---



## Synthèse (9 scénarios)



| Scénario | Script | Résultat clé | Crash ? |

|----------|--------|--------------|---------|

| Health check | `test_api_health` | `status=ok`, `service=quanta-api` | Non |

| Flux upload → analyze → status | `test_api_upload_analyze_flow` | `status=done`, pipeline OK | Non |

| Upload invalide | `test_api_upload_invalid` | HTTP 400, message lisible | Non |

| Analyze file_id absent | `test_api_analyze_file_not_found` | HTTP 404 | Non |

| Analyze query vide | `test_api_analyze_empty_query` | HTTP 422 (`""` et `"   "`) | Non |

| Status analysis_id absent | `test_api_status_not_found` | HTTP 404 | Non |

| Upload > 10 Mo | `test_api_upload_too_large` | HTTP 413 | Non |

| Flux complet live (Groq) | `test_api_full_flow_live` | intent + interprétation via API | Non |

| OpenAPI + /docs | `test_api_openapi_docs` | 5 endpoints documentés | Non |



---



## Détail



### Endpoints exposés



```

GET  /health

POST /upload

POST /analyze

GET  /status/{analysis_id}

GET  /history

```



### Flux standard (`clean.csv`)



```

POST /upload        -> file_id + colonnes

POST /analyze       -> analysis_id (pending)

GET  /status/{id}   -> done + result (intent, analysis, interpretation)

GET  /history       -> count >= 1

```



BackgroundTasks : exécutées de façon synchrone par `TestClient` — pas de polling nécessaire dans les tests.



### Flux live Groq (`region_likert.csv`)



```

query = "comparer le revenu entre régions"

intent.action = compare_groups

analysis.status = ok

interpretation.llm_available = true

3 niveaux d'interprétation non vides

```



### Erreurs HTTP



| Cas | Code | Détail |

|-----|------|--------|

| Extension `.xyz` | 400 | `Impossible de lire le fichier : Format non supporté : xyz` |

| `file_id` inconnu | 404 | message explicite |

| `query` vide / blanc | 422 | validation Pydantic |

| `analysis_id` inconnu | 404 | message explicite |

| Fichier > 10 Mo | 413 | `Fichier trop volumineux` |



### Swagger / OpenAPI



```

uvicorn main:app --reload

# http://127.0.0.1:8000/docs

```



Vérifié : `/docs` → 200, `/openapi.json` liste les 5 paths.



---



## Observations (non bloquantes)



| Point | Note |

|-------|------|

| Emplacement `main.py` | Racine du repo pour compatibilité Render/Railway (`uvicorn main:app`) |

| Stockage | SQLite (`quanta.db`) + fichiers temp (`quanta_uploads/`) — métadonnées et analyses survivent au redémarrage (J21) |

| Starlette deprecation | Warning `httpx` vs `httpx2` dans TestClient — sans impact fonctionnel |

| CORS | `CORS_ALLOWED_ORIGINS` (défaut `http://localhost:3000`) |



---



## Relancer les tests API



```bash

cd QUANTA

python -m tests.test_api_health

python -m tests.test_api_upload_analyze_flow

python -m tests.test_api_upload_invalid

python -m tests.test_api_analyze_file_not_found

python -m tests.test_api_analyze_empty_query

python -m tests.test_api_status_not_found

python -m tests.test_api_upload_too_large

python -m tests.test_api_full_flow_live

python -m tests.test_api_openapi_docs

```



---



# BILAN J24 — Non-régression massif API HTTP (Mois 1)



Date : 2026-06-18  

Script : `tests/test_regression_j24.py`  

Client : `requests` (HTTP réel, pas `TestClient`)  

Prérequis serveur : `uvicorn main:app --reload --port 8000`  

Commande : `python -m tests.test_regression_j24`



## Statut : VALIDÉ — MOIS 1 CLOS



**12/12 datasets passent** sans erreur bloquante. Pipeline complet accessible via l'API : upload → analyze → poll status → résultat JSON sérialisable.



Configuration exécution : clé Groq configurée (`llm_available=True` sur les 12 cas). Durée totale ~2 min.



---



## Synthèse (12 datasets)



| Dataset | Status | Action exécutée | Score confiance | LLM dispo | JSON OK |

|---------|--------|-----------------|-----------------|-----------|---------|

| `clean.csv` | done | descriptive_only | 98.0 | True | Oui |

| `missing_15pct.csv` | done | descriptive_only | 90.5 | True | Oui |

| `outliers_extreme.csv` | done | descriptive_only | 100.0 | True | Oui |

| `region_likert.csv` | done | compare_groups_multi | 100.0 | True | Oui |

| `small_sample.csv` | done | descriptive_only | 94.0 | True | Oui |

| `large_sample.csv` | done | regression_ols | 100.0 | True | Oui |

| `with_duplicates.csv` | done | descriptive_only | 92.8 | True | Oui |

| `mixed_categorical.csv` | done | compare_groups_multi | 98.0 | True | Oui |

| `ts_2groups_normal.csv` | done | compare_groups_2 | 100.0 | True | Oui |

| `ts_2groups_nonnormal.csv` | done | compare_groups_2 | 96.8 | True | Oui |

| `ts_logistic_binary.csv` | done | regression_logistic | 100.0 | True | Oui |

| `ts_assoc_fisher.csv` | done | descriptive_only | 94.0 | True | Oui |



---



## Critères vérifiés (par dataset)



- `GET /status` → `status == "done"` (pas `"error"`)

- `result.analysis.status == "ok"`

- `result.analysis.inference.action_executed != None`

- `result.analysis.confidence_score.score_global > 0`

- `result.interpretation.llm_available` booléen (True ou False acceptables)

- `json.dumps(result)` sans exception



---



## Observations (non bloquantes)



| Point | Note |

|-------|------|

| Intent LLM variable | Sur `clean.csv`, `ts_assoc_fisher.csv` et quelques requêtes descriptives, le LLM retombe sur `descriptive_only` au lieu de `correlation` / `association` — le pipeline reste `status=ok` avec stats brutes accessibles |

| `ts_assoc_fisher.csv` | Requête « association exposition-maladie » → `descriptive_only` en live (intent non mappé) ; pas d'échec car critères J24 = robustesse API, pas action exacte |

| Port 8000 occupé | Si un ancien processus écoute sur 8000 avec erreurs 500, relancer `uvicorn` ou utiliser `QUANTA_API_URL=http://127.0.0.1:8001` |

| Encodage Windows | Le script force `stdout` en UTF-8 pour afficher le message final avec emoji |



---



## Relancer le bilan J24



```bash

cd QUANTA

# Terminal 1 — serveur

uvicorn main:app --reload --port 8000



# Terminal 2 — régression

python -m tests.test_regression_j24

```



Variable optionnelle : `QUANTA_API_URL` (défaut `http://127.0.0.1:8000`).



---



# Migration SQLite (J21) — persistance API



Date : 2026-06-20  

Emplacement : `db.py` (racine) + `main.py` (dicts remplacés par appels SQLite)  

Commande tests API : `python -m tests.test_api_<cas>` (9 scripts, inchangés)  

Commande test critique : `python -m tests.test_persistence`



## Statut : VALIDÉ



La migration remplace le stockage en mémoire (`uploads` / `analyses`) par SQLite (`quanta.db`, configurable via `QUANTA_DB_PATH`). Les 9 scripts API passent sans régression. Le test `test_persistence.py` arrête et relance un vrai process `uvicorn` : `GET /status/{analysis_id}` et `GET /history` retrouvent l'analyse après redémarrage.



---



## Synthèse



| Vérification | Script / mécanisme | Résultat |

|--------------|-------------------|----------|

| Non-régression API (9 cas) | `test_api_*` via `TestClient` | 9/9 OK |

| Persistance après redémarrage process | `test_persistence` (uvicorn kill + relance) | OK |

| Fichier généré ignoré par git | `quanta.db` dans `.gitignore` | OK |



---



## Détail — test_persistence



```

[1] uvicorn process 1 (QUANTA_DB_PATH = fichier temp)

[2] POST /upload (clean.csv) -> POST /analyze -> poll GET /status -> done

[3] kill process 1

[4] uvicorn process 2 (même QUANTA_DB_PATH)

    GET /status/{analysis_id} -> 200, status=done, result présent

    GET /history -> analysis_id listé, count >= 1

```



Port dédié : `8765` (override : `QUANTA_PERSISTENCE_PORT`). Pas de `TestClient` — validation du vrai problème (perte d'état au redémarrage serveur).



---



## Observations



| Point | Note |

|-------|------|

| Thread-safety | Verrou global + `check_same_thread=False` pour BackgroundTasks |

| Fichiers uploadés | Toujours sur disque (`quanta_uploads/`) ; seules métadonnées + analyses en base |

| Cleanup shutdown | Retiré (contradictoire avec persistance) |

| Tests in-process | `reset_api_state()` vide les tables SQLite via `db.clear_all()` |



---



## Relancer



```bash

cd QUANTA



# 9 tests API (TestClient)

python -m tests.test_api_health

python -m tests.test_api_upload_analyze_flow

python -m tests.test_api_upload_invalid

python -m tests.test_api_analyze_file_not_found

python -m tests.test_api_analyze_empty_query

python -m tests.test_api_status_not_found

python -m tests.test_api_upload_too_large

python -m tests.test_api_full_flow_live

python -m tests.test_api_openapi_docs



# Test critique persistance (process uvicorn réel)

python -m tests.test_persistence

```


