# QUANTA — État Actuel du Système
*Dernière mise à jour : 24 juillet 2026*

Document de référence pour les sessions de développement. Décrit **ce qui existe et fonctionne aujourd’hui**, pas la vision produit ni les specs futures. Les limitations sont assumées.

---

## 1. Vue d'ensemble

- **Ce qu’est QUANTA** : un moteur d’analyse statistique doctoral-level qui transforme un fichier de données + une requête (optionnelle) en résultats chiffrés déterministes, interprétation textuelle structurée, et rapport PDF signable.
- **Promesse centrale** : « Tu déposes ta base. Tu reçois un rapport que tu peux signer. » — séparation stricte **COMPUTE** (calcule) → **BRAIN** (interprète seulement) → **REPORT** (met en page).
- **Stack technique (versions exactes, juillet 2026)** :

| Couche | Technologie | Version |
|--------|-------------|---------|
| Runtime | Python | 3.12+ (cible projet) |
| API | FastAPI | 0.137.0 |
| Serveur | uvicorn | 0.49.0 |
| Validation | pydantic | 2.13.4 |
| Data | pandas | 3.0.3 |
| Numérique | numpy | 2.4.6 |
| Stats | scipy | 1.17.1 |
| Stats modèles | statsmodels | 0.14.6 |
| ANOVA Welch | pingouin | 0.6.1 |
| Post-hoc | scikit-posthocs | 0.14.0 |
| Graphiques | matplotlib / seaborn | 3.11.0 / 0.13.2 |
| Excel | openpyxl | 3.1.5 |
| SPSS | pyreadstat | 1.3.5 |
| PDF | WeasyPrint | 69.0 |
| HTTP LLM | requests | 2.32.4 |
| Env | python-dotenv | 1.2.2 |
| Frontend | Next.js | 16.2.9 |
| UI | React | 19.2.4 |
| CSS | Tailwind CSS | 4.x |
| Motion | framer-motion | ^12.42.0 |
| Persistance | SQLite (stdlib) | fichier `quanta.db` |

---

## 2. Architecture des fichiers

Chemins relatifs à la racine du dépôt. Lignes ≈ comptage physique (indicatif).

### Racine
- `main.py` — API FastAPI : upload, analyze async, status, history, report PDF (`?theme=dark|light`), **audit_trail** horodaté — dépend de `db`, `app.compute`, `app.orchestrator`, `app.llm.brain`, `app.report_generator`
- `db.py` — persistance SQLite (uploads + analyses) — stdlib `sqlite3` uniquement
- `requirements.txt` — pin des dépendances Python
- `.env.example` — modèle de configuration LLM
- `QUANTA_STATE.md` — ce document
- `DESIGN_BRIEF.md` — contrat visuel frontend (pas le moteur stats)
- `NOTES.md` — notes historiques de conception (non normatif)
- `legacy/` — code historique **lecture seule** (référence, ne pas modifier)

### `app/`
- `app/orchestrator.py` — pipeline bout-en-bout : compute → test_selector → délégation → **puissance statsmodels** → score de confiance
- `app/report_generator.py` — HTML → PDF WeasyPrint (thèmes dark/light) — lit le résultat assemblé, ne recalcule rien
- `app/compute/compute.py` — chargement, diagnostic, nettoyage, descriptives, normalité, corrélation, OLS, charts, scripts R/Stata, **`compute_statistical_power`**
- `app/compute/test_selector.py` — arbre de décision + tests d’inférence + **post-hoc** (Tukey / Dunn / Games-Howell)
- `app/llm/brain.py` — `text_to_intent`, `generate_interpretation`, anti-hallucination, Skeptic Engine, `analyze_with_brain`

### Frontend `quanta-frontend/`
- `app/page.tsx` — point d’entrée Next (délègue à `HomePage`)
- `app/components/HomePage.tsx` — orchestration UI upload → analyse → résultats
- `app/components/UploadZone.tsx` — drag & drop fichier
- `app/components/AnalysisProgress.tsx` — polling `/status`
- `app/components/AnalysisResults.tsx` — résultats + **deux téléchargements PDF** (Dark / Académique)
- `app/components/ConfidenceScore.tsx` — score de confiance
- `public/sample_data.csv` — dataset d’exemple (50 lignes)

### Tests `tests/`
- Suite manuelle documentée dans `tests/RESULTS.md` (compute, selector, orchestrator, brain, API, persistance, CSV français)
- Helpers : `_api_test.py`, `_print_*.py`

---

## 3. Les Organes actifs

### Organe 01 — Intake Engine (`app/compute/compute.py` → `load_and_diagnose`)

- **Formats acceptés** : CSV, Excel (`.xls`/`.xlsx`), Stata (`.dta`), SPSS (`.sav` via pyreadstat)
- **Encodages gérés** : cascade `utf-8` → `utf-8-sig` → `cp1252` → `latin-1` (filet de sécurité)
- **Séparateurs détectés** : virgule, point-virgule, tabulation, pipe (par cohérence du nombre de colonnes, pas comptage brut)
- **Virgule décimale française** : oui — `_try_convert_french_decimal()` si ≥ 90 % des valeurs convertibles
- **Détection de colonnes** :
  - numériques continues vs catégorielles (garde-fou cardinalité &lt; 10 sur n ≥ 10)
  - IDs probables exclus (`id`, `uuid`, etc.)
  - dates / type de dataset heuristique
- **Détection doublons** : oui via `df.duplicated()` — champs `n_duplicates` + `duplicates_removed: false` (signalement, **pas** de suppression au diagnostic)
- **Statistiques descriptives** (`descriptive_stats` dans le diagnostic) :
  - **Numériques** : mean, median, std, min, max, skewness, kurtosis, missing_pct
  - **Catégorielles** : frequencies, percentages, mode, missing_pct
- **Limites API** (dans `main.py`, pas dans compute) : **10 Mo**, **50 000 lignes**

### Organe 02 — Cleaning Core (`clean_dataframe`)

**Statut : PARTIEL (~70 %)**

**Ce qui est fait :**
- Copie défensive `df.copy()`
- Détection + log des doublons **sans suppression** (`detection_sans_suppression`)
- Imputation manquants numériques : médiane (&lt; 5 %), moyenne (5–20 %), suppression colonne (&gt; 20 %)
- Imputation manquants catégoriels : mode (&lt; 20 %), sinon suppression colonne
- Winsorisation 1 %–99 % sur numériques si n ≥ seuil (sinon log `winsorisation_non_appliquee`)
- `audit_log` structuré `{etape, colonne, decision, valeur, justification}`

**Ce qui ne l’est pas encore :**
- Validation / accord utilisateur avant chaque transformation
- Imputation avancée (MICE, KNN, modèles)
- Suppression optionnelle des doublons sous contrôle utilisateur
- UI de revue du cleaning avant analyse
- Export du dataset nettoyé vers le client

### Organe 03 — Statistical Brain (`test_selector.py` + `orchestrator.py`)

**Tests implémentés (avec conditions) :**

| Famille | Test | Conditions | ddl retournés |
|---------|------|------------|---------------|
| 2 groupes indépendants | t-Student | normalité OK + Levene variances égales | `df` (= n1+n2−2) |
| 2 groupes indépendants | t-Welch | normalité OK + variances inégales | `df` (scipy `.df`, Satterthwaite) |
| 2 groupes indépendants | Mann-Whitney U | non-normalité | — |
| 2 groupes appariés | t pairé / Wilcoxon | `paired=True` + normalité | `df` (t pairé) / — (Wilcoxon) |
| k groupes | ANOVA + **Tukey HSD** (si p &lt; 0.05) | normal + variances égales | `df_between`, `df_within` |
| k groupes | Welch ANOVA (`pingouin.welch_anova`) + **Games-Howell** (repli Tukey) | normal + variances inégales | `df_between`, `df_within` (dénominateur décimal) |
| k groupes | Kruskal-Wallis + **Dunn Bonferroni** (si p &lt; 0.05) | non-normal | `df` (= k−1) |
| Association | Chi-deux | effectifs attendus ≥ 5 | `df` (via `chi2_contingency`) |
| Association | Fisher exact | table 2×2, effectifs &lt; 5 | `df` dans `chi2_indicatif` seulement |
| Association | Chi-deux avec réserve | table &gt; 2×2, effectifs &lt; 5 | `df` |
| Corrélation | Pearson / Spearman | déléguée à compute (normalité conjointe) | — (délégation compute) |
| Régression | OLS | target numérique + prédicteurs (délégation) | — (délégation compute) |
| Régression | Logistique binaire | target catégorielle à 2 niveaux | — |
| Repli | `descriptive_only` | schéma invalide / intention absente | — |

**Post-hoc (juil. 2026) :**
- Format unifié `posthoc: { method, comparisons[{group1, group2, meandiff, p_adj, significant}] }` ou `null` si p ≥ 0.05
- Affichage PDF : sous-section « Comparaisons post-hoc » (lignes or / muted)

**Puissance statistique (juil. 2026) :**
- `compute.compute_statistical_power()` appelé par l’orchestrateur après chaque test
- t-test / Mann-Whitney → `TTestIndPower` ; ANOVA / Kruskal → `FTestAnovaPower` ; Chi-deux → `GofChisquarePower`
- Champs : `power`, `power_interpretation`, `n_required` (si power &lt; 0.8, effet moyen 0.3)

**Arbre de décision (résumé) :**
1. Valider colonnes (existence, type, exclusion IDs) → `validation_issues`
2. Selon `action` : `compare_groups` / `association` / `regression` / `correlation` / `descriptive_only`
3. Pour groupes : 2 → comparaison 2 groupes ; 3+ → multi-groupes ; &lt; 2 → skip
4. Normalité + Levene orientent paramétrique vs non-paramétrique
5. Fallback systématique vers descriptif si schéma incohérent (jamais d’exception non gérée)

**Score de confiance (pondérations) :**
- Qualité des données — **20 %**
- Respect des conditions — **25 %**
- Cohérence inter-méthodes — **20 %**
- Taille d’échantillon — **15 %**
- Stabilité (outliers / interventions) — **20 %**
- Niveaux : Élevé (≥ 85) / Modéré (≥ 65) / Faible (≥ 40) / Très faible
- **Plafonds** : n &lt; 30 → niveau max « Faible » ; n &lt; 100 → max « Modéré »

**Mode autonome** (`auto_intent` si query vide) :
- 1+ cat + numériques → `compare_groups` (jusqu’à 3 targets)
- 2+ numériques → 1 corrélation
- 2+ cat → 1 association
- Toujours un `descriptive_only` en fin
- Brain sélectionne le run « le plus significatif » (p minimale, sinon score) pour l’interprétation principale ; le rapport multi-tests liste l’ensemble (filtre `descriptive_only` si d’autres tests ont une vraie p-value)

### Organe 04 — Interpretation Layer (`app/llm/brain.py`)

- **Provider principal** : Groq, modèle défaut `llama-3.3-70b-versatile` (`PRIMARY_*` ou legacy `GROQ_API_KEY`)
- **Fallback** : OpenRouter, modèle défaut `deepseek/deepseek-chat` (`FALLBACK_*` / `OPENROUTER_API_KEY`)
- **API** : compatible OpenAI `chat/completions` ; retries + backoff ; **jamais d’exception** vers l’appelant si LLM down → `llm_available: false` + résultats bruts
- **Niveaux** : technique / analytique / décisionnel (+ résumé exécutif, limites)
- **Anti-hallucination** : extracte les nombres du JSON généré et les compare aux sources (±1 % / ±0.01) ; détecte formats anormaux (zéros de tête type `025,02`)
- **Skeptic Engine** (`validate_conclusions`) : post-interprétation ; si p &gt; 0,05 et texte revendique significativité sans nuance (ou l’inverse) → `skeptic_engine_alert` + message ; **ne bloque jamais** la génération
- **Règle d’or** : le LLM ne calcule jamais ; il cite / reformule

### Organe 05 — Report Forge (`app/report_generator.py`)

- **Format** : PDF via **WeasyPrint 69.0** (HTML/CSS → bytes)
- **Thèmes** : `theme="dark"` (défaut) ou `theme="light"` (académique) — or/cyan conservés
- **Sections actuelles** :
  1. Page de garde (fichier, date, score, versions moteur, SHA256)
  2. **1. Présentation des données** (n, variables, manquants, doublons)
  3. **1.5 Statistiques descriptives** (tableaux APA)
  4. **2. Analyse statistique** (H₀/H₁, APA, **post-hoc**, **puissance 1-β**, graphiques)
  5. **3. Interprétation** (+ Skeptic Engine si alerté)
  6. **4. Limites et réserves**
  7. **En résumé** (puces actionnables)
  8. **Défense Scientifique** — objections/réponses automatiques (normalité, puissance réelle, effet négligeable, Skeptic)
  9. **Annexe A** — scripts R + Stata
  10. **Annexe C** — bibliographie méthodologique automatique
  11. **Annexe D** — script Python Colab (reproductible)
  12. **Annexe E** — journal d’audit horodaté
- **Graphiques intégrés** : oui — base64 PNG (distributions, QQ, heatmap, diagnostics)
- **Scripts reproductibles** : R + Stata (compute) + **Python Colab** (généré dans le rapport)

### Organe 06 — API & Persistance (`main.py` + `db.py`)

**Endpoints (6) :**

| Méthode | Route | Rôle |
|---------|-------|------|
| GET | `/health` | santé service |
| POST | `/upload` | fichier → diagnostic léger + `file_id` |
| POST | `/analyze` | lance analyse async → `analysis_id` (+ `audit_trail` dans le résultat) |
| GET | `/status/{analysis_id}` | polling pending/running/done/error |
| GET | `/history` | dernières analyses |
| GET | `/report/{analysis_id}?theme=dark\|light` | PDF binaire (analyse `done` uniquement) |

- **Persistance** : SQLite `quanta.db` (configurable `QUANTA_DB_PATH`) — tables `uploads`, `analyses` ; fichiers physiques dans `temp/quanta_uploads/`
- **Asynchrone** : `BackgroundTasks` FastAPI (pas Celery/Redis)
- **CORS** : défaut `http://localhost:3000` (`CORS_ALLOWED_ORIGINS`)
- **Audit trail** : journal horodaté (chargement → diagnostic → chaque test → préparation rapport) stocké dans `result["audit_trail"]`

---

## 4. Interface Frontend (`quanta-frontend/`)

- **Framework** : Next.js **16.2.9** (App Router) + React **19.2.4** + Tailwind **4**
- **Composants applicatifs** :
  - `HomePage` — état global (fichier, query, phase, résultat)
  - `UploadZone` — upload contrôlé (`selectedFile`)
  - Lien « Pas de fichier ? Tester avec un exemple → » → charge `public/sample_data.csv` + query « Analyser automatiquement ce dataset »
  - `AnalysisProgress` — poll `/status`
  - `AnalysisResults` — interprétation, score, **Rapport Dark** + **Rapport Académique**
  - `ConfidenceScore` — visualisation du score
- **UI shadcn** : `button`, `accordion` (sous `components/ui/`)
- **Flux utilisateur** : upload (ou exemple) → query optionnelle → Analyser → progression → résultats → téléchargement PDF (dark ou light) → nouvelle analyse
- **Design system** (globals.css) :
  - Fonds : void `#0A0A0F`, surface `#13131A`, elevated `#1C1C26`
  - Accents : or `#C9A84C`, cyan `#00D4FF`
  - Texte : primary / secondary / muted
  - Typo : Space Grotesk (display), Geist (sans), JetBrains Mono (mono)
- **Prérequis** : `NEXT_PUBLIC_API_URL` (ex. `http://127.0.0.1:8000`)

---

## 5. Tests validés

Source principale : `tests/RESULTS.md` (validations manuelles chronologiques).

### Compute (2026-06-15, MAJ CSV FR 2026-06-30)
Datasets : `clean`, `missing_15pct`, `outliers_extreme`, `region_likert`, `small_sample`, `large_sample`, `with_duplicates`, `mixed_categorical` — **aucun crash** ; IDs exclus ; reclassification Likert OK.

### Test selector
Scénarios validés : Student, Mann-Whitney, ANOVA, Kruskal-Wallis, Chi-deux, Fisher 2×2, logistique, cas piège (colonne absente / id) → `descriptive_only`. Relancés **24 juil. 2026** après post-hoc / power / annexes — **zéro régression**.

### Orchestrator
compare_groups E2E, délégation OLS, délégation corrélation, score dégradé + plafonds n, trap, fichier corrompu → `status=failed`.

### Brain (live Groq + repli sans clé)
`text_to_intent` live / no-key ; `generate_interpretation` live / no-key ; `analyze_with_brain` E2E ; sérialisation JSON. Modèle live documenté : `llama-3.3-70b-versatile`.

### API
9 scripts TestClient + OpenAPI ; flux live Groq ; limites taille ; query vide (mode auto).

### Persistance SQLite (J21)
`test_persistence` : vrai process uvicorn — status + history survivent au redémarrage.

### CSV français réel
`french_excel_export.csv` (Latin-1, `;`, virgule décimale) — upload + analyze + status OK (`test_french_excel_export`).

### Régression Mois 1
12 datasets via API avec clé Groq — statut `done`, `llm_available=True` sur les cas documentés.

---

## 6. Ce qui fonctionne de bout en bout

- Upload multi-format avec diagnostic de colonnes
- Analyse async complète : compute → sélection de test → **puissance** → score → interprétation LLM (si clés) ou repli brut
- Mode autonome sans query
- Post-hoc automatiques (Tukey HSD, Dunn, Games-Howell) quand le test global est significatif
- Rapport PDF téléchargeable en **thème Dark** ou **Académique (light)**
- Défense Scientifique + bibliographie (Annexe C) + script Python Colab (Annexe D) + journal d’audit (Annexe E)
- Frontend local : upload, exemple, progress, résultats, double download PDF
- Persistance SQLite survivant aux redémarrages
- Robustesse CSV francophones (encodage / séparateur / décimale)
- Audit log cleaning/sélection **et** audit trail horodaté API
- Graphiques base64 générés dans le pipeline et intégrés au PDF

---

## 7. Ce qui est partiellement implémenté

| Élément | Avancement estimé | Commentaire |
|---------|-------------------|-------------|
| Cleaning Core | ~70 % | Automatique + audit ; pas de consentement utilisateur |
| Rapport académique « complet » | ~90 % | Annexes A–E, défense, puissance, thèmes ; manque reco / méthodo narrative séparée |
| ddl dans tableaux APA | ~90 % | Clés exposées ; cas délégués (corrélation / OLS) peuvent afficher « — » |
| Welch ANOVA | 100 % | `pingouin.welch_anova` ; ddl décimaux documentés |
| Post-hoc Tukey / Dunn / Games-Howell | ~95 % | Format unifié + PDF ; Dunn exige `scikit-posthocs` |
| Power Analysis | ~90 % | statsmodels branché ; MW via \|r\| approximation TTestIndPower |
| Scientific Defense | ~95 % | 4 objections conditionnelles ; puissance réelle dans objection 2 |
| Mode multi-tests autonome | ~85 % | Fonctionne ; interprétation primaire = test le plus significatif |
| Skeptic Engine | ~90 % | Code actif + bandeau PDF ; tests dédiés / UX frontend encore manquants |
| Frontend produit | ~70 % | Flux principal + dual PDF ; pas d’historique UI, auth, settings |
| Audit trail PDF | ~85 % | Journal API → Annexe E ; entrée « PDF » = résultat prêt (génération à la demande) |

---

## 8. Ce qui n'est pas encore implémenté

- Authentification / multi-utilisateurs / comptes
- File d’attente lourde (Celery, Redis, workers)
- Déploiement production (domaine CORS restreint, HTTPS, etc.)
- Accord utilisateur explicite avant cleaning / suppression doublons
- Section Méthodologie / Recommandations séparées (structure « 10 sections » des règles report)
- Export dataset nettoyé
- Tests inférentiels avancés (ANOVA factorielle, modèles mixtes, survival, bayésien…)
- Affichage UI dédié de `skeptic_engine_alert`
- Internationalisation (UI FR hardcodée)
- CI automatisée (les tests sont surtout manuels via `python -m tests…`)

---

## 9. Variables d'environnement requises

Fichier `.env` à la racine (jamais commit). Modèle : `.env.example`.

| Variable | Rôle | Exemple |
|----------|------|---------|
| `PRIMARY_API_KEY` | Clé LLM principal (Groq) | `gsk_…` |
| `PRIMARY_BASE_URL` | Base URL OpenAI-compat | `https://api.groq.com/openai/v1` |
| `PRIMARY_MODEL` | Modèle principal | `llama-3.3-70b-versatile` |
| `FALLBACK_API_KEY` | Clé secours (OpenRouter) | `sk-or-…` |
| `FALLBACK_BASE_URL` | Base URL secours | `https://openrouter.ai/api/v1` |
| `FALLBACK_MODEL` | Modèle secours | `deepseek/deepseek-chat` |
| `GROQ_API_KEY` | Alias legacy de PRIMARY | (optionnel) |
| `OPENROUTER_API_KEY` | Alias legacy de FALLBACK | (optionnel) |
| `CORS_ALLOWED_ORIGINS` | Origines CORS (CSV) | `http://localhost:3000` |
| `QUANTA_DB_PATH` | Chemin SQLite | `quanta.db` |

**Frontend** (`quanta-frontend/.env.local`) :

| Variable | Rôle | Exemple |
|----------|------|---------|
| `NEXT_PUBLIC_API_URL` | URL de l’API FastAPI | `http://127.0.0.1:8000` |

Sans clé LLM : l’analyse statistique **fonctionne** ; l’interprétation textuelle bascule en `llm_available: false`.

---

## 10. Comment lancer QUANTA localement

### Prérequis
- Python 3.12+
- Node.js 20+ (recommandé pour Next 16)
- Dépendances système WeasyPrint (GTK/Pango selon OS — obligatoire pour le PDF)

### Backend
```bash
cd QUANTA
python -m venv .venv
# Windows :
.venv\Scripts\activate
# Unix :
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # puis renseigner PRIMARY_API_KEY (et fallback si besoin)

uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Vérifier : `http://127.0.0.1:8000/health` et `http://127.0.0.1:8000/docs`

### Frontend
```bash
cd quanta-frontend
npm install
# créer .env.local avec :
# NEXT_PUBLIC_API_URL=http://127.0.0.1:8000

npm run dev
```
Ouvrir : `http://localhost:3000`

### Parcours de smoke test
1. « Tester avec un exemple » → Analyser  
2. Attendre le statut `done`  
3. Lire interprétation + score  
4. Télécharger le PDF Dark **et** Académique  

### Relancer une validation ciblée
```bash
python -m tests.test_selector_2groups_normal
python -m tests.test_selector_2groups_nonnormal
python -m tests.test_selector_multigroup
python -m tests.test_selector_association
python -m tests.test_selector_logistic
python -m tests.test_selector_trap
```

---

## Ajouts récents (21–24 juillet 2026)

| Feature | Où | Statut |
|---------|-----|--------|
| Post-hoc Tukey HSD / Dunn / Games-Howell | `test_selector` + PDF | ✅ |
| Scientific Defense | `report_generator` | ✅ |
| Power Analysis (statsmodels) | `compute` + orchestrator + APA | ✅ |
| Thème Light / Académique | `generate_pdf_report(theme=…)` + `/report?theme=` + UI | ✅ |
| Bibliographie Annexe C | `report_generator` | ✅ |
| Script Python Annexe D (Colab) | `report_generator` | ✅ |
| Audit trail Annexe E | `main._run_analysis_background` + PDF | ✅ |

---

## Limitations connues (honnêteté opérationnelle)

1. **Doublons** : détectés et signalés ; **conservés** dans le dataset analysé (plus de `drop_duplicates` au cleaning).
2. **ddl APA** : clés standardisées exposées par `test_selector` ; cas délégués (corrélation / OLS) peuvent encore afficher « — ».
3. **Welch ANOVA** : implémentation stricte via pingouin ; dénominateur non-entier attendu.
4. **PDF / WeasyPrint** : dépendances OS fragiles ; échec → `/report` peut renvoyer une erreur plutôt qu’un PDF.
5. **LLM** : qualité non déterministe ; Skeptic + anti-hallucination mitigent mais ne garantissent pas.
6. **Frontend** : mono-page ; pas d’historique navigable côté UI malgré `/history` API.
7. **Puissance MW** : approximation via `|r|` sous `TTestIndPower` (pas un modèle MW dédié).
8. **Legacy** : `/legacy` est référence figée — ne pas y développer.

---

*Fin de l’état actuel. Mettre à jour ce fichier à chaque organe significativement modifié.*
