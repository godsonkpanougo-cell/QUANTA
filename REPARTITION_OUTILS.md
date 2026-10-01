# RÉPARTITION DES OUTILS — WINDSURF / FREEBUFF (règle de projet, à partir du 2026-10-01)

> Fait suite à l'incident du 30/09 : deux outils ont écrit simultanément dans `main.py`
> sans frontière claire, et aucun CI n'a rattrapé le mélange (commit `import app.billing`
> non fonctionnel). La règle n'est pas « Freebuff a le droit à X sujets » mais une
> **séparation par fichiers/branches**, plus stricte qu'avant. Ce document fait foi.
> État git vérifié à la rédaction : `main` local = `origin/main` = `0406933`
> (réaligné par fast-forward après un `reset` local vers 056e537 ; aucune perte),
> `import main` OK.

---

## 1. WINDSURF — exécuteur produit, sur `main`

- Reste l'implémenteur des chantiers définis par le directeur (Godson + Claude/Buffy) en
  consignes `.md`/prompts **précis, autonomes et autocontextualisées**, avec preuve brute
  exigée (logs, sorties de commandes, diffs) — comme jusqu'à présent.
- Branches : `main`, ou branches de feature courtes **fusionnées vite** sur `main`.
- Prochaines tâches disponibles une fois le git remis d'aplomb (tirées de
  `QUANTA_STATISTICAL_COVERAGE_MATRIX.md`, hors paywall/annulation/timeout) :
  1. combler les items de couverture statistique déjà identifiés ;
  2. le point de vérification jamais fait : **audit accessibilité réel** (pas déclaratif).
- **Fichiers interdits** tant que le paywall n'est pas repris explicitement :
  `app/billing.py`, `db.py` (partie billing), `report_generator.py` / `pdf_worker.py`
  (partie watermark/branding).

## 2. FREEBUFF — deux casquettes séparées, JAMAIS mélangées dans le même run

### Casquette 1 — Auditeur / second avis (rôle par défaut)
- Revue de ce que Windsurf livre : vérification forensique (`git log`, `git show`,
  `git status`, greps, relance des tests), verdict directeur avant merge sur `main`.
- Chaque livraison Windsurf importante passe par une revue Freebuff avant merge.
- Expérience validée : forensique rigoureuse, preuve à chaque étape, pas de complaisance
  (voir `RATTRAPAGE_CLAUDE_2026-10-01.md` — deux résumés Windsurf sur trois se sont avérés
  inexacts : décompte pytest faux, moitié du travail non committée, chiffres invérifiables).

### Casquette 2 — Exécuteur isolé, sur sa propre branche
- Uniquement des tâches propres qui ne touchent ni aux fichiers du paywall, ni à `main.py`,
  ni à `orchestrator.py`/`compute.py` **en même temps que Windsurf y travaille**.
- Périmètres naturels : le repo frontend (`quanta-frontend/`), les tests (`tests/`),
  la documentation.
- **Jamais directement sur `main`** : toujours sur une branche `feature/freebuff-<sujet>`.

## 3. RÈGLE COMMUNE AUX DEUX OUTILS (pour que l'incident ne se reproduise pas)

1. **Condition d'entrée, pas vérification a posteriori** : chaque commit de chaque outil doit
   pouvoir répondre « quel est le diff exact et pourquoi », avec
   `python -c "import main"` vérifié **avant tout push**.
2. **Frontière de fichiers** : si une tâche nécessite de toucher un fichier du périmètre de
   l'autre outil → mandat explicite du directeur d'abord.
3. **Interdiction permanente** : `git push --force` (règle déjà posée après le force push du
   30/09 ; squash local AVANT push uniquement).
4. Un seul commit par tâche validée, preuves brutes collées dans le rapport, stop point avant
   tout correctif non mandaté.

## 4. SUJETS GELÉS (aucun des deux outils n'y touche)

- **Paywall** : exclusivement en `feature/paywall-wip` (6db8a98), **non commité sur main** tant
  que Godson n'a pas tranché Stripe / Bénin / statut juridique. Mandat explicite requis.
- **Annulation d'analyse et timeout worker** : gelés, non assignés, jusqu'à ce que Godson
  fournisse `L2_tobit.dta` ou relance le sujet lui-même.

---

## Rappel d'état (pour situer la répartition)

- Tâche A (déduplication ACM + fix PDF + TIMING) : **livrée et validée** (`0406933`, CI verte,
  déploiement Render à confirmer par marqueurs `TIMING - ACM ...` sur le prochain run).
- Tâche C (TIMING interprétation LLM + re-test budget + test timeout) : **consigne autonome
  déjà rédigée**, à donner à Windsurf quand le directeur décide de la lancer.
- Détails complets : `RATTRAPAGE_CLAUDE_2026-10-01.md`.
