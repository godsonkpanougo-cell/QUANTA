# RAPPORT A4 — Durcissement : bug méthodologique P0, tests réparés, contrat, HC3, Sentry

- **Date** : 05/10/2026
- **Branche** : `feature/freebuff-durcissement-plus` (créée depuis `main` `f61a566`)
- **Périmètre** : les 4 sous-points de A4 demandés — réparer les 2 exclusions de tests, contrat Pydantic du payload, HC3 automatique sur hétéroscédasticité, monitoring (Sentry optionnel). **Plus une découverte majeure** : le bug `theme="both"` (cause historique du test orchestrateur en échec).
- **Protocole symbole** : preuves brutes, un commit par tâche, jamais de force push, `import main` vérifié.

---

## 1. Résultat global

| Vérification | Résultat |
|---|---|
| Suite complète **SANS exclusions** (`python -m pytest tests/ -q`) | **126 passed, 0 failed** en 5 min 24 s |
| Les 2 exclusions historiques réintégrées | `test_quota` 3/3 ✓, `test_orchestrator_compare_groups` 1/1 ✓ |
| `python -c "import main"` | OK (aucune régression d'import) |
| Bloc A4 (`tests/test_industrialisation.py`) | 5/5 |
| Suite intermédiaire (piliers) | 32/32 (projects 11, conversation 9, defense 4, etc.) |

---

## 2. BUG MAJEUR découvert et corrigé : normalité vide en `theme="both"` (défaut prod)

### 2.1 Le bug

Dans `run_base_compute_pipeline` (`app/compute/compute.py`), la branche `theme="both"` — **le défaut de prod** — faisait :

```python
norm = norm_dark.get("normality", {})   # écrase le dict complet par la sous-clé
...
return { ..., "normality_tests": norm.get("normality", {}), ... }  # refait .get -> {} VIDE
```

Double `.get("normality")` : le payload final contenait une **normalité vide** en branche both (mais correcte en mono-thème — d'où la difficulté à voir l'échec).

### 2.2 Conséquence prouvée (A/B, avant fix)

| Exécution | Normalité dans le payload | Test sélectionné |
|---|---|---|
| Pipeline seul (`run_base_compute_pipeline` mono-thème) | peuplée (test NORMALE ✓) | — |
| Orchestrateur (theme="both") | **vide** → `_normality_ok` False | **Mann-Whitney systématique** |

Donc **en prod, tous les tests de comparaison basculaient en non-paramétrique** au lieu de Student/Welch même quand les données étaient normales — une faute méthodologique exactement dans la ligne de mire de l'incident de crédibilité.

### 2.3 Le fix (commenté dans le code, `BUG FIX (05/10/2026)`)

```python
# norm doit rester le resultat COMPLET de normality_tests (avec la cle interne
# "normality"), comme dans la branche mono-theme -- le return final fait
# norm.get("normality") et produisait un dict VIDE quand theme="both" ...
norm = norm_dark
```

### 2.4 Preuve après fix

Orchestrateur sur données normales → **Student/Welch sélectionné** (normalité peuplée). Verrouillé par `tests/test_orchestrator_compare_groups.py` (§3.1) et par le contrat d'industrialisation (§5).

---

## 3. Les 2 exclusions de tests réparées (réintégrées dans la suite complète)

### 3.1 `tests/test_orchestrator_compare_groups.py` — « no tests ran » résolu

- **Cause racine** : le fichier était un script `if __name__ == "__main__":` — **jamais collecté par pytest**. D'où le mystère historique « no tests ran » et l'exclusion.
- **Fix** : converti en vrai test pytest (`test_orchestrator_compare_groups_selectionne_parametrique`) avec le mode CLI conservé pour l'investigation manuelle.
- **Preuve** : `1 passed` ; sélection Student/Welch confirmée après le fix §2.

### 3.2 `tests/test_quota.py` — 2 échecs historiques

- **Causes** (diagnostiquées, pas contournées) :
  1. rate-limiter slowapi **5/min** → 429 dès la 6ᵉ requête du test (le test dépasse 5 requêtes par conception) ;
  2. 15 analyses avec un payload **identique** → cache-hit → zéro consommation de quota (by design), donc le compteur attendu ne bougeait pas.
- **Fix** (fixture `_disable_rate_limiter_for_quota_tests`) :
  - `main.limiter.enabled = False` (toggle runtime slowapi — le rate-limit reste actif en prod, seulement neutralisé dans ce test) ;
  - requêtes **uniques** `f"Test analysis {i+1}"` (contourne le cache de manière légitime) ;
  - `monkeypatch.setattr(main, "_run_analysis_background", lambda *a, **k: None)` — sinon le test déclenche 15 **vraies** analyses LLM (timeout garanti, hors périmètre du test qui vérifie le quota, pas le LLM).
- **Preuve** : **3/3 passed**.

---

## 4. HC3 automatique sur hétéroscédasticité (`ols_regression`)

- **Comportement** : si Breusch-Pagan **OU** White p < 0,05 → refit `sm.OLS(Y, X).fit(cov_type="HC3")`. Les estimations ponctuelles sont identiques ; seuls écarts-types, IC et p-values changent (c'est le but des erreurs-types robustes).
- **Nouvelles clés du payload** : `heteroscedasticity_detected` (bool), `cov_type_used` ("HC3"/"nonrobust"), `coefficients_robust` (dict par variable : coefficient, std_err_robust, t_stat_robust, p_value_robust, bornes d'IC, significant_robust), `robust_note` (texte explicatif). Le payload classique `coefficients` reste inchangé en comparaison.
- **Preuves brutes** :
  - dataset hétéroscédastique (seed 7) : `heteroscedasticity_detected=True`, `cov_type_used="HC3"`, SE 0,165 → 0,178, **coefficients identiques** ;
  - dataset homoscédastique (seed 3) : `heteroscedasticity_detected=False`, `cov_type_used="nonrobust"`, `coefficients_robust == {}`.
- **Note d'implémentation** : `target_col` doit appartenir aux colonnes numériques, sinon la régression est `skipped` (comportement existant, respecté par les tests).
- Verrouillé par `test_hc3_heteroscedasticite_active` et `test_hc3_homoscedasticite_sans_robustesse`.

---

## 5. Contrat Pydantic du payload (`app/schemas/analysis.py`)

- **Contenu** : `AnalysisPayload` (+ `ConfidenceScore`, `InferenceBlock`), `extra="allow"` (les clés non déclarées restent acceptées — le contrat décrit, il ne casse pas).
- **Point d'attention (corrigé en cours de route)** : le contrat décrit la réponse de l'**ORCHESTRATEUR** (`run_full_analysis`), pas le payload du pipeline de base. La première version du test validait le mauvais objet ; corrigé via le helper `tests/_print_orchestrator.py` (`run_orchestrator_sample`).
- **Ce que le contrat verrouille** : normalité peuplée dans les 2 branches de thème, sélection paramétrique fonctionnelle, présence des clés critiques (`multiplicity`, `confidence_score`, `action_executed`, …).
- **Preuve** : `tests/test_industrialisation.py` **5/5** (dont validation `AnalysisPayload.model_validate(payload_orchestrateur_reel)`).

---

## 6. Sentry optionnel (`main.py`)

- **Design** : bloc post-`include_router(defense.router)` — **actif uniquement si `SENTRY_DSN` est défini dans l'environnement**. Sans DSN : zéro import, zéro dépendance, zéro effet (no-op) ; si DSN présent mais `sentry-sdk` absent : warning loggé, l'app démarre quand même.
- **État** : `requirements.txt` volontairement **sans** `sentry-sdk` et `.env` sans DSN → le bloc est no-op aujourd'hui ; l'activation en prod = ajouter `sentry-sdk[fastapi]` + `SENTRY_DSN` (2 lignes de config, zéro code).
- **Preuve** : `import main` OK avec le bloc en place.

---

## 7. Fichiers touchés (commit A4)

| Fichier | Nature |
|---|---|
| `app/compute/compute.py` | fix `theme="both"` + HC3 auto |
| `main.py` | bloc Sentry optionnel |
| `app/schemas/__init__.py`, `app/schemas/analysis.py` | NOUVEAUX — contrat Pydantic |
| `tests/test_quota.py` | fixture limiter + requêtes uniques + worker no-op |
| `tests/test_orchestrator_compare_groups.py` | script → pytest |
| `tests/test_industrialisation.py` | NOUVEAU — 5 tests d'industrialisation |

**Fichiers présents dans le dépôt de travail mais HORS périmètre A4 (non commités, non touchés)** : `app/report_generator.py` (modifié par ailleurs), `app/quanta_fonts.py`, `quanta-frontend/*`, `scripts/audit_pdf_geometry.py`, `scripts/gen_preview_reports.py`, `scripts/inspect_pdfs.py`, `scripts/investigate_bootstrap_eta2.py`, `assets/`, `lighthouse-report-home.*`, `quanta_pdf_preview.html`, `rapports quanta/preview/` — travail d'autres chantiers/threads, exclus du commit A4.

---

## 8. Conclusion

A4 est **complet et prouvé** : la suite complète tourne **sans aucune exclusion** (126/126), le bug méthodologique `theme="both"` (Mann-Whitney systématique en prod) est corrigé et verrouillé par 2 niveaux de tests, le quota et l'orchestrateur sont testables, le payload est sous contrat Pydantic, HC3 répond automatiquement à l'hétéroscédasticité, et Sentry est prêt à brancher sans aucune dépendance imposée. Cumulé avec le rapport A1 (incident 260 s clos), le socle de crédibilité passe de « promesse » à « vérifiable par quiconque ».

*Fin du rapport A4.*
