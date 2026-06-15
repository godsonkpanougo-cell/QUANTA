\# NOTES.md � Audit du code legacy QUANTA



> Audit r�alis� le Jour 1, avant tout refactor. Verdict global : \\\*\\\*ce code est bien plus solide qu'attendu\\\*\\\*.

> Le document de specs parlait de bugs bloquants et de pipeline cass� � ces bugs sont presque tous

> dans `brain.py` (couche LLM), pas dans `compute.py` (couche calcul). `compute.py` est quasi pr�t pour la v2.



\---



\## compute.py � Verdict : \~85% R�UTILISABLE TEL QUEL



\### Ce qui fonctionne (et est m�me au-dessus du niveau attendu pour un Jour 1)



\- \*\*`load\\\_and\\\_diagnose()`\*\* : g�re CSV (avec d�tection s�parateur , vs ;), Excel, Stata (.dta), SPSS (.sav).

&#x20; D�tecte types de colonnes, missing %, doublons, outliers IQR, et m�me un "dataset\_type" probable

&#x20; (s�rie temporelle / enqu�te / petit �chantillon). C'est exactement le contenu attendu pour le Jour 3-4.



\- \*\*`clean\\\_dataframe()`\*\* : applique d�j� les r�gles de la Section "Cleaning Core" du doc de specs

&#x20; (m�diane si <5% missing, imputation si 5-20%, suppression si >20%, winsorisation 1%-99%).

&#x20; Log structur� (`cleaning\\\_log`) � c'est la base de l'audit\_log pr�vu au Jour 6.



\- \*\*`descriptive\\\_stats()`\*\* : stats compl�tes (mean, std, m�diane, skewness, kurtosis, CV, IQR) +

&#x20; fr�quences pour cat�gorielles + graphiques (histogrammes, barres) en dark luxury. Couvre le Jour 39

&#x20; (tableaux APA) � 80%.



\- \*\*`normality\\\_tests()`\*\* : Shapiro-Wilk ET D'Agostino-Pearson (d�j� la recommandation de ChatGPT sur

&#x20; le seuil n!) + QQ-plots + conclusion consolid�e NORMALE/NON-NORMALE + recommandation de famille de

&#x20; tests. Couvre le Jour 4 quasi enti�rement.



\- \*\*`correlation\\\_analysis()`\*\* : Pearson ou Spearman selon normalit�, p-values pairwise, classement

&#x20; par force, heatmap. Couvre une bonne partie du Jour 9-10.



\- \*\*`ols\\\_regression()`\*\* : r�gression compl�te avec VIF, Durbin-Watson, Breusch-Pagan, White test,

&#x20; graphiques de diagnostic r�sidus. Tr�s solide � couvre le Jour 10.



\- \*\*`generate\\\_r\\\_script()` / `generate\\\_stata\\\_script()`\*\* : g�n�rent des scripts comment�s, structur�s,

&#x20; avec packages/imports corrects. Couvre une grosse partie du Jour 41/44.



\- \*\*`run\\\_full\\\_compute\\\_pipeline()`\*\* : orchestrateur qui encha�ne tout, retourne un dict propre avec

&#x20; diagnosis/cleaning/descriptive/normality/correlation/regression/charts/scripts. C'est quasi

&#x20; l'endpoint /analyze attendu.



\### Ce qui est cass� / fragile / � corriger



1\. \*\*AUCUN ARBRE DE D�CISION DE TESTS (le coeur des Jours 7-8-11 manque enti�rement)\*\*

&#x20;  - `compute.py` calcule TOUJOURS : descriptives + normalit� + corr�lation + r�gression OLS,

&#x20;    quel que soit l'objectif de l'utilisateur ou la nature des variables.

&#x20;  - Il n'y a NI comparaison de groupes (t-test, ANOVA, Mann-Whitney...), NI chi-deux/Fisher,

&#x20;    NI r�gression logistique. C'est-�-dire : toute la moiti� "cat�gorielle" et "comparaison

&#x20;    de groupes" de l'Annexe B du doc de specs est absente.

&#x20;  - C'est le trou principal. Le `test\\\_selector.py` du Jour 7-8 est � �crire de z�ro.



2\. \*\*Bug latent � `fillna(..., inplace=True)` sur une colonne issue de `select\\\_dtypes`\*\*

&#x20;  - Lignes \~175, 179, 191 : `df\\\[col].fillna(median\\\_val, inplace=True)` sur une Series extraite

&#x20;    d'un DataFrame peut d�clencher un `SettingWithCopyWarning` voire ne pas modifier `df` selon

&#x20;    la version de pandas (chaining assignment). � corriger en `df\\\[col] = df\\\[col].fillna(...)`.



3\. \*\*Pas de d�tection "num�rique mais en r�alit� cat�goriel"\*\*

&#x20;  - Confirme exactement le pi�ge que Gemini a signal� : une colonne r�gion encod�e 1/2/3/4/5 ou

&#x20;    une �chelle de Likert sera trait�e comme `numeric\\\_cols` et entrera dans `descriptive\\\_stats`,

&#x20;    `normality\\\_tests`, `correlation\\\_analysis`, `ols\\\_regression` comme une vraie variable continue.

&#x20;  - Aucun garde-fou (`nunique() < 10` par exemple) dans `load\\\_and\\\_diagnose()`.



4\. \*\*`ols\\\_regression()` choisit Y arbitrairement (`numeric\\\_cols\\\[0]`)\*\*

&#x20;  - Si `target\\\_col` n'est pas fourni, Y = premi�re colonne num�rique du dataset, ce qui peut

&#x20;    �tre un identifiant ou une variable sans aucun sens comme variable d�pendante.

&#x20;  - Pas de validation que Y a du sens (ex: si Y est en r�alit� une variable cat�gorielle encod�e

&#x20;    en int � cf point 3, le bug se propage).



5\. \*\*`run\\\_full\\\_compute\\\_pipeline()` calcule la r�gression M�ME SI elle n'a pas de sens\*\*

&#x20;  - Si le dataset a 2 variables num�riques dont une est un ID, la r�gression tourne quand m�me

&#x20;    et produit des r�sultats qui seront envoy�s au LLM pour interpr�tation � donc un rapport

&#x20;    avec une r�gression absurde mais "interpr�t�e s�rieusement".



6\. \*\*`correlation\\\_analysis()` : matrice de p-values jamais utilis�e\*\*

&#x20;  - `p\\\_matrix` est construite (ligne \~445-476) mais n'est ni retourn�e ni utilis�e dans le

&#x20;    dict final. Code mort ou oubli � � clarifier (peut-�tre pr�vu pour un affichage futur des

&#x20;    significativit�s sur la heatmap).



7\. \*\*G�n�ration de scripts R/Stata : indices fixes (`numeric\\\_cols\\\[:4]`, `\\\[:6]`, `\\\[:8]`)\*\*

&#x20;  - Fonctionne mais peut planter ou produire du code vide si le dataset a moins de colonnes

&#x20;    que ces indices (ex: dataset avec 2 colonnes num�riques ? `numeric\\\_cols\\\[1:4]` est vide,

&#x20;    `x\\\_cols` vide ? `" + ".join(x\\\_cols\\\[:6])` produit une formule R invalide `y \\\~ ` sans

&#x20;    variable). � s�curiser avec des conditions.



8\. \*\*`PALETTE\\\["bg"] = "#0a0a0a"` vs doc de specs `#0A0A0F`\*\*

&#x20;  - D�tail mineur, mais l�g�re incoh�rence de couleur entre le code et le document de specs

&#x20;    (Section 13). � harmoniser si on garde cette palette pour les graphiques matplotlib.



\### � garder pour v2 (sans modification ou avec modifications mineures)



\- `load\\\_and\\\_diagnose()` (+ ajout du garde-fou num�rique/cat�goriel du point 3)

\- `clean\\\_dataframe()` (+ fix `inplace=True` du point 2)

\- `descriptive\\\_stats()`

\- `normality\\\_tests()`

\- `correlation\\\_analysis()` (clarifier le sort de `p\\\_matrix`)

\- `generate\\\_r\\\_script()` / `generate\\\_stata\\\_script()` (+ s�curiser les indices du point 7)

\- La structure g�n�rale de `run\\\_full\\\_compute\\\_pipeline()` comme squelette d'orchestrateur



\### � �crire de z�ro (Semaine 2 du programme, Jours 7-11)



\- `test\\\_selector.py` � l'arbre de d�cision complet de l'Annexe B (comparaisons de groupes,

&#x20; chi-deux/Fisher, r�gression logistique, corr�lations avec choix automatique)

\- Int�gration du switch automatique avec logging dans l'audit\_log (recommandation Gemini)

\- Rendre la r�gression OLS conditionnelle (ne s'ex�cute que si l'objectif/la structure des

&#x20; donn�es le justifie, pas syst�matiquement)



\---



\## brain.py � Logique des phases (6 appels LLM s�quentiels, pas 8 "�tapes �gales")



\### Architecture g�n�rale



Le fichier comporte une fonction `call\\\_llm()` (fallback Groq ? OpenRouter ? Gemini, avec retries

8/16/24s) et un pipeline `analyze\\\_with\\\_brain()` qui encha�ne 6 appels LLM s�quentiels (le doc de

specs en mentionne 8, mais ici il y a 6 phases distinctes � 3 d'entre elles �tant les "3A/3B/3C"

du document).



\### D�tail des phases



| # | Phase | Input (r�sum�) | Output attendu | Tokens max | Pause apr�s |

|---|-------|-----------------|-----------------|-----------|-------------|

| 1 | `\\\_phase\\\_diagnosis` | n\_rows/cols, types, missing, outliers, doublons, cleaning\_log | Diagnostic structurel 3 niveaux | 1500 | 5s |

| 2 | `\\\_phase\\\_descriptive` | Stats num�riques (top 6) + cat�gorielles (top 4) | Interpr�tation descriptive 3 niveaux | 1800 | 5s |

| 3A | `\\\_phase\\\_normality` | R�sultats Shapiro-Wilk (top 6 colonnes) | H0/H1, d�cision, implications | 1500 | 5s |

| 3B | `\\\_phase\\\_correlation` | Top 8 corr�lations significatives | Interpr�tation corr�lations, multicolin�arit� | 1500 | 5s |

| 3C | `\\\_phase\\\_regression` | R�sultats OLS complets (R�, coefs significatifs, VIF, DW, BP) | Interpr�tation r�gression 3 niveaux | 2000 | 10s |

| 8 | `\\\_phase\\\_report\\\_forge` | Synth�se globale (n\_rows, dataset\_type, R�, n\_charts) | Rapport final complet (r�sum� ex�cutif, m�thodo, r�sultats, conclusions, limites, score) | 3000 | � |



\*\*Donc : 6 appels LLM s�quentiels\*\*, avec des pauses cumul�es de 5+5+5+5+10 = 30 secondes avant

le dernier appel (le plus gros, 3000 tokens). Le doc de specs parlait de "Phase 3 d�coup�e en

3A/3B/3C" � c'est exactement ce qu'on voit ici.



\### Ce qui fonctionne dans brain.py



\- \*\*`SYSTEM\\\_PROMPT`\*\* est bien �crit : interdit explicitement au LLM d'inventer des chiffres,

&#x20; impose les 3 niveaux (technique/analytique/d�cisionnel), impose H0/H1 explicite. Bonne base

&#x20; pour le prompt unique du Jour 14-16.



\- \*\*Le fallback multi-provider\*\* (`call\\\_llm`) fonctionne dans sa logique (Groq ? OpenRouter ?

&#x20; Gemini, retries), mais c'est pr�cis�ment l'architecture que le programme 90 jours a d�cid�

&#x20; d'ABANDONNER au Jour 13 (un seul provider payant).



\- \*\*`\\\_phase\\\_report\\\_forge`\*\* contient d�j� la bonne structure de sections (r�sum� ex�cutif,

&#x20; m�thodologie, r�sultats, conclusions, limites + score) � r�utilisable comme trame du prompt unique.



\### Ce qui est cass� / fragile (et explique les 429 document�s dans le doc de specs)



1\. \*\*6 appels LLM s�quentiels = 6 points de d�faillance + 30s de pauses fixes\*\*

&#x20;  - Sur free tier, chaque appel peut �chouer ind�pendamment. Le pipeline entier prend au

&#x20;    minimum \~30s de pauses + temps de 6 g�n�rations. C'est la cause directe des erreurs 429

&#x20;    en cascade d�crites dans le document de specs (Section 9).



2\. \*\*Extraction du score de confiance par parsing de texte fragile (lignes \~393-402)\*\*

&#x20;  ```python

&#x20;  for word in report\_text.split():

&#x20;      if word.isdigit() and 50 <= int(word) <= 100:

&#x20;          ...

&#x20;  ```

&#x20;  - Cherche un nombre entre 50 et 100 suivi de "/100" ou "sur 100" dans le texte g�n�r�.

&#x20;  - Tr�s fragile : formulation diff�rente, nombre d'ann�e (2024), pourcentage non li� au score,

&#x20;    ou r�ponse en langue diff�rente peut casser ou fausser ce parsing.

&#x20;  - Exactement le probl�me que le Jour 12 corrige : score calcul� math�matiquement par

&#x20;    `confidence\\\_score.py`, jamais extrait du texte LLM.



3\. \*\*`raise RuntimeError("Tous les LLM sont �puis�s.")`\*\*

&#x20;  - Si les 3 providers �chouent, `analyze\\\_with\\\_brain` l�ve une exception non g�r�e. Pas de

&#x20;    fallback "retourner les r�sultats bruts sans interpr�tation" � pourtant la r�gle d'or que

&#x20;    le programme impose (Jour 18).



4\. \*\*Aucune validation que les chiffres cit�s par le LLM correspondent aux chiffres fournis\*\*

&#x20;  - Le `SYSTEM\\\_PROMPT` interdit d'inventer des chiffres, mais rien ne v�rifie que le texte

&#x20;    g�n�r� respecte cette consigne (recommandation ChatGPT/point ?).



5\. \*\*Pauses fixes non adaptatives\*\*

&#x20;  - `PAUSE = 5` secondes cod� en dur, qu'on soit sur un free tier satur� ou un provider rapide.



6\. \*\*Les phases 3A/3B/3C ne re�oivent que des extraits tronqu�s ("top 6", "top 8")\*\*

&#x20;  - Si le dataset a 15 variables num�riques, seules 6 sont interpr�t�es dans `\\\_phase\\\_descriptive`

&#x20;    et `\\\_phase\\\_normality`. Le rapport final pourrait ignorer des variables importantes sans le dire.



\### Constat global pour le Jour 16 (appel LLM unique)



\- \*\*Tout ce qui doit dispara�tre\*\* : `call\\\_llm()` avec fallback 3 providers, les 6 fonctions

&#x20; `\\\_phase\\\_\\\*` s�par�es, les pauses entre phases, le parsing fragile du score.

\- \*\*Tout ce qui doit �tre fusionn� en UN seul prompt\*\* : le contenu informationnel des phases

&#x20; 1, 2, 3A, 3B, 3C, 8 (diagnostic + descriptives + normalit� + corr�lations + r�gression +

&#x20; structure du rapport final) � devient les sections d'un unique JSON envoy� en un seul appel.

\- \*\*`SYSTEM\\\_PROMPT`\*\* est r�cup�rable presque tel quel comme base du prompt syst�me unique

&#x20; (� adapter pour d�crire le format JSON structur� attendu en sortie).

\- \*\*Le score de confiance\*\* ne vient plus jamais du LLM � il vient de `confidence\\\_score.py`

&#x20; (Jour 12), calcul� sur les crit�res de l'Annexe A, et seulement \*expliqu�\* par le LLM si besoin.



\---



\## SYNTH�SE � Ce que �a change concr�tement pour le programme 90 jours



\- \*\*Bonne nouvelle\*\* : les Jours 3, 4, 9, 10, 39, 41, 44 sont largement acc�l�r�s � base solide

&#x20; existante � corriger/adapter plut�t qu'� �crire de z�ro. Gain de temps potentiel important en

&#x20; semaine 1 et semaine 2 (partie "ex�cution des tests continus/r�gression/corr�lation").



\- \*\*Le vrai chantier reste intact\*\* : l'arbre de d�cision complet (Jours 7-8, `test\\\_selector.py`)

&#x20; et l'orchestrateur avec switch automatique (Jour 11) sont presque enti�rement � �crire � c'est

&#x20; LE trou du projet actuel, exactement comme suspect� dans le programme 90 jours.



\- \*\*brain.py est � r��crire � \~90%\*\*, mais sa logique informationnelle (quoi dire, dans quel

&#x20; ordre, avec quelles contraintes) est r�cup�rable comme base de prompt pour le Jour 14-16.

&#x20; Le `SYSTEM\\\_PROMPT` actuel est un bon point de d�part.



\- \*\*Risque � corriger en priorit� d�s le Jour 3-4\*\* : le garde-fou num�rique vs cat�goriel

&#x20; (point 3) doit �tre ajout� t�t, car `compute.py` actuel laisserait une variable Likert/code-r�gion

&#x20; se faire moyenner, normaliser, corr�ler et r�gresser sans broncher � exactement le pi�ge

&#x20; signal� par Gemini.
  
note - deus : scikit-posthocs pour la prise en charge du test de dunn au jour 9


note - deus : 1. .cursorrules — La Constitution

C’est le cerveau juridique du projet.

Il ne dit pas comment coder une fonction.

Il dit :

comment QUANTA pense.

Son rôle :

imposer la philosophie globale ;
empêcher Cursor de faire du refactoring sauvage ;
protéger l’architecture ;
rappeler que QUANTA est un logiciel scientifique avant d’être une app.

Sans lui :

Cursor devient un développeur rapide.

Avec lui :

Cursor agit comme un architecte.

2. compute.mdc — Le Tribunal Mathématique

C’est le gardien du moteur.

Son rôle :

empêcher toute approximation statistique ;
imposer le déterminisme ;
forcer la validation des hypothèses ;
protéger les calculs contre NaN, Likert, divisions nulles, biais.

Il répond à :

« est-ce que ce chiffre est réellement défendable ? »

Sans lui :

QUANTA devient un chatbot.

3. api.mdc — Le Contrôle Frontalier

C’est la frontière du système.

Son rôle :

contrôler tout ce qui entre ;
contrôler tout ce qui sort ;
empêcher les structures incohérentes.

Il répond à :

« est-ce que l’extérieur peut casser QUANTA ? »

Sans lui :

tu te retrouves avec des dict partout et des bugs fantômes.

4. llm.mdc — La Muselière du LLM

Le plus dangereux.

Son rôle :

empêcher le LLM de devenir statisticien ;
l’obliger à rester interprète.

Il répond à :

« est-ce que l’IA raconte des choses qu’elle n’a jamais calculées ? »

Sans lui :

tu obtiens des beaux rapports faux.

5. report.mdc — Le Contrat de Confiance

Le rapport est ton produit.

Son rôle :

rendre les résultats lisibles ;
permettre reproduction ;
permettre contestation.

Il répond à :

« est-ce qu’un humain peut signer ce document ? »

Sans lui :

QUANTA est juste une API.

6. tests.mdc — Le Système Immunitaire

Celui qui protège le futur.

Son rôle :

détecter les régressions ;
geler les résultats ;
empêcher une correction de casser autre chose.

Il répond à :

« est-ce que QUANTA est encore vrai après 200 commits ? »

Sans lui :

plus QUANTA grandit, plus il devient fragile.

Ensemble :

.cursorrules
↓
compute
↓
api
↓
llm
↓
report
↓
tests
