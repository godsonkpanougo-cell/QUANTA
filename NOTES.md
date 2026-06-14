\# NOTES.md — Audit du code legacy QUANTA



> Audit réalisé le Jour 1, avant tout refactor. Verdict global : \\\*\\\*ce code est bien plus solide qu'attendu\\\*\\\*.

> Le document de specs parlait de bugs bloquants et de pipeline cassé — ces bugs sont presque tous

> dans `brain.py` (couche LLM), pas dans `compute.py` (couche calcul). `compute.py` est quasi prêt pour la v2.



\---



\## compute.py — Verdict : \~85% RÉUTILISABLE TEL QUEL



\### Ce qui fonctionne (et est même au-dessus du niveau attendu pour un Jour 1)



\- \*\*`load\\\_and\\\_diagnose()`\*\* : gère CSV (avec détection séparateur , vs ;), Excel, Stata (.dta), SPSS (.sav).

&#x20; Détecte types de colonnes, missing %, doublons, outliers IQR, et même un "dataset\_type" probable

&#x20; (série temporelle / enquête / petit échantillon). C'est exactement le contenu attendu pour le Jour 3-4.



\- \*\*`clean\\\_dataframe()`\*\* : applique déjà les règles de la Section "Cleaning Core" du doc de specs

&#x20; (médiane si <5% missing, imputation si 5-20%, suppression si >20%, winsorisation 1%-99%).

&#x20; Log structuré (`cleaning\\\_log`) — c'est la base de l'audit\_log prévu au Jour 6.



\- \*\*`descriptive\\\_stats()`\*\* : stats complètes (mean, std, médiane, skewness, kurtosis, CV, IQR) +

&#x20; fréquences pour catégorielles + graphiques (histogrammes, barres) en dark luxury. Couvre le Jour 39

&#x20; (tableaux APA) à 80%.



\- \*\*`normality\\\_tests()`\*\* : Shapiro-Wilk ET D'Agostino-Pearson (déjà la recommandation de ChatGPT sur

&#x20; le seuil n!) + QQ-plots + conclusion consolidée NORMALE/NON-NORMALE + recommandation de famille de

&#x20; tests. Couvre le Jour 4 quasi entièrement.



\- \*\*`correlation\\\_analysis()`\*\* : Pearson ou Spearman selon normalité, p-values pairwise, classement

&#x20; par force, heatmap. Couvre une bonne partie du Jour 9-10.



\- \*\*`ols\\\_regression()`\*\* : régression complète avec VIF, Durbin-Watson, Breusch-Pagan, White test,

&#x20; graphiques de diagnostic résidus. Très solide — couvre le Jour 10.



\- \*\*`generate\\\_r\\\_script()` / `generate\\\_stata\\\_script()`\*\* : génèrent des scripts commentés, structurés,

&#x20; avec packages/imports corrects. Couvre une grosse partie du Jour 41/44.



\- \*\*`run\\\_full\\\_compute\\\_pipeline()`\*\* : orchestrateur qui enchaîne tout, retourne un dict propre avec

&#x20; diagnosis/cleaning/descriptive/normality/correlation/regression/charts/scripts. C'est quasi

&#x20; l'endpoint /analyze attendu.



\### Ce qui est cassé / fragile / à corriger



1\. \*\*AUCUN ARBRE DE DÉCISION DE TESTS (le coeur des Jours 7-8-11 manque entièrement)\*\*

&#x20;  - `compute.py` calcule TOUJOURS : descriptives + normalité + corrélation + régression OLS,

&#x20;    quel que soit l'objectif de l'utilisateur ou la nature des variables.

&#x20;  - Il n'y a NI comparaison de groupes (t-test, ANOVA, Mann-Whitney...), NI chi-deux/Fisher,

&#x20;    NI régression logistique. C'est-à-dire : toute la moitié "catégorielle" et "comparaison

&#x20;    de groupes" de l'Annexe B du doc de specs est absente.

&#x20;  - C'est le trou principal. Le `test\\\_selector.py` du Jour 7-8 est à écrire de zéro.



2\. \*\*Bug latent — `fillna(..., inplace=True)` sur une colonne issue de `select\\\_dtypes`\*\*

&#x20;  - Lignes \~175, 179, 191 : `df\\\[col].fillna(median\\\_val, inplace=True)` sur une Series extraite

&#x20;    d'un DataFrame peut déclencher un `SettingWithCopyWarning` voire ne pas modifier `df` selon

&#x20;    la version de pandas (chaining assignment). À corriger en `df\\\[col] = df\\\[col].fillna(...)`.



3\. \*\*Pas de détection "numérique mais en réalité catégoriel"\*\*

&#x20;  - Confirme exactement le piège que Gemini a signalé : une colonne région encodée 1/2/3/4/5 ou

&#x20;    une échelle de Likert sera traitée comme `numeric\\\_cols` et entrera dans `descriptive\\\_stats`,

&#x20;    `normality\\\_tests`, `correlation\\\_analysis`, `ols\\\_regression` comme une vraie variable continue.

&#x20;  - Aucun garde-fou (`nunique() < 10` par exemple) dans `load\\\_and\\\_diagnose()`.



4\. \*\*`ols\\\_regression()` choisit Y arbitrairement (`numeric\\\_cols\\\[0]`)\*\*

&#x20;  - Si `target\\\_col` n'est pas fourni, Y = première colonne numérique du dataset, ce qui peut

&#x20;    être un identifiant ou une variable sans aucun sens comme variable dépendante.

&#x20;  - Pas de validation que Y a du sens (ex: si Y est en réalité une variable catégorielle encodée

&#x20;    en int — cf point 3, le bug se propage).



5\. \*\*`run\\\_full\\\_compute\\\_pipeline()` calcule la régression MÊME SI elle n'a pas de sens\*\*

&#x20;  - Si le dataset a 2 variables numériques dont une est un ID, la régression tourne quand même

&#x20;    et produit des résultats qui seront envoyés au LLM pour interprétation — donc un rapport

&#x20;    avec une régression absurde mais "interprétée sérieusement".



6\. \*\*`correlation\\\_analysis()` : matrice de p-values jamais utilisée\*\*

&#x20;  - `p\\\_matrix` est construite (ligne \~445-476) mais n'est ni retournée ni utilisée dans le

&#x20;    dict final. Code mort ou oubli — à clarifier (peut-être prévu pour un affichage futur des

&#x20;    significativités sur la heatmap).



7\. \*\*Génération de scripts R/Stata : indices fixes (`numeric\\\_cols\\\[:4]`, `\\\[:6]`, `\\\[:8]`)\*\*

&#x20;  - Fonctionne mais peut planter ou produire du code vide si le dataset a moins de colonnes

&#x20;    que ces indices (ex: dataset avec 2 colonnes numériques ? `numeric\\\_cols\\\[1:4]` est vide,

&#x20;    `x\\\_cols` vide ? `" + ".join(x\\\_cols\\\[:6])` produit une formule R invalide `y \\\~ ` sans

&#x20;    variable). À sécuriser avec des conditions.



8\. \*\*`PALETTE\\\["bg"] = "#0a0a0a"` vs doc de specs `#0A0A0F`\*\*

&#x20;  - Détail mineur, mais légère incohérence de couleur entre le code et le document de specs

&#x20;    (Section 13). À harmoniser si on garde cette palette pour les graphiques matplotlib.



\### À garder pour v2 (sans modification ou avec modifications mineures)



\- `load\\\_and\\\_diagnose()` (+ ajout du garde-fou numérique/catégoriel du point 3)

\- `clean\\\_dataframe()` (+ fix `inplace=True` du point 2)

\- `descriptive\\\_stats()`

\- `normality\\\_tests()`

\- `correlation\\\_analysis()` (clarifier le sort de `p\\\_matrix`)

\- `generate\\\_r\\\_script()` / `generate\\\_stata\\\_script()` (+ sécuriser les indices du point 7)

\- La structure générale de `run\\\_full\\\_compute\\\_pipeline()` comme squelette d'orchestrateur



\### À écrire de zéro (Semaine 2 du programme, Jours 7-11)



\- `test\\\_selector.py` — l'arbre de décision complet de l'Annexe B (comparaisons de groupes,

&#x20; chi-deux/Fisher, régression logistique, corrélations avec choix automatique)

\- Intégration du switch automatique avec logging dans l'audit\_log (recommandation Gemini)

\- Rendre la régression OLS conditionnelle (ne s'exécute que si l'objectif/la structure des

&#x20; données le justifie, pas systématiquement)



\---



\## brain.py — Logique des phases (6 appels LLM séquentiels, pas 8 "étapes égales")



\### Architecture générale



Le fichier comporte une fonction `call\\\_llm()` (fallback Groq ? OpenRouter ? Gemini, avec retries

8/16/24s) et un pipeline `analyze\\\_with\\\_brain()` qui enchaîne 6 appels LLM séquentiels (le doc de

specs en mentionne 8, mais ici il y a 6 phases distinctes — 3 d'entre elles étant les "3A/3B/3C"

du document).



\### Détail des phases



| # | Phase | Input (résumé) | Output attendu | Tokens max | Pause après |

|---|-------|-----------------|-----------------|-----------|-------------|

| 1 | `\\\_phase\\\_diagnosis` | n\_rows/cols, types, missing, outliers, doublons, cleaning\_log | Diagnostic structurel 3 niveaux | 1500 | 5s |

| 2 | `\\\_phase\\\_descriptive` | Stats numériques (top 6) + catégorielles (top 4) | Interprétation descriptive 3 niveaux | 1800 | 5s |

| 3A | `\\\_phase\\\_normality` | Résultats Shapiro-Wilk (top 6 colonnes) | H0/H1, décision, implications | 1500 | 5s |

| 3B | `\\\_phase\\\_correlation` | Top 8 corrélations significatives | Interprétation corrélations, multicolinéarité | 1500 | 5s |

| 3C | `\\\_phase\\\_regression` | Résultats OLS complets (R², coefs significatifs, VIF, DW, BP) | Interprétation régression 3 niveaux | 2000 | 10s |

| 8 | `\\\_phase\\\_report\\\_forge` | Synthèse globale (n\_rows, dataset\_type, R², n\_charts) | Rapport final complet (résumé exécutif, méthodo, résultats, conclusions, limites, score) | 3000 | — |



\*\*Donc : 6 appels LLM séquentiels\*\*, avec des pauses cumulées de 5+5+5+5+10 = 30 secondes avant

le dernier appel (le plus gros, 3000 tokens). Le doc de specs parlait de "Phase 3 découpée en

3A/3B/3C" — c'est exactement ce qu'on voit ici.



\### Ce qui fonctionne dans brain.py



\- \*\*`SYSTEM\\\_PROMPT`\*\* est bien écrit : interdit explicitement au LLM d'inventer des chiffres,

&#x20; impose les 3 niveaux (technique/analytique/décisionnel), impose H0/H1 explicite. Bonne base

&#x20; pour le prompt unique du Jour 14-16.



\- \*\*Le fallback multi-provider\*\* (`call\\\_llm`) fonctionne dans sa logique (Groq ? OpenRouter ?

&#x20; Gemini, retries), mais c'est précisément l'architecture que le programme 90 jours a décidé

&#x20; d'ABANDONNER au Jour 13 (un seul provider payant).



\- \*\*`\\\_phase\\\_report\\\_forge`\*\* contient déjà la bonne structure de sections (résumé exécutif,

&#x20; méthodologie, résultats, conclusions, limites + score) — réutilisable comme trame du prompt unique.



\### Ce qui est cassé / fragile (et explique les 429 documentés dans le doc de specs)



1\. \*\*6 appels LLM séquentiels = 6 points de défaillance + 30s de pauses fixes\*\*

&#x20;  - Sur free tier, chaque appel peut échouer indépendamment. Le pipeline entier prend au

&#x20;    minimum \~30s de pauses + temps de 6 générations. C'est la cause directe des erreurs 429

&#x20;    en cascade décrites dans le document de specs (Section 9).



2\. \*\*Extraction du score de confiance par parsing de texte fragile (lignes \~393-402)\*\*

&#x20;  ```python

&#x20;  for word in report\_text.split():

&#x20;      if word.isdigit() and 50 <= int(word) <= 100:

&#x20;          ...

&#x20;  ```

&#x20;  - Cherche un nombre entre 50 et 100 suivi de "/100" ou "sur 100" dans le texte généré.

&#x20;  - Très fragile : formulation différente, nombre d'année (2024), pourcentage non lié au score,

&#x20;    ou réponse en langue différente peut casser ou fausser ce parsing.

&#x20;  - Exactement le problème que le Jour 12 corrige : score calculé mathématiquement par

&#x20;    `confidence\\\_score.py`, jamais extrait du texte LLM.



3\. \*\*`raise RuntimeError("Tous les LLM sont épuisés.")`\*\*

&#x20;  - Si les 3 providers échouent, `analyze\\\_with\\\_brain` lève une exception non gérée. Pas de

&#x20;    fallback "retourner les résultats bruts sans interprétation" — pourtant la règle d'or que

&#x20;    le programme impose (Jour 18).



4\. \*\*Aucune validation que les chiffres cités par le LLM correspondent aux chiffres fournis\*\*

&#x20;  - Le `SYSTEM\\\_PROMPT` interdit d'inventer des chiffres, mais rien ne vérifie que le texte

&#x20;    généré respecte cette consigne (recommandation ChatGPT/point ?).



5\. \*\*Pauses fixes non adaptatives\*\*

&#x20;  - `PAUSE = 5` secondes codé en dur, qu'on soit sur un free tier saturé ou un provider rapide.



6\. \*\*Les phases 3A/3B/3C ne reçoivent que des extraits tronqués ("top 6", "top 8")\*\*

&#x20;  - Si le dataset a 15 variables numériques, seules 6 sont interprétées dans `\\\_phase\\\_descriptive`

&#x20;    et `\\\_phase\\\_normality`. Le rapport final pourrait ignorer des variables importantes sans le dire.



\### Constat global pour le Jour 16 (appel LLM unique)



\- \*\*Tout ce qui doit disparaître\*\* : `call\\\_llm()` avec fallback 3 providers, les 6 fonctions

&#x20; `\\\_phase\\\_\\\*` séparées, les pauses entre phases, le parsing fragile du score.

\- \*\*Tout ce qui doit être fusionné en UN seul prompt\*\* : le contenu informationnel des phases

&#x20; 1, 2, 3A, 3B, 3C, 8 (diagnostic + descriptives + normalité + corrélations + régression +

&#x20; structure du rapport final) — devient les sections d'un unique JSON envoyé en un seul appel.

\- \*\*`SYSTEM\\\_PROMPT`\*\* est récupérable presque tel quel comme base du prompt système unique

&#x20; (à adapter pour décrire le format JSON structuré attendu en sortie).

\- \*\*Le score de confiance\*\* ne vient plus jamais du LLM — il vient de `confidence\\\_score.py`

&#x20; (Jour 12), calculé sur les critères de l'Annexe A, et seulement \*expliqué\* par le LLM si besoin.



\---



\## SYNTHÈSE — Ce que ça change concrètement pour le programme 90 jours



\- \*\*Bonne nouvelle\*\* : les Jours 3, 4, 9, 10, 39, 41, 44 sont largement accélérés — base solide

&#x20; existante à corriger/adapter plutôt qu'à écrire de zéro. Gain de temps potentiel important en

&#x20; semaine 1 et semaine 2 (partie "exécution des tests continus/régression/corrélation").



\- \*\*Le vrai chantier reste intact\*\* : l'arbre de décision complet (Jours 7-8, `test\\\_selector.py`)

&#x20; et l'orchestrateur avec switch automatique (Jour 11) sont presque entièrement à écrire — c'est

&#x20; LE trou du projet actuel, exactement comme suspecté dans le programme 90 jours.



\- \*\*brain.py est à réécrire à \~90%\*\*, mais sa logique informationnelle (quoi dire, dans quel

&#x20; ordre, avec quelles contraintes) est récupérable comme base de prompt pour le Jour 14-16.

&#x20; Le `SYSTEM\\\_PROMPT` actuel est un bon point de départ.



\- \*\*Risque à corriger en priorité dès le Jour 3-4\*\* : le garde-fou numérique vs catégoriel

&#x20; (point 3) doit être ajouté tôt, car `compute.py` actuel laisserait une variable Likert/code-région

&#x20; se faire moyenner, normaliser, corréler et régresser sans broncher — exactement le piège

&#x20; signalé par Gemini.

