# RAPPORT P1 — PILIER 1 : PROJET DE RECHERCHE PERSISTANT

> Date : 02/10/2026 — Exécution : Buffy (Freebuff). Mandat : « on met en place
> les 4 piliers, un rapport par action, sans casser l'existant, dans un même
> dossier » — les rapports vivent tous dans `RAPPORTS_PILIERS/`.

---

## 1. Pourquoi ce pilier (rappel de l'arbitrage)

Claude/ChatGPT sont indispensables parce qu'ils sont **l'endroit où vit le
travail quotidien**. Or QUANTA traitait l'analyse comme un événement ponctuel :
upload → analyse → PDF → fini, alors qu'un mémoire = **6 mois sur les MÊMES
données**. Le Projet change la nature du produit : le dataset versionné, les
analyses rejouables à l'identique, la comparaison avant/après nettoyage —
l'endroit où on range son travail de recherche, celui qu'on ne quitte pas.

## 2. Conception (règle « sans casser l'existant »)

**[app/projects.py](app/projects.py)** — module ISOLÉ :
- 3 tables SQLite dédiées, `IF NOT EXISTS` → **zéro migration**, zéro touch du
  schéma de db.py :
  - `project_projects` (nom, description, hash dataset courant) ;
  - `project_dataset_versions` (version_no, file_hash sha256, filename,
    n_rows, n_cols — **idempotent par hash** : même fichier = même version) ;
  - `project_runs` (query, analysis_id, status, summary, created_at) ;
- connexion via `db.DB_PATH` (la même base, `QUANTA_DB_PATH` respecté en tests) ;
- isolation stricte par `user_id` sur **chaque** requête (comme db.py) ;
- contextmanager `_conn()` : commit/rollback + **fermeture** (le CM natif de
  sqlite3 ne ferme pas — fuite évitée) ;
- branchement dans main.py : **2 lignes** (import + `include_router`), endpoint
  existants intouchés.

### Surface API (préfixe /projects, auth `get_current_user` obligatoire)
| Endpoint | Rôle |
|---|---|
| `POST /projects` | créer (nom non vide) |
| `GET /projects` | liste (compteurs runs/versions) |
| `GET /projects/{id}` | détail avec versions + runs |
| `DELETE /projects/{id}` | suppression (cascade sur ses 3 tables seulement) |
| `POST /projects/{id}/versions` | ajouter version (idempotent par file_hash) |
| `POST /projects/{id}/runs` | enregistrer une exécution |
| `POST /projects/runs/{id}/attach` | lier l'analyse terminée + summary |
| `POST /projects/runs/{id}/replay` | **rejouer à l'identique** |
| `GET /projects/{id}/compare?version_a&version_b` | **comparaison de versions** |

### Les deux fonctions « qui font sortir du lot »
1. **Replay** : même `file_hash` + même `query` → le cache existant
   (`db.find_cached_analysis`) garantit **l'identité du résultat**. Pas de
   recalcul, pas de dérive : rejouer, c'est re-prouver. Si le cache manque,
   la réponse explique exactement quoi relancer.
2. **Compare** : delta de `score_global` + delta de p-values par test
   (paires (name, decision)) entre les derniers runs « done » de deux
   versions → « avec vs sans outliers : +5,5 points de confiance, le test
   X passe de p=0,001 à p=0,03 ».

## 3. Preuves brutes (exécutions réelles du 02/10)

### 3.1 Tests ciblés
```
python -m pytest tests/test_projects.py -q     -> 11 passed, 18.10s
```
Verrouillés : CRUD + strip du nom + nom vide rejeté ; **isolation entre
utilisateurs** (cross-user = 404 en HTTP, ValueError en métier) ; idempotence
des versions par hash ; **replay identique via cache** (même analysis_id,
même score_global) ; **compare delta confiance 82,5 → 88,0 (Δ=+5,5)** et
delta p-value 0,001 → 0,03 ; endpoints HTTP complets avec auth mockée
(pattern utilisé par les tests du repo) ; auth requise (401/403 sans session) ;
2 corrections de tests pendant l'écriture : tables préexistantes dans la
fixture + signature `picture_url` de `create_or_update_user`.

### 3.2 Non-régression globale
```
python -m pytest tests/ (hors test_quota, test_orchestrator_compare_groups)
  -> 98 passed (87 précédents + 11 nouveaux), 214.43s
python -c "import main" -> IMPORT MAIN OK
```

## 4. Non-cassage vérifié

- **main.py** : +2 lignes uniquement (import + include_router au-dessus du
  `db.init_db()` préexistant) ;
- **db.py** : zéro modification ;
- endpoints préexistants : intouchés (les routes /projects sont préfixées) ;
- tables db.py : la fixture de tests ne touche QUE les 3 tables project_* ;
- CI de branche : à confirmer sur GitHub Actions après push (feature/**).

## 5. Ce qui reste pour compléter le pilier en prod (hors périmètre code)

- **Branchement frontend** : le workspace UI (branche `feature/ui-redesign-quanta`,
  travail en cours ailleurs) devra ajouter la page Workspace (liste des
  projets, versions, runs, bouton replay). Les endpoints sont prêts pour ça.
- **Wire-up automatique** : attacher automatiquement le run quand une analyse
  demandée depuis le projet se termine (aujourd'hui l'attach se fait au
  polling ou manuellement — l'endpoint existe ; automatisable en +5 lignes
  dans /status).

## 6. État git

- Branche `feature/freebuff-piliers` (main intact).
- Commits : P1a/P1b (module + branchement + tests), P1c (rapport).
- Fichiers hérités non commités volontairement (pas à moi) :
  `scripts/investigate_bootstrap_eta2.py`, artefacts lighthouse.

## 7. Ce qui reste (avant P2)

| Pilier | État |
|---|---|
| P0 crédibilité | ✅ livré (rapport P0) |
| **P1 Projet persistant** | ✅ **livré ce tour** (backend + API + tests) |
| P2 Session conversationnelle | prochain tour (moteur `text_to_intent` existe) |
| P3 Repro Pack ZIP | à venir |
| P4 Mode Soutenance | à venir |
