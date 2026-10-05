# RAPPORT A2 — Frontend des 4 piliers : Workspace, Chat, Dossier d'audit, Soutenance

- **Date** : 05/10/2026
- **Branche** : `feature/freebuff-durcissement-plus` (les écrans consomment les endpoints piliers mergés sur `main` `f61a566` et déployés)
- **Principe** : fichiers 100 % nouveaux (aucune collision avec le chantier UI-redesign en cours), conventions du repo respectées (`useAuth`, `NEXT_PUBLIC_API_URL`, classes `quanta-*`, `glass`, `lucide-react`).

---

## 1. Ce qui a été livré

| Pilier | Écran(s) | Endpoints consommés | Fichiers |
|---|---|---|---|
| P1 Projet persistant | `/workspace` (liste + création) · `/workspace/[project_id]` (versions, runs, Replay, comparaison A/B) | `GET/POST /projects`, `GET /projects/{id}`, `POST /projects/runs/{run_id}/replay`, `GET /projects/{id}/compare` | `app/workspace/page.tsx`, `app/workspace/[project_id]/page.tsx` |
| P2 Session conversationnelle | `/conversation` (sessions, tour par tour, polling) | `GET/POST /conversations`, `GET /conversations/{id}`, `POST /conversations/{id}/ask`, `GET /status/{id}` | `app/conversation/page.tsx` |
| P3 Repro Pack | `/audit/[analysis_id]` (Dossier d'audit : fiche + ZIP dark/light) | `GET /repro_pack/{id}?theme=dark|light` | `app/audit/[analysis_id]/page.tsx` |
| P4 Mode Soutenance | `/defense` (index) · `/defense/[analysis_id]` (fiche, mémo, questions du jury, défenses, impression) | `GET /history`, `GET /defense/{id}` | `app/defense/page.tsx`, `app/defense/[analysis_id]/page.tsx` |

**Points d'entrée** :
- `app/components/SiteHeader.tsx` : 3 onglets ajoutés (Workspace, Conversation, « Préparer ma soutenance ») ; l'onglet Méthodologie ouvre `NEXT_PUBLIC_API_URL/methodologie` dans un nouvel onglet (page servie par l'API, pas par Next.js — un `Link` interne donnerait un 404).
- `app/history/page.tsx` : boutons « Soutenance » et « Dossier d'audit » sur chaque analyse terminée.
- Chaînage pédagogique intégré : Soutenance → « Pièce jointe pour le jury : dossier d'audit → » ; Audit → « Étape suivante : préparer ma soutenance → ».

**Changement backend minimal (clé additive)** : `db.list_analyses` expose désormais `file_id` par analyse — nécessaire au chat pour créer une session sur un upload existant (aucune clé retirée, aucun test ne verrouillait la shape).

## 2. Décisions d'interface notables

- **Honnêteté du mode dégradé** : dans le chat, si le LLM est indisponible, la réponse affiche explicitement « Mode dégradé : le service d'interprétation est momentanément indisponible, mais l'analyse statistique a bien été exécutée » — jamais de texte d'excuse générique ni de faux contenu.
- **Replay** : le bouton « Rejouer » affiche la garantie (« cache — mêmes valeurs garanties ») ou la raison d'échec du replay, sans masquer le message serveur.
- **Soutenance** : page imprimable (`window.print()`), mémo « dernière ligne » mis en avant, points de vigilance du Skeptic Engine affichés avec leur défense préparée.
- **Polling borné** : le chat interroge `/status/{id}` toutes les 3 s avec garde-fou d'arrêt à 3 minutes (pas de spinner infini).

## 3. Vérifications (preuves)

| Vérification | Résultat |
|---|---|
| `npx tsc --noEmit` | **0 erreur** (après correction d'un `use` manquant dans `defense/[analysis_id]`) |
| ESLint sur les 6 fichiers nouveaux/modifiés | **0 erreur** (24 → 0 : `setState` sync dans les effets différés, apostrophes → `&apos;` comme la convention du repo) |
| Suite Python liée (`test_public_pages` + `test_industrialisation`) | 9/9 passed (règression backend exclue) |
| `import db` | OK |

## 4. Limitations consignées (honnêteté)

1. **Build Next.js complet non exécuté localement** : `npm run build` dépasse 10 min sur cette machine (three.js + machine lente, timeout deux fois atteint). La vérification s'appuie sur `tsc --noEmit` (0 erreur) + ESLint (0 erreur), qui couvrent les erreurs de type et de convention ; le build de prod sera validé par le déploiement Vercel.
2. **Test E2E navigateur non automatisé** : les écrans exigent une session Google OAuth réelle (cookie) ; les parcours ont été conçus sur les contrats exacts des routers (shapes lues dans `app/projects.py`, `app/conversation.py`, `app/defense.py`, `db.py`), mais un clic-test manuel reste recommandé après déploiement.
3. **Collision de chantier évitée de justesse** : pendant le travail, un autre thread a basculé le dépôt sur `main` et créé un stash contenant des fichiers modifiés ici. Les 3 fichiers trackés touchés par A2 (`db.py`, `SiteHeader.tsx`, `history/page.tsx`) ont été récupérés du stash (extraction ciblée par `git checkout stash@{0} --`, le stash restant intact pour son propriétaire) et commités sur la branche feature. Aucun fichier du chantier UI-redesign n'a été modifié ni commité.

## 5. Conclusion

Les 4 piliers sont désormais **visibles et utilisables** dans l'interface : un pilier invisible valait zéro pour l'utilisateur. L'utilisateur peut créer un projet, rejouer une exécution à l'identique, comparer deux versions de dataset, dialoguer avec ses données tour par tour, télécharger un dossier d'audit par tiers, et entrer en soutenance avec les questions du jury et les réponses chiffrées. Le tout sans toucher au travail d'écran en cours du chantier UI-redesign.

*Fin du rapport A2.*
