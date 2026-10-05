# RAPPORT A3 — Page Méthodologie publique (comparatif honnête, distribution par le haut)

- **Date** : 05/10/2026
- **Commit** : `c5e6458` (feat A3) — branché dans `main` via `3806169`
- **Objectif distribution** : donner aux encadreurs (UAC / UL / INSAE) une page publique qui permet de décider en connaissance de cause — et transformer l'honnêteté de l'outil en argument de vente.

---

## 1. Ce qui a été livré

- **Endpoint public** : `GET /methodologie` → `HTMLResponse` 200, **sans authentification**.
- **Module** : `app/public_pages.py` (router `tags=["public"]`), câblé dans `main.py` après le router defense (`app.include_router(public_pages.router)`).
- **Zéro dépendance ajoutée** : HTML autonome construit à l'import (aucun template engine, aucun fichier statique, aucun accès DB ni LLM) → réponse **déterministe octet par octet**.

## 2. Contenu (honnêteté = argumentaire)

1. **Principe « aucune confiance par défaut »** : calcul déterministe d'abord (SciPy/Statsmodels), texte LLM ensuite, mode dégradé assumé ; traçabilité chiffre → test → règle de sélection ; multiplicité BH systématique (brut vs ajusté affichés) ; robustesse HC3 automatique sur hétéroscédasticité ; audit par Repro Pack.
2. **Règle de sélection des tests exposée** (paramétrique vs non paramétrique) — avec **transparence sur le bug `theme="both"` corrigé le jour même** : un outil qui exige la preuve s'applique la même règle à lui-même.
3. **Comparatif honnête 4 outils** (QUANTA / ChatGPT seul / Julius AI / SPSS) : colonnes « oui » pour QUANTA mais aussi ses **« non » assumés** (tests avancés hors périmètre, pas de substitution à un cours de stats, pas de garantie de significativité, LLM pas une source).
4. **Section « Ce que QUANTA ne fait pas »** explicite.
5. **6 arguments pour l'encadreur** : anti p-hacking par construction, soutenances préparées sur les propres chiffres de l'étudiant, audit d'un mémoire en minutes (Repro Pack), pédagogie par la traçabilité, zéro licence/installation, limites publiées = crédibilité.
6. **Preuves chiffrées** (§5 de la page) : 19,1 s vs 198,7 s, 126 tests sans exclusion, endpoints 401-protégés en prod.

## 3. Vérifications

| Vérification | Résultat |
|---|---|
| `tests/test_public_pages.py` | **4/4** : 200 sans auth + HTML fr autonome, comparatif complet (4 outils, colonnes « non » présentes), déterminisme octet par octet (2 GET identiques), pureté (aucune dépendance DB/LLM) |
| Suite Python liée (re-run avec A2) | 9/9 |
| CI sur `main` | success (`3806169`, puis `e5f3bc6`) |
| **Prod** | `https://quanta-ijmg.onrender.com/methodologie` → **200** ; contenu vérifié en prod (grep : comparatif, Benjamini-Hochberg, « Ce que QUANTA ne fait pas ») |

## 4. Décisions notables

- **Lien depuis le frontend** : l'onglet « Méthodologie » du header Next.js ouvre `NEXT_PUBLIC_API_URL/methodologie` dans un nouvel onglet (lien `<a>` externe, pas `Link` interne — la page vit sur l'API, un routage Next donnerait un 404 Vercel).
- **Statique et déterministe par design** : la page n'a ni session, ni quota, ni rate-limit applicatif spécifique (limiteur global de l'app seulement) — elle doit pouvoir être citée dans un email à un encadreur sans pré-requis.
- **Publication du bug corrigé** : choix assumé — documenter une faute corrigée renforce la position « preuves, pas promesses ».

## 5. Limitations consignées

1. `/openapi.json` renvoie 500 en prod (anomalie découverte pendant les sondes A1, indépendante de la page) — ticket ouvert, non bloquant.
2. La page est en français uniquement (audience cible UAC/UL/INSAE) ; une version EN reste à produire si la distribution s'élargit.
3. Suite au passage en prod du fix A4, le texte (19,1 s ; bug corrigé le 05/10/2026) devra être re-daté aux prochaines évolutions chiffrées.

*Fin du rapport A3.*
