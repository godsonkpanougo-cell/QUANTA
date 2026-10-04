# RAPPORT P4 — PILIER 4 : MODE SOUTENANCE — et BILAN FINAL DES 4 PILIERS

> Date : 02/10/2026 — Exécution : Buffy (Freebuff). Mandat : « continuer les
> 4 piliers, un rapport par action, sans casser l'existant, rapports dans un
> même dossier » — rapport n°5 et dernier de `RAPPORTS_PILIERS/`.

---

## 1. Pourquoi ce pilier (rappel de l'arbitrage)

L'indispensabilité se décide sur les moments de vérité : **la veille de la
défense**. Le Mode Soutenance génère les questions probables du jury AVEC LES
RÉPONSES CHIFFRÉES tirées de l'analyse persistée, plus les défenses aux points
de vigilance que le Skeptic Engine a déjà identifiés. Aucun concurrent ne peut
le faire : ils n'ont pas la rigueur statistique sous-jacente — donc rien de
fiable à citer. Pour le public visé, c'est la fonction dont on parle entre
étudiants.

## 2. Conception (règle « sans casser l'existant »)

**[app/defense.py](app/defense.py)** — module ISOLÉ :
- **AUCUNE table nouvelle** (lit l'analyse via `db.get_analysis`) ;
- **ZÉRO LLM, ZÉRO recalcul** : génération DÉTERMINISTE, instantanée, sans
  coût API et sans risque de timeout (compatible budget Render) ;
- **ZÉRO chiffre inventé** : chaque réponse reformule des valeurs extraites
  du résultat persisté et porte son champ `source` (chemin JSON) — la
  soutenance reste AUDITABLE, cohérente avec le Repro Pack (P3) ;
- s'adapte à ce que l'analyse contient réellement : sections absentes omises ;
- gère les deux formes de persistance (pipeline direct ou emboîté
  `result.analysis` de brain.analyze_with_brain) ;
- branchement main.py : **2 lignes** (import + include_router).

### Contenu du pack (`GET /defense/{analysis_id}`)
| Bloc | Contenu |
|---|---|
| `fiche_identite` | fichier, n_rows/n_cols, requête, test exécuté, score de confiance |
| `questions_probables` | 5-6 questions-types : choix du test (justifié par la normalité), robustesse (statistique, p, décision, **taille d'effet + IC bootstrap + puissance**), faux positifs (**1025 brut → 1010 après correction FDR du P0, méthode citée**), taille d'échantillon (plafond de confiance cité), préparation des données (audit_log), normalité |
| `defenses_points_de_vigilance` | une stratégie de réponse par point du Skeptic Engine (aucun chiffre inventé — renvoie aux données qui bornent) |
| `memo_derniere_ligne` | les 3 chiffres à avoir en tête en entrant dans la salle (p principal, score de confiance, corrélation la plus forte avec q) |

## 3. Preuves brutes (exécutions réelles du 02/10)

### 3.1 Tests ciblés — `python -m pytest tests/test_defense.py -q`
```
4 passed, 10.84s  (2e exécution : 4 passed — stables)
```
Verrouillés : chaque réponse CHIFFRÉE provient de la persistance
(p=0.0089, Mann-Whitney, effet 0.41 IC [0.18 ; 0.62], puissance 0.87,
1025→1010, n=301, 82.4, winsorize_outliers — toutes valeurs du résultat
de test) ; champ `source` présent sur chaque question ; **déterminisme**
(2 appels → dicts identiques) ; emboîtement brain unwrappé ; résultat
minimal (sans inférence) produit quand même un pack ; 404 introuvable,
400 non terminée, HTTP 200/404 cross-user/401-403.

### 3.2 Non-régression globale
```
python -m pytest tests/ (hors test_quota, test_orchestrator_compare_groups)
  -> 117 passed (113 + 4), 216.68s
python -c "import main" -> IMPORT MAIN OK
```

### 3.3 Dette technique PAYÉE au passage (cause, pas contournement)
Une instabilité inter-runs de la suite complète est apparue (1 échec
intermittent, puis aggravation à 9/18 lors de runs rapprochés). Diagnostic :
la DB de test **persiste entre les runs pytest** alors que mes fixtures de
tests P1/P2/P4 utilisaient des identités déterministes — collision UNIQUE sur
`users.email` (colonne UNIQUE vérifiée dans db.py) et sur uploads/analyses
après run interrompu. Correctif sur la cause : identités et ids uniques par
run dans les 3 fichiers de tests piliers. **24/24 ×3 runs consécutifs** puis
**117/117** en suite complète.

## 4. Non-cassage vérifié

- main.py : +2 lignes additives (import + include_router `/defense`) ;
- db.py, /analyze, /status, /report, /projects, /conversations, /repro_pack :
  **zéro modification** ; zéro table nouvelle ;
- les seuls fichiers de tests modifiés : corrections d'ids uniques (ci-dessus),
  aucune assertion affaiblie.

## 5. BILAN FINAL DU CHANTIER DES 4 PILIERS (P0→P4)

| Pilier | Livrable | Tests | CI | Rapport |
|---|---|---|---|---|
| P0 crédibilité | Holm/BH corrigés (bug monotonies échangées) + deadline LLM par provider ; L2_tobit : 1025 sig brut → 774 Holm / 1010 FDR | 11/11 | verte `141f7c1` | RAPPORT_P0_CREDIBILITE.md |
| P1 Projet persistant | versions de dataset (idempotentes par sha256), replay à l'identique, comparaison de versions | 11/11 | verte `f2e3d06` | RAPPORT_P1_PROJET_PERSISTANT.md |
| P2 Session conversationnelle | parler à ses données sans re-upload (cache → quota → worker DI), intégré aux Projets | 9/9 | verte `36e7fc2` | RAPPORT_P2_SESSION_CONVERSATIONNELLE.md |
| P3 Repro Pack | ZIP d'audit : README sha256+versions+seeds, resultats.json exact, données+PDF+scripts | 6/6 | verte `b22c508` | RAPPORT_P3_REPRO_PACK.md |
| **P4 Mode Soutenance** | questions du jury + réponses chiffrées citées + défenses Skeptic + mémo, déterministe | 4/4 | ce push | ce rapport |

**Suite complète finale : 117/117 — zéro régression, zéro table migrée,
modules tous isolés (branchements main.py cumulés : ~10 lignes additives).**

### Ce qui reste (hors périmètre backend, à coordonner)
1. **Merge** `feature/freebuff-piliers` → main (validation directeur/Windsurf) ;
2. **Frontend** : page Workspace (P1), chat (P2), bouton « Dossier d'audit » (P3),
   onglet « Préparer ma soutenance » (P4) — tous les endpoints sont prêts ;
3. Re-test prod L2_tobit après déploiement Render (attendre les TIMING
   `ACM plots generation < 15 s`, `correlation pairs (vectorized) < 2 s`) ;
4. Exclusions pytest préexistantes hors périmètre : `test_quota`,
   `test_orchestrator_compare_groups` ; hérités non commités (pas à moi) :
   `investigate_bootstrap_eta2.py`, artefacts lighthouse.
