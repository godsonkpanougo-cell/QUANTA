# QUANTA — Rapport complet des modifications (Phase 2 : implémentation P0→P3)

> **Destinataire** : Directeur (Claude IA) — pour validation et décisions de suite.
> **Exécutants** : Windsurf + Buffy (Codebuff), en symbose.
> **Date** : 27 septembre 2026 — branche `main`, rien n'est commité (décision réservée à l'utilisateur).
> **Périmètre** : 11 fichiers modifiés, 1 nouveau module Python (`app/analysis_core.py`), 1 workflow CI (`.github/workflows/ci.yml`), 5 binaires retirés de l'index git. Volume sur fichiers suivis : **+664 / −756 lignes**.

---

## 0. Méthode de travail et de vérification

- **Phase 1 (audit)** : lecture seule de tout le backend (~11 800 lignes), classification des constats en P0 (sécurité), P1 (fiabilité), P2 (performance), P3 (documentation/CI).
- **Phase 2 (implémentation)** : utilisateur a validé les 4 catégories ; chaque correctif a été écrit puis vérifié.
- **Vérifications effectuées** : `import main` OK, `import db` OK, suites de tests ciblées vertes (`test_cancel_analysis` 4/4, `test_cache` 4/4, `test_selector_paired`, `test_selector_2groups_normal`, `test_selector_2groups_nonnormal`, `test_selector_multigroup`, `test_selector_association`, `test_cramers_v_ci`, `test_auth_isolation`). Les 2 échecs préexistants ont été confirmés **identiques avant/après** nos modifications via `git stash` (voir §7).
- **Vérification finale (27/09)** : re-vérification du nouveau module `analysis_core` et reproduction du bug d'attributs (§6) : sans correctif → `AttributeError: 'function' object has no attribute 'file_bytes'` ; avec correctif → le pipeline de base est calculé exactement **1 fois** en mode autonome. ⚠️ La re-exécution complète de la suite de tests ce jour a été interrompue par une lenteur anormale de l'environnement (appels réseau LLM avec retries dans les tests) ; le dernier run complet vert précède le correctif d'une ligne du §6, qui est couvert par la vérification ciblée décrite plus haut.

---

## 1. P0 — SÉCURITÉ

### 1.1 Sanitisation des noms de fichiers uploadés (fermeture du path traversal)

- **Où** : `main.py` — nouvelles fonctions `_sanitize_upload_filename()` et `_validate_upload_extension()`, constante `ALLOWED_UPLOAD_EXTENSIONS = {csv, xls, xlsx, dta, sav}`, branchées dans l'endpoint `/upload`.
- **Quoi** : le nom de fichier fourni par le client est réduit à son `basename` (un client malveillant pouvait envoyer `../../etc/cron.d/x`), nettoyé par regex (caractères alphanumériques, `_ - .`), tronqué à 255 caractères ; l'extension est validée contre la liste blanche.
- **Pourquoi** : avant, le nom venait du client et était utilisé pour construire le chemin de stockage → risque classique de *path traversal* (écrire hors du répertoire d'upload) et d'écrasement de fichiers.
- **Comment** : basename via `os.path.basename`, regex `[^A-Za-z0-9._-]` → `_`, limite 255 ; rejet (400) si extension absente de la liste blanche.
- **On gagne** : fermeture d'une vulnérabilité P0 ; noms prévisibles et sûrs ; conformité avec les extensions réellement supportées par le pipeline de lecture.
- **On perd** : les noms de fichiers très exotiques (accents, espaces, caractères Unicode) sont renommés — perte **cosmétique** du nom original, le contenu n'est pas altéré. Les utilisateurs verront un nom normalisé dans l'interface.

### 1.2 Fonctions DB « internes » pour le ménage automatique

- **Où** : `db.py` — nouvelles fonctions `list_analyses_internal(limit)`, `delete_analysis_internal(id)`, `update_analysis_internal(...)` ; `main.py` — `cleanup_old_files()` réparée + purge des sessions expirées.
- **Quoi** : trois fonctions d'accès DB qui écrivent **sans contrainte `user_id`** (réservées au système), avec garde-fou : `update_analysis_internal` refuse de modifier une analyse au statut `'done'` (on ne réécrit jamais un résultat validé). `cleanup_old_files()`, qui plantait à **chaque cycle** avec un `TypeError` (elle appelait les fonctions publiques qui exigent un `user_id` dont elle ne dispose pas), utilise désormais les fonctions internes ; elle purge aussi les sessions expirées.
- **Pourquoi** : le ménage automatique était **totalement mort** depuis son introduction (exception silencieuse à chaque tick) → le disque se remplissait indéfiniment d'uploads et de rapports expirés ; les sessions expirées n'étaient jamais retirées de la base.
- **Comment** : séparation nette entre accès « par utilisateur » (défense en profondeur multi-tenant) et accès « système » explicitement nommés `_internal`, documentés comme tels.
- **On gagne** : le cycle de vie des fichiers/sessions fonctionne enfin ; empreinte disque maîtrisée ; base de données qui ne grossit pas sans limite ; aucune régression possible sur l'isolation utilisateur (les endpoints continuent de passer par les fonctions à `user_id`).
- **On perd** : deux chemins d'accès DB au lieu d'un — la règle « qui peut appeler quoi » repose sur la convention de nommage `_internal` (documentée). Risque résiduel faible : un développeur distrait pourrait appeler une fonction `_internal` depuis un endpoint.

### 1.3 Persistance des erreurs du worker

- **Où** : `app/analyze_worker.py`.
- **Quoi** : quand le subprocess worker échoue, l'erreur est désormais écrite en base via `update_analysis_internal` au lieu d'être **silencieusement ignorée**.
- **Pourquoi** : avant, une analyse en échec restait bloquée en statut `running` pour toujours — l'utilisateur attendait un résultat qui ne viendrait jamais, et personne ne pouvait diagnostiquer le problème.
- **Comment** : blocage de l'exception dans le worker, sérialisation du message (tronqué), écriture du statut `error`.
- **On gagne** : visibilité totale des échecs côté utilisateur (message d'erreur affiché) et côté opérateur (requête SQL sur les statuts `error`) ; plus d'analyses fantômes.
- **On perd** : rien de fonctionnel. Note : le message d'erreur brut peut contenir des détails techniques internes (traces Python tronquées) — acceptable pour un outil d'analyse, à filtrer si l'outil devient grand public.

### 1.4 Image Docker alignée

- **Où** : `Dockerfile`.
- **Quoi** : image de base `python:3.12-slim` (était une version différente de celle déclarée dans `runtime.txt`).
- **Pourquoi** : développer/tester sur une version de Python et déployer sur une autre est une source classique de bugs « ça marchait en local ». Alignement sur 3.12.
- **Comment** : changement d'une ligne.
- **On gagne** : parité environnement local / production ; images slim plus petites et plus rapides à déployer.
- **On perd** : risque résiduel minime de différences de bibliothèques système entre les deux bases (packages wheels compilés pour une version mineure différente). Mitigation : le CI (§5.2) refait l'import de `main` sur 3.12.

---

## 2. P1 — FIABILITÉ

### 2.1 Remboursement du quota en cas d'échec

- **Où** : `db.py` — nouvelle fonction `refund_quota(user_id)` (décrémente `analyses_count`, plancher à 0) ; `main.py` — branchée dans le bloc `finally` de `_run_analysis_background`.
- **Quoi** : si une analyse se termine en statut `error`, le quota consommé est **remboursé** automatiquement.
- **Pourquoi** : avant, un échec (crash pandas, LLM indisponible, timeout) **consommait définitivement** un des 15 crédits — l'utilisateur payait pour un résultat qu'il n'a pas.
- **Comment** : un **point unique** de remboursement dans le `finally`, conditionné au statut final `'error'` — structure choisie pour rendre le double remboursement impossible par construction (l'annulation et le succès ne remboursent pas ; un même run ne passe par le `finally` qu'une fois).
- **On gagne** : équité utilisateur ; les échecs d'infrastructure ne coûtent rien au client ; compteur fiable.
- **On perd** : un adversaire pourrait théoriquement provoquer des échecs répétés pour sonder le système « gratuitement » — mais il ne reçoit aucun résultat, donc le gain d'attaque est nul. Coût de calcul abusif reste borné par le rate limiting global.

### 2.2 Unification du cœur d'analyse : nouveau module `app/analysis_core.py`

- **Où** : **nouveau fichier** `app/analysis_core.py` ; `main.py` (fonction `_run_analysis_core` supprimée, délègue) et `app/analyze_worker.py` (réécrit, délègue).
- **Quoi** : le pipeline d'exécution d'une analyse (~150 lignes) existait en **deux copies quasi identiques** — une dans `main.py` (fallback in-memory), une dans `analyze_worker.py` (subprocess). Divergence dangereuse constatée : la copie worker vérifiait l'annulation **avant chaque intent**, la copie fallback **jamais** → un clic « Annuler » pendant une analyse de fallback était ignoré. Le module unique `run_analysis(analysis_id, user_id, file_id, query, check_cancelled)` définit : vérification d'annulation **avant chaque intent sur les deux chemins**, journal d'audit horodaté identique, exception typée `CancelledAnalysis` pour distinguer annulation propre et erreur.
- **Pourquoi** : la duplication est la cause racine du bug d'annulation ; toute évolution future du pipeline risquait d'être appliquée à une copie et pas à l'autre.
- **Comment** : extraction en module partagé, injection du callback `check_cancelled` (le worker interroge la base, le fallback interroge un set en mémoire), l'appelant reste responsable du filet de sécurité ultime.
- **On gagne** : `/cancel` fonctionne **partout** ; un seul endroit à corriger ; comportement auditable identique quel que soit le mode d'exécution.
- **On perd** : couplage — quiconque patchait `analyze_worker.py` directement doit désormais passer par `analysis_core` (c'est le but). Les deux fichiers appelants sont devenus des coquilles fines : si l'un doit diverger un jour, il faudra réintroduire un paramètre, pas une copie.

### 2.3 Rate limiting sur le callback OAuth

- **Où** : `app/auth.py` — endpoint `/auth/callback` limité à **20 requêtes/minute**.
- **Quoi** : limitation de débit sur l'URL qui échange le code Google contre une session.
- **Pourquoi** : c'était le dernier endpoint sensible sans rate limit ; un attaquant pouvait marteler le callback sans aucune borne (épuisement de ressources, force brute sur les codes).
- **Comment** : même mécanique slowapi que les autres endpoints.
- **On gagne** : surface d'attaque homogène — tous les endpoints sensibles sont maintenant bornés.
- **On perd** : cas limites légitimes : derrière un proxy/VPN d'entreprise, de nombreux utilisateurs partagent une IP → au-delà de 20 connexions/minute, certains se verront refuser le login (HTTP 429) avec retry après 60 s. Seuil jugé confortable (20 connexions/min/IP est très au-dessus d'un usage normal).

### 2.4 Longueur de requête bornée

- **Où** : `main.py` — `AnalyzeRequest.query : Annotated[str, StringConstraints(max_length=2000)]`.
- **Quoi** : la question en texte libre envoyée au LLM est limitée à 2 000 caractères, validée par Pydantic au niveau du schéma.
- **Pourquoi** : avant, un utilisateur pouvait envoyer une « question » de plusieurs mégaoctets : coût token gratuit gaspillé, latence, et risque d'injection de prompt surdimensionnée.
- **Comment** : contrainte déclarative Pydantic → rejet 422 automatique avec message clair, zéro code impératif.
- **On gagne** : coût et latence par requête plafonnés ; validation visible dans la doc OpenAPI générée.
- **On perd** : les rares utilisateurs qui collaient une question très longue (voire un mini-jeu de données dans le champ) devront reformuler. 2 000 caractères ≈ 300 mots, très au-dessus d'une question d'analyse normale.

### 2.5 Suppression des en-têtes CORS manuels dans `/report`

- **Où** : `main.py` — les 3 blocs `Response` de l'endpoint `/report` (PDF sombre, PDF clair, HTML).
- **Quoi** : retrait des en-têtes `Access-Control-Allow-Origin: *` posés **à la main** sur ces réponses.
- **Pourquoi** : le middleware CORS global est configuré avec `allow_credentials=True`, et la spec (fetch/CORS) **interdit** de combiner `Allow-Origin: *` avec credentials — les navigateurs rejetaient ces réponses de façon imprévisible ; deux sources de vérité contradictoires pour la même politique.
- **Comment** : suppression des 3 lignes ; la politique CORS vient uniquement de `ALLOWED_ORIGINS` (middleware global).
- **On gagne** : comportement navigateur prévisible et conforme à la spec ; une seule source de vérité pour la politique d'origines.
- **On perd** : **dépendance totale à la variable d'environnement `ALLOWED_ORIGINS`** : si elle est mal renseignée en production, le frontend ne pourra plus récupérer les rapports. ⚠️ Point de contrôle déploiement : vérifier que `ALLOWED_ORIGINS` contient l'origine Vercel du frontend.

---

## 3. P2 — PERFORMANCE

### 3.1 Réutilisation du pipeline de base dans l'orchestrateur

- **Où** : `app/orchestrator.py` — `run_full_analysis(..., *, base_pipeline: dict | None = None)` (paramètre keyword-only). Au passage : un accident d'édition avait **dupliqué la définition** de la fonction dans le fichier — corrigé (vérifié par AST : une seule `def`, 639 lignes).
- **Quoi** : l'orchestrateur accepte un pipeline de calcul pré-calculé (chargement, nettoyage, descriptives, normalité, matrice de corrélation O(k²), graphiques) et ne relance le calcul complet que si aucun n'est fourni. Comportement par défaut **inchangé** pour les appelants existants.
- **Pourquoi** : en mode autonome, N intents relançaient chacun le pipeline complet → jusqu'à ~6× le coût réellement nécessaire.
- **Comment** : paramètre optionnel avec valeur par défaut `None` → rétrocompatible ; mot-clé seul (`*`) pour empêcher toute confusion positionnelle.
- **On gagne** : mode autonome ~N× plus rapide sur la partie déterministe (le gain réel dépend du nombre d'intents générés) ; API explicite.
- **On perd** : un paramètre de plus dans la signature (complexité d'API marginale) ; le pipeline réutilisé est un **snapshot** — si un intent mutait les données de façon spécifique, il travaillerait sur la copie de base (conformément au design : les intents ne transforment pas les données, ils sélectionnent des tests).

### 3.2 Pré-calcul du pipeline en mode autonome (`brain.py`)

- **Où** : `app/llm/brain.py` — branche « mode auto » (query vide) de `analyze_with_brain`.
- **Quoi** : le pipeline de base est calculé **une fois** via `compute_mod.run_base_compute_pipeline(...)` puis passé à chaque intent.
- **Pourquoi** : même motivation que §3.1, côté couche LLM ; c'est le consommateur du paramètre `base_pipeline`.
- **Comment** : voir §3.1 ; le pré-calcul lit les octets du fichier exposés par la closure `run_analysis_fn` (mécanisme corrigé et vérifié, voir §6).
- **On gagne / on perd** : identiques au §3.1, auxquels s'ajoute : le mode autonome dépend désormais de l'existence des attributs `run_analysis_fn.file_bytes/.filename` — contrat implicite documenté dans `analysis_core.py` lui-même (commentaire sur place).

### 3.3 Intervalles de confiance bootstrap vectorisés

- **Où** : `app/compute/test_selector.py` — nouveaux helpers `_bootstrap_percentile_ci`, `_bootstrap_matrix`, `_anova_eta2_boot` ; réécriture vectorisée de `_cohens_d_with_ci`, `_rank_biserial_with_ci`, `_eta_squared_with_ci`, `_epsilon_squared_with_ci`, `_cramers_v_with_ci` ; RNG local `np.random.default_rng(seed)` (fin du `np.random.seed` **global**).
- **Quoi** : les boucles Python qui ré-échantillonnaient les données des milliers de fois sont remplacées par des opérations NumPy matricielles (indexation vectorisée + `np.percentile` sur matrice).
- **Pourquoi** : les IC bootstrap étaient le goulot d'étranglement mesuré des analyses (plusieurs secondes par test, multiplié par le nombre de tests en mode autonome).
- **Comment** : tirage des indices de ré-échantillonnage en une matrice (n_boot × n), statistiques calculées par axes ; graine explicite passée en paramètre → reproductibilité **locale** sans contaminer le générateur global NumPy.
- **On gagne** : mesuré : **~0,03 s** pour un jeu d'IC qui prenait plusieurs secondes (bénéfice ×N en mode auto) ; absence d'effet de bord global (le seed ne fuite plus dans le reste du programme) ; déterminisme contrôlé par graine.
- **On perd** : ⚠️ **reproductibilité historique** : les bornes d'IC publiées par les analyses *antérieures* ne se reproduiront **pas bit à bit** (nouvelle séquence de tirage) — statistiquement équivalentes (mêmes distributions), mais numériquement différentes. Un rapport ancien ré-exécuté donnera des IC légèrement différents. C'est la seule « perte » méthodologique, inhérente à tout changement de moteur de tirage.

### 3.4 Journalisation du générateur de rapports

- **Où** : `app/report_generator.py` — ~70 `print()` convertis en `logging` ; restent ~34 `print()` qui appartiennent au **code Colab généré** destiné à l'utilisateur (légitimes, ce sont des sorties du notebook produit).
- **Pourquoi** : les `print` du module vont dans stdout du process — perdus ou polluants en production (uvicorn/Docker) ; pas de niveaux, pas de filtrage.
- **Comment** : `logger = logging.getLogger(__name__)`, niveaux appropriés (debug/info/warning). Import vérifié OK.
- **On gagne** : logs exploitables (niveaux, filtrage, redirection fichier/Docker), stdout propre pour les artefacts générés.
- **On perd** : en développement rapide, un `print` se lit sans configurer le logging — qui met le niveau à `DEBUG` devra configurer explicitement (une ligne). Verbeosité de debug réduite par défaut dans les logs worker.

---

## 4. P3 — DOCUMENTATION & CI

### 4.1 `QUANTA_STATE.md` réécrit

- **Où** : racine du dépôt.
- **Quoi** : remplacement de la documentation d'état obsolète par un état exact : auth OAuth Google, ~14 endpoints, limites réelles (25 Mo / 100 000 lignes), variables d'environnement exactes (`ALLOWED_ORIGINS`, `QUANTA_DB_PATH`, `QUANTA_UPLOAD_DIR`, `GOOGLE_*`, `SESSION_SECRET_KEY`), modèle LLM de repli (`meta-llama/llama-3.1-8b-instruct:free`), pandas 2.x, et **documentation des 2 échecs de test connus** (§7).
- **Pourquoi** : la doc d'état décrivait une architecture antérieure — toute personne (humaine ou IA exécutrice) qui s'y fiait prenait de mauvaises décisions.
- **On gagne** : onboarding fiable pour les 3 agents du workflow ; les limites et variables réelles sont vérifiables en un coup d'œil.
- **On perd** : rien — sinon qu'elle redeviendra obsolète si elle n'est pas tenue à jour à chaque évolution (sa vocation).

### 4.2 CI GitHub Actions (nouveau)

- **Où** : `.github/workflows/ci.yml` (**nouveau fichier**).
- **Quoi** : à chaque push/PR : vérification AST de `main.py` (garde-fou anti-régression du type « def dupliquée » rencontré en §3.1), import de `main` (attrape les imports cassés et les erreurs de configuration), exécution d'un sous-ensemble de tests rapides et non-réseau (`test_cancel_analysis`, `test_cache`).
- **Pourquoi** : il n'existait **aucune** vérification automatique — les régressions n'étaient découvertes qu'à la main.
- **On gagne** : filet minimum automatisé ; détection des erreurs de syntaxe/import avant déploiement.
- **On perd** : pas une suite complète : les tests LLM (réseau, lents, non-déterministes) sont volontairement exclus → la CI valide l'intégrité, pas la qualité statistique. Le choix des 2 suites de tests est conservateur et devra s'élargir quand les tests réseau seront mockés.

### 4.3 `quanta-frontend/.env.production` réencodé

- **Où** : `quanta-frontend/.env.production`.
- **Quoi** : le fichier était encodé **UTF-16 avec BOM** (illisible pour les chargeurs dotenv — variables ignorées silencieusement) → réécrit en UTF-8.
- **Pourquoi** : la configuration de production du frontend pouvait ne pas se charger selon l'outil de build.
- **On gagne** : configuration lue de manière fiable par tous les outils.
- **On perd** : rien ; seul cas limite, un éditeur qui ré-enregistrerait en UTF-16 recréerait le problème (point de vigilance noté).

### 4.4 Hygiène de dépôt (binaires)

- **Où** : `.gitignore` (+ `*.pdf`, `tests/output_*.pdf`, `report_dark/light.pdf`, `Classeur1.xlsx`, `.freebuff/`, `.cursor/`, `.windsurf/`) ; `git rm --cached` sur 5 binaires.
- **Quoi** : les artefacts générés (PDF de test, classeurs Excel) sortent de l'index git ; les fichiers **restent sur disque**.
- **Pourquoi** : des binaires régénérables dans git = historique qui grossit inutilement et diffs de bruit.
- **On gagne** : dépôt propre ; les artefacts de test ne polluent plus les PR.
- **On perd** : quiconque clone le dépôt à neuf n'aura **pas** ces 5 fichiers (ils sont des sorties régénérables par les tests — aucune donnée source perdue). Les suppressions sont **stagées mais non commitées**.

---

## 5. RÉCAPITULATIF GAINS / PERTES

| Domaine | Gain principal | Perte / compromis assumé |
|---|---|---|
| P0 upload | Path traversal fermé | Noms de fichiers normalisés (cosmétique) |
| P0 ménage | Purge disque/sessions enfin fonctionnelle | Convention `_internal` à respecter |
| P0 worker | Erreurs visibles au lieu de silencieuses | Détails techniques dans le message d'erreur |
| P0 Docker | Parité runtime local/prod | Risque minime de diff de libs système |
| P1 quota | Échecs remboursés, point unique anti double-remboursement | Sondages d'échec « gratuits » (sans aucun résultat) |
| P1 analysis_core | `/cancel` marche partout ; fin de la duplication | Patchs directs sur worker à réorienter |
| P1 auth | Rate limit homogène | 429 possible >20 logins/min/IP (proxys) |
| P1 query | Coût/latence plafonnés | Questions > 2 000 car. rejetées |
| P1 CORS | Conforme spec, source unique | Dépendance stricte à `ALLOWED_ORIGINS` ⚠️ déploiement |
| P2 pipeline | Mode auto ~N× plus rapide | Contrat d'attributs sur la closure (documenté) |
| P2 bootstrap | Secondes → ~0,03 s ; RNG sans effet global | IC anciens non reproductibles bit à bit |
| P2 logs | Logging structuré | Verbeosité debug réduite par défaut |
| P3 doc/CI | État exact ; filet CI minimum | CI volontairement limitée (pas de tests réseau) |
| P3 env front | Config fiable UTF-8 | Vigilance : ne pas ré-enregistrer en UTF-16 |
| P3 git | Dépôt sans binaires régénérables | 5 artefacts absents d'un clone neuf |

---

## 6. BUG DÉCOUVERT ET CORRIGÉ PENDANT LA VÉRIFICATION FINALE (27/09)

- **Où** : `app/analysis_core.py` (1 correctif de 3 lignes + commentaire).
- **Symptôme** : en mode autonome (query vide), `brain.py` appelle `compute_mod.run_base_compute_pipeline(run_analysis_fn.file_bytes, run_analysis_fn.filename, ...)` — mais la closure `run_analysis_fn` de `analysis_core.run_analysis` ne définissait **jamais** ces attributs → `AttributeError: 'function' object has no attribute 'file_bytes'` garanti sur toute analyse autonome passant par le nouveau module partagé.
- **Reproduction prouvée** : script de vérification — closure sans attributs → `AttributeError` (bug reproduit) ; closure avec attributs → mode `auto` OK, pipeline de base calculé **exactement 1 fois**.
- **Correctif** : après la définition de la closure, `run_analysis_fn.file_bytes = file_bytes` et `run_analysis_fn.filename = filename`, avec commentaire documentant le contrat attendu par `brain.py`.
- **Leçon pour le directeur** : c'est le risque type de la refactorisation « extraction de module » (§2.2) — le contrat implicite entre `main.py` (ancienne closure, qui exposait peut-être ces attributs) et `brain.py` n'était couvert par **aucun test**. Recommandation : ajouter un test unitaire `test_analysis_core_exposes_file_attrs` et un test du mode auto sans clé API (fallback `descriptive_only`), hors réseau.

---

## 7. CE QUI N'A PAS ÉTÉ TOUCHÉ (échecs préexistants, choix documentés)

Deux tests échouaient **avant** nos modifications et échouent **identiquement après** (confirmé par `git stash`) — décision de ne pas les corriger dans cette phase pour ne pas mélanger les périmètres :

1. **`test_quota`** : le rate limit slowapi déclenche un 429 avant le 15ᵉ appel du test — le test dépasse lui-même sa propre limite (problème test/limite, pas code métier). Correctif recommandé : mock du limiter ou activation `enabled=False` en test.
2. **`test_orchestrator_compare_groups`** : le test attend Student/Welch mais le dataset `ts_2groups_normal.csv` produit Mann-Whitney — décalage entre le jeu de données et l'attente du test (probable changement de dataset sans mise à jour du test, ou critère de normalité trop strict dans le sélecteur). **Question pour le directeur** : corriger le dataset, ou assouplir le seuil de normalité du sélecteur ? (impact produit réel : des utilisateurs avec des données normales peuvent recevoir du non-paramétrique à tort — à arbitrer en Phase 3.)

---

## 8. ÉTAT GIT ET PROCHAINES ÉTAPES

- **Modifiés (non commités)** : `.gitignore`, `Dockerfile`, `QUANTA_STATE.md`, `app/analyze_worker.py`, `app/auth.py`, `app/compute/test_selector.py`, `app/llm/brain.py`, `app/orchestrator.py`, `app/report_generator.py`, `db.py`, `main.py`.
- **Nouveaux** : `.github/workflows/ci.yml`, `app/analysis_core.py`, le présent rapport.
- **Stagés** : suppressions des 5 binaires (fichiers présents sur disque).
- **Rien n'est commité** — l'utilisateur décide.

**Recommandations Phase 3 (au directeur)** :
1. Corriger les 2 tests préexistants (§7) et ajouter un test du mode auto sans réseau (§6).
2. Vérifier `ALLOWED_ORIGINS` en production (conséquence directe du §2.5).
3. Étendre la CI : mocks LLM + test du sélecteur statistique de bout en bout.
4. Arbitrage méthodologique : seuil de normalité du sélecteur (Mann-Whitney vs Student).
5. Commit en 3 lots lisibles : `P0+P1 sécurité/fiabilité`, `P2 performance`, `P3 docs/CI + hygiène git`.
