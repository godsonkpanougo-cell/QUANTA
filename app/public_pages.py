"""Pages publiques statiques (A3) — page Méthodologie.

Zéro dépendance ajoutée : HTML autonome servi par FastAPI (aucun template
engine, aucun fichier externe). Contenu 100 % statique, déterministe, sans
accès DB ni réseau. La page assume les limites de l'outil et positionne
honnêtement QUANTA face à ChatGPT / Julius AI / SPSS — argumentaire destiné
aux encadreurs (UAC / UL / INSAE) qui imposent l'outil à leurs étudiants.

Déterminisme : la même requête renvoie exactement les mêmes octets (testé).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public"])

# Dernière mise à jour du contenu (texte affiché en pied de page).
PAGE_UPDATED = "05/10/2026"


_METHODOLOGIE_HTML = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QUANTA — Méthodologie &amp; comparatif honnête</title>
<meta name="description" content="Comment QUANTA produit chaque chiffre, ce qu'il ne fait pas, et comparatif honnête avec ChatGPT, Julius AI et SPSS.">
<style>
:root {{
  --bg: #0d1117; --panel: #161b22; --ink: #e6edf3; --muted: #9aa4b2;
  --accent: #4ea8ff; --ok: #3fb950; --warn: #d29922; --bad: #f85149;
  --line: #232b36;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.65 "Segoe UI", system-ui, -apple-system, sans-serif; }}
.wrap {{ max-width: 980px; margin: 0 auto; padding: 40px 20px 80px; }}
h1 {{ font-size: 2rem; margin: 0 0 6px; }}
h2 {{ font-size: 1.35rem; margin-top: 48px; border-bottom: 1px solid var(--line); padding-bottom: 8px; }}
h3 {{ font-size: 1.05rem; margin-bottom: 4px; }}
p, li {{ color: var(--ink); }}
.lede {{ color: var(--muted); font-size: 1.05rem; }}
.badge {{ display: inline-block; border: 1px solid var(--line); border-radius: 999px;
  padding: 2px 12px; font-size: .8rem; color: var(--muted); margin-right: 6px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; }}
.card p {{ color: var(--muted); margin: 6px 0 0; font-size: .93rem; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 14px; font-size: .95rem; }}
th, td {{ border: 1px solid var(--line); padding: 10px 12px; text-align: left; vertical-align: top; }}
th {{ background: var(--panel); }}
td.yes {{ color: var(--ok); font-weight: 600; }}
td.no  {{ color: var(--bad); font-weight: 600; }}
td.mid {{ color: var(--warn); font-weight: 600; }}
.note {{ background: var(--panel); border-left: 3px solid var(--accent);
  border-radius: 6px; padding: 12px 16px; margin: 14px 0; }}
.note p {{ color: var(--muted); margin: 4px 0; font-size: .93rem; }}
ol li, ul li {{ margin: 6px 0; }}
code {{ background: var(--panel); border: 1px solid var(--line); border-radius: 4px;
  padding: 1px 6px; font-size: .88em; }}
footer {{ margin-top: 60px; color: var(--muted); font-size: .85rem;
  border-top: 1px solid var(--line); padding-top: 16px; }}
a {{ color: var(--accent); }}
@media print {{ body {{ background: #fff; color: #111; }} }}
</style>
</head>
<body>
<div class="wrap">

<h1>QUANTA — Méthodologie &amp; comparatif honnête</h1>
<p class="lede">Ce que fait l'outil, comment chaque chiffre est produit, ce qu'il
<b>ne fait pas</b>, et comment il se positionne face à ChatGPT, Julius AI et SPSS.
Écrit pour les encadreurs qui doivent décider en connaissance de cause.</p>
<p>
<span class="badge">Page publique — mise à jour : {PAGE_UPDATED}</span>
<span class="badge">Aucune donnée collectée sur cette page</span>
</p>

<h2>1. Le principe : aucune confiance par défaut</h2>
<p>La plupart des « assistants statistiques IA » produisent un texte qui
<i>semble</i> expert sans qu'on puisse vérifier d'où vient chaque nombre.
QUANTA prend le parti inverse :</p>
<ol>
<li><b>Le calcul d'abord, le texte ensuite.</b> Les tests sont exécutés par du
code déterministe (SciPy/Statsmodels) sur vos données brutes. Le LLM n'intervient
<b>qu'après</b>, pour rédiger l'interprétation des chiffres déjà calculés — et si
le LLM est indisponible, l'analyse statistique reste complète (mode dégradé).</li>
<li><b>Chaque chiffre est traçable.</b> Le payload expose la valeur, la statistique
de test, la p-value, la taille d'effet, l'intervalle de confiance — et le nom exact
du test utilisé, avec la règle de sélection qui a conduit à ce choix.</li>
<li><b>La correction de multiplicité n'est pas optionnelle.</b> Quand des dizaines
de corrélations sont testées, la méthode de Benjamini-Hochberg est appliquée et les
deux comptages (brut / ajusté) sont affichés. Une p-value isolée sur 1 326 paires
n'est pas une découverte.</li>
<li><b>La robustesse est automatique.</b> Si Breusch-Pagan ou White détecte une
hétéroscédasticité (p&nbsp;&lt;&nbsp;0,05), la régression est refitée avec des
écarts-types robustes HC3, présentés <i>à côté</i> des estimations classiques pour
comparaison. Les coefficients ne changent pas ; l'incertitude, elle, devient honnête.</li>
<li><b>Chaque analyse est auditable.</b> Le « Repro Pack » ZIP permet à un tiers de
recalculer chaque chiffre publié. Le « Dossier d'audit » et le « Mode Soutenance »
cités dans l'interface proviennent des données persistées, jamais d'un texte généré.</li>
</ol>

<h2>2. Le choix des tests, sans boîte noire</h2>
<p>La sélection entre test paramétrique et non paramétrique suit une règle publique
et vérifiable dans le payload :</p>
<ul>
<li>Normalité testée par colonne (Shapiro-Wilk / D'Agostino selon n) → le résultat
peuple la section <code>normality</code> ;</li>
<li>si la normalité tient sur les groupes comparés → <b>Student</b> (variances
égales) ou <b>Welch</b> (inégales) ;</li>
<li>sinon → <b>Mann-Whitney</b> / Kruskal-Wallis, avec la raison du repli affichée.</li>
</ul>
<div class="note">
<p><b>Transparence sur un bug corrigé (05/10/2026) :</b> en affichage « deux
thèmes », une variable était écrasée deux fois et la section normalité arrivait
<b>vide</b> au sélecteur — tous les tests basculaient alors systématiquement en
Mann-Whitney, même sur des données normales. Le bug est corrigé, prouvé par test
de non-régression, et nous le publions parce qu'un outil qui exige la preuve doit
s'appliquer la même règle à lui-même.</p>
</div>

<h2>3. Comparatif honnête</h2>
<p>Chaque outil est bon pour quelque chose. Le tableau dit aussi ce que QUANTA
<b>ne fait pas</b>.</p>
<table>
<tr><th>Critère</th><th>QUANTA</th><th>ChatGPT (seul)</th><th>Julius AI</th><th>SPSS</th></tr>
<tr><td>Exécution réelle des tests (code déterministe)</td>
<td class="yes">Oui</td><td class="mid">Variable (analysable, pas par défaut reproductible)</td>
<td class="yes">Oui (Python exécuté)</td><td class="yes">Oui (référence)</td></tr>
<tr><td>Traçabilité chiffre → test → règle de choix</td>
<td class="yes">Natif (payload + Repro Pack)</td><td class="no">Non (texte non structuré)</td>
<td class="mid">Partielle (notebook)</td><td class="mid">Sorties classiques, sans règle exposée</td></tr>
<tr><td>Correction de multiplicité systématique et affichée</td>
<td class="yes">Oui (BH, brut vs ajusté)</td><td class="no">Non, sauf si demandé</td>
<td class="no">Non par défaut</td><td class="mid">Option procédurale</td></tr>
<tr><td>Robustesse HC3 automatique sur hétéroscédasticité</td>
<td class="yes">Oui (BP/White → refit)</td><td class="no">Non</td><td class="no">Non</td>
<td class="mid">Manuelle (menu)</td></tr>
<tr><td>Audit tiers : chaque chiffre recalculable</td>
<td class="yes">Oui (Repro Pack ZIP)</td><td class="no">Non</td><td class="mid">Rejouable à la main</td>
<td class="mid">Via fichiers .spv</td></tr>
<tr><td>Interprétation en français, orientée mémoire/soutenance</td>
<td class="yes">Oui (LLM, borné, dégradé propre)</td><td class="yes">Oui (fort)</td>
<td class="mid">Anglais d'abord</td><td class="no">Non</td></tr>
<tr><td>Préparation du jury (questions/réponses chiffrées)</td>
<td class="yes">Oui (Mode Soutenance)</td><td class="no">Non</td><td class="no">Non</td>
<td class="no">Non</td></tr>
<tr><td>Tests avancés (séries temporelles, SEM, bayésien)</td>
<td class="no">Non (hors périmètre assumé)</td><td class="mid">Oui mais non vérifiable</td>
<td class="mid">Oui (code)</td><td class="yes">Oui</td></tr>
<tr><td>Coût étudiant</td><td class="yes">Gratuit (tiers libre)</td>
<td class="mid">Abonnement pour l'usage sérieux</td><td class="mid">Abonnement</td>
<td class="no">Licence payante</td></tr>
</table>

<h3>Ce que QUANTA ne fait pas — et qu'il ne faut pas lui demander</h3>
<ul>
<li><b>Il ne choisit pas votre hypothèse.</b> Il exécute la vôtre et vous montre
ce que disent les données.</li>
<li><b>Il ne remplace pas un cours de stats.</b> Il documente chaque choix pour
que vous puissiez le défendre, pas pour que vous n'ayez pas à le comprendre.</li>
<li><b>Il ne garantit pas la significativité.</b> Si le résultat n'est pas
significatif après correction de multiplicité, la page, le dossier d'audit et la
soutenance le diront tel quel.</li>
<li><b>Le LLM n'est pas une source.</b> Si les providers LLM sont indisponibles,
l'analyse reste complète et l'interface le signale (mode dégradé) — un mémoire ne
dépend jamais d'un service tiers pour exister.</li>
</ul>

<h2>4. Pour un encadreur (UAC / UL / INSAE) : pourquoi l'imposer aux étudiants</h2>
<div class="grid">
<div class="card"><h3>Corriger la plaie des p-hacking</h3>
<p>Des centaines de corrélations testées en silence, une p-value isolée citée en
« découverte » : la correction BH appliquée d'office et le comptage brut/ajusté
affiché ferment cette porte par construction.</p></div>
<div class="card"><h3>Soutenances plus courtes et plus solides</h3>
<p>Le Mode Soutenance génère les questions probables du jury <i>avec les réponses
chiffrées tirées de l'analyse</i>. L'étudiant arrive préparé sur ses propres
nombres, pas sur des formules mémorisées.</p></div>
<div class="card"><h3>Audit d'un mémoire en minutes</h3>
<p>Vous ne relisez pas la sortie SPSS de l'étudiant ligne à ligne : le Repro Pack
contient données, code d'analyse et résultats — chaque chiffre du mémoire est
recalculable par un tiers en une commande.</p></div>
<div class="card"><h3>Pédagogie par la traçabilité</h3>
<p>L'étudiant voit <i>pourquoi</i> Welch plutôt que Student, <i>pourquoi</i> HC3
plutôt que l'erreur-type classique : la règle de décision fait partie du rendu.
L'outil enseigne la méthode qu'il applique.</p></div>
<div class="card"><h3>Zéro licence, zéro installation</h3>
<p>Fonctionne dans le navigateur, gratuit pour l'étudiant, datasets CSV/Excel/
Stata/SPSS acceptés. Aucun argument de coût ne bloque l'adoption d'un groupe
entier de étudiants.</p></div>
<div class="card"><h3>Limites assumées = crédibilité</h3>
<p>La page liste ce que l'outil ne fait pas. Un encadreur peut l'exiger en
connaissance de cause, et l'étudiant ne peut pas présenter un test avancé
que l'outil n'a pas exécuté.</p></div>
</div>

<h2>5. Preuves, pas promesses</h2>
<ul>
<li><b>Incident de performance clos</b> : une analyse complète (diagnostic,
normalité, sélection, 1 326 corrélations, multiplicité, OLS, scoring) sur un
vrai dataset étudiant s'exécute en <b>19,1 s</b> (contre 198,7 s avant
optimisation), LLM dégradé borné à 18,5 s — chronologies détaillées dans le
dossier <code>RAPPORTS_PILIERS/</code> du dépôt public.</li>
<li><b>Suite de tests sans exclusion</b> : 126 tests, dont le bug décrit en §2
est verrouillé par non-régression.</li>
<li><b>Endpoints protégés</b> : projets, conversations, dossiers d'audit et
soutenance ne répondent qu'authentifié (401 vérifié en production).</li>
</ul>

<footer>
QUANTA — statistique traçable pour mémoires et soutenances · page statique
générée côté serveur, mise à jour {PAGE_UPDATED} ·
<a href="/">Retour à l'application</a>
</footer>

</div>
</body>
</html>
"""


@router.get("/methodologie", response_class=HTMLResponse)
def methodologie_page() -> HTMLResponse:
    """Page publique statique : méthodologie + comparatif honnête.

    Aucune dépendance, aucun état, aucun accès DB : le HTML est construit
    une fois à l'import -> réponse déterministe octet par octet.
    """
    return HTMLResponse(content=_METHODOLOGIE_HTML, status_code=200)
