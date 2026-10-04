# RAPPORT P3 — PILIER 3 : REPRO PACK (ARCHIVE D'AUDIT TÉLÉCHARGEABLE)

> Date : 02/10/2026 — Exécution : Buffy (Freebuff). Mandat : « continuer les
> 4 piliers, un rapport par action, sans casser l'existant, rapports dans un
> même dossier » — rapport n°4 de `RAPPORTS_PILIERS/`.

---

## 1. Pourquoi ce pilier (rappel de l'arbitrage)

L'argument qui convainc un encadreur n'est pas « notre IA est forte », c'est
« **ce rapport est auditable** ». Le Repro Pack matérialise la promesse
« chaque chiffre de ce rapport est recomputable » — un ZIP par analyse qui
réunit la sortie exacte, les données d'origine, l'environnement et les seeds.
Aucun concurrent n'offre cela ; c'est ce qui transforme un utilisateur en
avocat et un encadreur en prescripteur.

## 2. Conception (règle « sans casser l'existant »)

**[app/repro_pack.py](app/repro_pack.py)** — module ISOLÉ :
- **AUCUNE table nouvelle** (lit analyses/uploads via db.py existant) ;
- **AUCUN recalcul statistique** : assemblage en lecture pure (compatible
  budget Render) ;
- branchement main.py : **2 lignes** (import + include_router).

### Contenu du ZIP (`GET /repro_pack/{analysis_id}?theme=dark|light`)
| Fichier | Contenu |
|---|---|
| `README.txt` | audit : analysis_id, dates, requête, **sha256 du fichier source**, dimensions, **versions exactes des packages** (numpy, pandas, scipy, statsmodels, prince, matplotlib, seaborn, fastapi, uvicorn), Python, plateforme, **seeds documentés** (random_state=42, bootstraps seedés par appel), procédure « comment vérifier un chiffre » |
| `resultats.json` | la sortie persistée EXACTE (source de vérité qui a produit le PDF) — **aucune réécriture** |
| `donnees/<fichier>` | l'upload original tel quel (identité vérifiable par le sha256 du README) ; mention explicite si absent du disque |
| `rapport_<theme>.pdf` | inclus SI déjà généré ; sinon le README indique comment l'obtenir (`GET /report/{id}`) |
| `script_reproduction.R` / `.do` | embarqués s'ils sont présents dans le résultat persisté |

Réponses d'erreurs cohérentes avec le repo : 404 introuvable/cross-user,
400 analyse non terminée, 401/403 sans session.

## 3. Preuves brutes (exécutions réelles du 02/10)

### 3.1 Tests ciblés — `python -m pytest tests/test_repro_pack.py -q`
```
6 passed, 11.28s
```
Verrouillés : ZIP valide avec tous les fichiers attendus ; **sha256 du
fichier source présent dans le README et égal au contenu embarqué** ;
versions des packages + seeds + mentions de contenu dans le README ;
**`resultats.json` strictement IDENTIQUE à la sortie persistée**
(comparaison dict == dict, preuve de non-réécriture) ; données embarquées
**à l'octet près** ; scripts R et Stata présents ; PDF inclus quand il
existe (et absent avec mention `GET /report/` sinon) ; 404 introuvable ;
400 non terminée ; téléchargement HTTP complet (headers
`application/zip` + `attachment`) ; **cross-user 404** ; 401/403 sans auth.

### 3.2 Non-régression globale
```
python -m pytest tests/ (hors test_quota, test_orchestrator_compare_groups)
  -> 113 passed (107 précédents + 6 nouveaux), 257.37s
python -c "import main" -> IMPORT MAIN OK
```

## 4. Non-cassage vérifié

- main.py : +2 lignes additives (import + include_router `/repro_pack`) ;
- db.py, /analyze, /status, /report : **zéro modification** ;
- zéro table nouvelle, zéro migration, endpoint préfixé isolé ;
- CI de branche : verte à confirmer après push (feature/**).

## 5. Évolutions possibles (hors périmètre de ce pilier)

- Déclencher la génération du PDF avant l'assemblage si absent (coût :
  subprocess PDF worker — laissé au frontend qui le fait déjà via /report) ;
- bouton « Télécharger le dossier d'audit » côté frontend ;
- inclure l'audit_log du cleaning comme fichier séparé (déjà dans
  resultats.json aujourd'hui).

## 6. État git

- Branche `feature/freebuff-piliers` (main intact).
- Commits : P3 code+tests, P3 rapport.
- Hérités non commités (pas à moi) : `investigate_bootstrap_eta2.py`, lighthouse.

## 7. État du chantier des piliers

| Pilier | État |
|---|---|
| P0 crédibilité | ✅ livré (RAPPORT_P0_CREDIBILITE.md) |
| P1 Projet persistant | ✅ livré (RAPPORT_P1_PROJET_PERSISTANT.md) |
| P2 Session conversationnelle | ✅ livré (RAPPORT_P2_SESSION_CONVERSATIONNELLE.md) |
| **P3 Repro Pack ZIP** | ✅ **livré ce tour** (ce rapport) |
| P4 Mode Soutenance | dernier pilier, à venir |
