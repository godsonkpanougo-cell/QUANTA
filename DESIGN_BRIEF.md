# QUANTA — DESIGN_BRIEF.md
## Le Contrat Visuel du Produit

> Ce document est la loi. Cursor, v0.dev, Antigravity et tout autre outil IA
> reçoivent son contenu dans chaque prompt de génération visuelle.
> Aucun composant n'est codé avant d'avoir été confronté à ce brief.

---

## SYNTHÈSE DES RÉFÉRENCES VISUELLES

*Analyse consolidée de 10 interfaces haute-fidélité soumises à Gemini Vision*

### Ce que les références ont en commun — le signal fort

Toutes les interfaces analysées partagent une même philosophie de fond :
**le noir n'est pas une couleur de fond, c'est un matériau.** Du `#030508`
au `#0D1117`, ces interfaces traitent l'obscurité comme de la matière
dense, texturée, physique — jamais comme un simple fond uni. Elles refusent
unanimement la grille rigide du SaaS générique, les boutons colorés plein,
les ombres portées massives et le glassmorphism décoratif (c'est-à-dire
appliqué sur de petits boutons ou menus). Là où le glassmorphism apparaît,
il est systémique — la structure elle-même est en verre, pas un ornement posé dessus.

La typographie converge vers un usage paradoxal : des titres monumentaux
en *Light* ou *Regular* (jamais Ultra-Bold), combinés à une micro-typographie
périphérique à `10-12px` traitée comme un HUD — l'interface d'un centre de
commandement aéronautique, pas d'une landing page SaaS.

L'animation est lente, physique et intentionnelle. Pas de splash d'effets.
Un seul mouvement orbital, une respiration d'éclairage, une révélation
typographique par resserrement progressif du letter-spacing. L'animation
signe une présence, elle ne fait pas le clown.

### Ce qui NE s'applique pas directement à QUANTA

Les objets 3D flottants (enceintes, sculptures, roches en orbite) sont des
supports de marque pour des produits physiques. QUANTA affiche des données
statistiques. Un statsticien travaille dessus 20 minutes. La densité doit
être supérieure à celle d'une landing page de portfolio. Les surfaces doivent
être lisibles, pas immersives à l'excès.

**Le curseur de QUANTA** : cinématique dans l'entrée et les transitions,
fonctionnel et dense dans l'affichage des résultats. Les deux états coexistent
et ne se contredisent pas — ils correspondent à deux moments différents de
l'usage (accueil/upload vs lecture de rapport).

---

## SYSTÈME DE DESIGN QUANTA

### 1. PALETTE

```
/* ── Fonds ─────────────────────────────────────────── */
--bg-void:       #0A0A0F;   /* noir abyssal — fond principal, 90% de la surface */
--bg-surface:    #13131A;   /* surface élevée — cartes, panneaux */
--bg-elevated:   #1C1C26;   /* surface haute — modales, dropdowns, hover */

/* ── Accents ────────────────────────────────────────── */
--accent-gold:   #C9A84C;   /* or institutionnel — CTA principal, titres clés */
--accent-gold-2: #E8D5A3;   /* or clair — hover states, icônes secondaires */
--accent-cyan:   #00D4FF;   /* cyan tech — états actifs, badges, liens */
--accent-cyan-2: #00A8CC;   /* cyan profond — variantes et ombres cyan */

/* ── Texte ──────────────────────────────────────────── */
--text-primary:  #E8E8E8;   /* blanc cassé légèrement chaud — corps principal */
--text-secondary:#9A9AA8;   /* gris acier désaturé — métadonnées, labels */
--text-muted:    #555563;   /* gris profond — placeholders, hints */

/* ── Structures ─────────────────────────────────────── */
--border-subtle: rgba(255,255,255,0.06);  /* bordure quasi-invisible — séparation douce */
--border-active: rgba(201,168,76,0.3);    /* bordure or translucide — focus, sélection */
--border-cyan:   rgba(0,212,255,0.2);     /* bordure cyan — état actif/running */

/* ── Feedback d'état ────────────────────────────────── */
--state-success: #2ECC71;
--state-warning: #F39C12;
--state-error:   #E74C3C;
```

**Règle d'usage de la couleur :**
Le noir doit occuper 80-85% de la surface. L'or est utilisé pour un seul
élément par section — jamais deux éléments or côte à côte. Le cyan signale
l'interactivité et les états dynamiques (analyse en cours, badge actif, lien).
Ensemble, or + cyan ne doivent jamais apparaître dans le même composant —
ils se prennent l'un pour l'autre et s'annulent. Règle simple : or = statique
(titres, CTA principal, score), cyan = dynamique (états, progress, notifications).

---

### 2. TYPOGRAPHIE

**Duo retenu :**
- **Space Grotesk** — affichage uniquement (H1, H2, titres de sections, score de confiance en grand).
  Caractère : géométrique, aéré, une légère personnalité technique qui n'est pas Inter.
  Usage : `font-weight: 300` à `500` exclusivement. Jamais Bold sur Space Grotesk — c'est contre son caractère.
- **Geist** (via `next/font` — optimisé Next.js, zéro flash) — tout le reste.
  Corps, labels, micro-UI, tableaux, erreurs, métadonnées. `font-weight: 400` standard.

**Échelle typographique :**
```
/* ── Affichage ─────────────────────────────── */
.display-xl:  Space Grotesk 300,  72px,  letter-spacing: -0.02em   /* Score de confiance en hero */
.display-lg:  Space Grotesk 300,  48px,  letter-spacing: -0.01em   /* Titre principal landing */
.display-md:  Space Grotesk 400,  36px,  letter-spacing: 0         /* Titres de sections */

/* ── Interface ──────────────────────────────── */
.heading-lg:  Geist 600,          24px,  letter-spacing: 0         /* Titres de cartes */
.heading-md:  Geist 500,          18px,  letter-spacing: 0.01em    /* Sous-titres */
.heading-sm:  Geist 500,          14px,  letter-spacing: 0.05em    /* Labels ALL CAPS */

/* ── Corps ──────────────────────────────────── */
.body-lg:     Geist 400,          16px,  line-height: 1.6          /* Corps principal */
.body-md:     Geist 400,          14px,  line-height: 1.5          /* Corps secondaire */
.body-sm:     Geist 400,          12px,  line-height: 1.4          /* Métadonnées */

/* ── HUD ────────────────────────────────────── */
.micro:       Geist 400,          11px,  letter-spacing: 0.08em    /* Micro-UI HUD style */
.mono:        JetBrains Mono 400, 13px,  letter-spacing: 0.02em    /* Valeurs statistiques, codes R */
```

**Règle ALL CAPS :** Uniquement sur les éléments de navigation, badges,
et labels de section (`.heading-sm`). Jamais sur du texte de corps.
Jamais sur plus de 4 mots consécutifs.

**Règle monospace :** Toutes les valeurs statistiques (p-values, coefficients,
statistiques de test) sont rendues en monospace `JetBrains Mono`. Cela renforce
visuellement la rigueur académique et aide l'alignement des colonnes numériques.
Ajouter via `next/font`.

---

### 3. COMPOSANTS

#### Cartes (Cards)
```css
/* Carte standard */
border-radius: 12px;
border: 1px solid var(--border-subtle);
background: var(--bg-surface);
/* Pas d'ombres portées massives. Si ombre, uniquement inset subtile. */

/* Carte active / focus */
border: 1px solid var(--border-active);
background: linear-gradient(135deg, var(--bg-surface), var(--bg-elevated));
```

#### Boutons
```css
/* Bouton primaire (or) */
.btn-primary {
  background: var(--accent-gold);
  color: var(--bg-void);
  border-radius: 8px;           /* Pas une pilule. Pas un carré vif. Entre les deux. */
  font: 500 14px/1 Geist;
  letter-spacing: 0.04em;
  padding: 12px 24px;
}

/* Bouton ghost (structure filaire) */
.btn-ghost {
  background: transparent;
  border: 1px solid var(--border-subtle);
  color: var(--text-primary);
  border-radius: 8px;
}

/* Bouton ghost actif */
.btn-ghost:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}
```

**Règle bouton :** Il n'existe que deux types de boutons dans QUANTA —
primaire or et ghost filaire. Pas de bouton "secondary filled", pas de pilule
(`border-radius: 99px`), pas de bouton plein coloré autre que l'or. La pilule
est le bouton SaaS générique par excellence.

#### Inputs et zones de saisie
```css
.input {
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font: 400 14px/1.5 Geist;
  padding: 12px 16px;
  transition: border-color 150ms ease;
}
.input:focus {
  border-color: var(--accent-cyan);
  outline: none;
  box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.08);
}
```

#### Zone d'upload (Drop Zone)
C'est le composant signature de la landing page. Il doit être mémorable.
```css
.drop-zone {
  background: var(--bg-surface);
  border: 1px dashed var(--border-subtle);
  border-radius: 16px;
  /* Au survol ou drag : */
  border-color: var(--accent-gold);
  box-shadow: 0 0 40px rgba(201, 168, 76, 0.08);
  /* Transition douce, pas instantanée */
  transition: all 300ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

#### Score de confiance (Composant signature)
Le score de confiance est l'élément le plus distinctif du produit.
Il doit être traité comme un artifact graphique, pas un simple badge.
```
Structure :
  [Nombre en Space Grotesk 300, 72px, couleur selon le niveau]
  [Barre de progression circulaire fine, 2px, en or/cyan]
  [Niveau en Geist 500, 14px, ALL CAPS, espacement 0.08em]
  [Points de vigilance en Geist 400, 12px, avec icône warning]

Couleur par niveau :
  Élevé   : #C9A84C (or)
  Modéré  : #00D4FF (cyan)
  Faible  : #F39C12 (orange)
  Très faible : #E74C3C (rouge)
```

#### Progress Bar (8 étapes)
```
Comportement :
  - 8 étapes nommées, affichées linéairement
  - Étape active : point cyan pulsant (animation keyframes, 1.5s ease)
  - Étapes passées : trait continu or, point plein
  - Étapes futures : trait pointillé, couleur --text-muted
  - Label de l'étape active en Geist 500 14px, couleur cyan
  - Jamais de pourcentage brut — seulement les noms d'étapes
```

---

### 4. DENSITÉ ET ESPACEMENT

QUANTA a deux modes de densité qui coexistent dans la même interface :

**Mode Hero (landing, upload, attente)** — densité faible, respiration maximale.
Inspiré directement des références : grand espace négatif, éléments repoussés
aux marges, centre sanctuarisé pour l'élément principal.

**Mode Rapport (résultats, statistiques, PDF)** — densité fonctionnelle.
L'information prime sur l'espace. Tableaux, cartes de tests, audit trail :
les données s'affichent serrées mais jamais étouffées.

**Système de spacing (basé sur une grille de 4px) :**
```
4px   — espace intra-composant (entre icône et texte dans un badge)
8px   — espace entre éléments liés (label + input)
12px  — padding interne des composants compacts
16px  — padding standard des cartes et inputs
24px  — espace entre composants d'une même section
32px  — marge de section (séparation entre blocs distincts)
48px  — séparation de sections majeures
64px  — marge verticale hero (respiration maximale)
```

---

### 5. ANIMATIONS ET MOTION

**Principe** : une seule animation par écran doit attirer l'œil à un moment
donné. Pas d'animations simultanées concurrentes.

**Durées et courbes :**
```javascript
const transitions = {
  micro:    '100ms ease',           // hover sur bouton, focus input
  standard: '200ms cubic-bezier(0.4, 0, 0.2, 1)',  // apparition composant
  reveal:   '400ms cubic-bezier(0.16, 1, 0.3, 1)', // entrée de sections
  slow:     '600ms ease',           // transitions de page, progress steps
  orbital:  '3000ms ease-in-out infinite', // ambient (point pulsant, particules)
}
```

**Animations autorisées :**
- Point cyan pulsant sur étape active de la progress bar (orbital)
- Révélation du titre par expansion de letter-spacing au load (reveal)
- Glow subtil de la zone d'upload au drag-over (standard)
- Transition de step à step dans la progress bar (slow)
- Fade-in des cartes de résultats avec translateY(8px) → translateY(0) (reveal)
- Chiffre du score de confiance qui compte de 0 vers la valeur réelle (slow)

**Animations interdites :**
- Particules flottantes ou objets 3D en orbite — pas pour une interface de données
- Parallaxe sur le scroll — distrayant, désoriente sur mobile
- Glassmorphism avec backdrop-filter sur des éléments de données (tableaux, valeurs) — illisible
- Transitions de page qui durent plus de 500ms
- Animations déclenchées au scroll avant que l'utilisateur ne soit actif

---

### 6. CE QUE QUANTA N'EST PAS

*Liste d'anti-patterns à communiquer explicitement à Cursor/v0.dev dans chaque prompt*

```
INTERDIT :
- border-radius: 999px  (pilule SaaS générique)
- background: linear-gradient(135deg, #6366f1, #8b5cf6)  (violet/indigo SaaS standard)
- backdrop-filter: blur() sur des tableaux de données (illisible)
- font-family: 'Poppins'  (la police Canva)
- box-shadow avec couleur colorée (ex: 0 4px 20px rgba(99,102,241,0.4))
- border-radius: 0px sur les boutons  (trop brutal, pas premium)
- Illustrations Lottie génériques
- Icônes emoji dans l'interface
- Fond blanc ou clair sur n'importe quelle section principale
- Gradients rose/orange sur des sections entières
- Compteurs de chiffres animés sans contexte statistique réel
- "TRUSTED BY 10,000 USERS" si ce n'est pas vrai
- Logos de clients en grille sur la landing page (QUANTA n'a pas encore de clients)
```

---

### 7. REPOS GITHUB — USAGE ET RÔLE DE CHAQUE UN

**À installer comme dépendances actives :**
- `shadcn/ui` — fondation de composants à restyler (Button, Card, Accordion,
  Badge, Separator, Sheet, Dialog). Ne pas utiliser les styles par défaut :
  copier les composants et les adapter à la palette QUANTA.
- `magicui` — animations de qualité production (NumberTicker pour le comptage
  du score, TextAnimate pour la révélation typographique, DotPattern pour
  l'arrière-plan hero).
- `lucide` — iconographie (déjà inclus dans shadcn/ui). Uniquement des icônes
  à trait fin (`strokeWidth: 1.5`). Pas d'icônes remplies.
- `tremor` — composants de dataviz (si utilisé pour les graphiques des
  résultats d'analyse, préférer Recharts qui est déjà dans les dépendances
  connues).

**À utiliser comme références visuelles, pas comme dépendances :**
- `satnaing/shadcn-admin` — layout de dashboard à observer pour la structure
  des sidebars et la disposition des cartes de résultats. Ne pas installer.
- `shadcnspace/shadcnspace` — composants avancés à copier sélectivement
  si un composant spécifique manque.
- `ixartz/SaaS-Boilerplate` — structure Next.js App Router, routing, auth.
  À observer pour la config, pas le style.
- `nextlevelbuilder/ui-ux-pro-max-skill` et `saifyxpro/ui-ux-design-pro-skill`
  — références de direction artistique. Extraire les patterns de layout et
  de composition, pas les composants directement.

**Ne pas installer :**
- `saas-js/saas-ui` — système de design complet avec son propre langage
  visuel, quasi-impossible à restyler sans conflits profonds.
- `primer/react` — langage visuel GitHub, trop neutre et institutionnel.

---

### 8. SIGNATURE VISUELLE QUANTA

*L'élément qui rend QUANTA immédiatement reconnaissable et impossible à
confondre avec un template*

**Le Score de Confiance comme artifact graphique.**

Quand l'analyse est terminée, le score de confiance (ex: 87/100 "Modéré")
n'est pas affiché dans un badge ou une barre de progression standard. Il
apparaît comme un grand chiffre en Space Grotesk Light, centré, qui compte
depuis 0 jusqu'à sa valeur réelle sur 1.5 secondes, entouré d'un cercle
de progression en trait fin (2px) dont la couleur change selon le niveau
(or/cyan/orange/rouge). En dessous, les points de vigilance s'affichent
comme une liste de terminaux — fond légèrement plus foncé que la carte,
police monospace, couleur --text-muted, avec une icône `⚠` en or si
pertinent.

C'est le moment dans l'interface où l'utilisateur comprend que QUANTA lui
dit quelque chose d'honnête sur ses données — pas seulement un résultat,
mais un jugement calibré sur la fiabilité de ce résultat. C'est ça, la
différence produit. L'interface doit la rendre visible et mémorable.

---

### 9. ENVIRONNEMENT TECHNIQUE QUANTA FRONTEND

```
Framework       : Next.js 14+ (App Router, TypeScript)
Styling         : Tailwind CSS (config étendue avec la palette ci-dessus)
Composants      : shadcn/ui (base) + magicui (animations)
Polices         : Space Grotesk + Geist + JetBrains Mono (via next/font)
Icônes          : lucide-react (strokeWidth 1.5 par défaut)
Animations      : Framer Motion (progress bar, transitions de page)
Dataviz         : Recharts (graphiques des résultats d'analyse)
Node            : v24.14.1
npm             : v11.11.0
```

**Configuration Tailwind à étendre (`tailwind.config.ts`) :**
```typescript
theme: {
  extend: {
    colors: {
      quanta: {
        void:      '#0A0A0F',
        surface:   '#13131A',
        elevated:  '#1C1C26',
        gold:      '#C9A84C',
        'gold-2':  '#E8D5A3',
        cyan:      '#00D4FF',
        'cyan-2':  '#00A8CC',
        primary:   '#E8E8E8',
        secondary: '#9A9AA8',
        muted:     '#555563',
      }
    },
    fontFamily: {
      display: ['Space Grotesk', 'sans-serif'],
      sans:    ['Geist', 'sans-serif'],
      mono:    ['JetBrains Mono', 'monospace'],
    },
    borderRadius: {
      'quanta': '8px',    // radius standard des composants QUANTA
      'card':   '12px',   // radius des cartes
      'hero':   '16px',   // radius des grandes zones (upload, modal)
    },
  }
}
```

---

*Dernière mise à jour : Jour 25, Mois 2 du programme 90 jours QUANTA*
*Doit être relu et validé avant chaque session de génération de composants.*
