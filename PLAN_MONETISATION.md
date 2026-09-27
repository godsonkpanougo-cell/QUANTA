# PLAN_MONETISATION.md — Paywall Stripe QUANTA

*Créé le 27 septembre 2026. Document d'exécution : chaque phase est vérifiable et réversible.*

## 0. Objectif business

Transformer QUANTA (moteur d'analyse statistique fonctionnel) en produit payant :

| Offre | Prix | Analyses | PDF |
|---|---|---|---|
| **Free** | 0 € | 1 / 30 jours | Filigrané « Démo QUANTA » |
| **Pro** | 19 €/mois (Stripe) | Illimité* | Propre, sans filigrane |
| **Agence** | 150 €/mois (facturation manuelle au début) | Illimité* | Marque blanche : logo + nom client sur la page de garde |

*« Illimité » = `monthly_limit` très élevé (10 000), le quota glissant existant est conservé comme garde-fou.

**Sans `STRIPE_SECRET_KEY`, QUANTA se comporte exactement comme aujourd'hui : 15 analyses/30 jours pour tous, aucun PDF filigrané.** C'est la garantie anti-casse.

## 1. Règles anti-casse (à respecter à chaque phase)

1. **Feature flag** : tout le billing derrière `STRIPE_SECRET_KEY` (import paresseux du SDK `stripe`, fonctions inertes sans clé).
2. **Migrations 100 % additives** : uniquement `ALTER TABLE ADD COLUMN` dans des try/except (pattern existant de `db.py`). Jamais de `DROP`, jamais de `NOT NULL` sur colonne ajoutée, jamais de recréation de table.
3. **Aucune modification des fonctions quota existantes** : `check_and_increment_quota`, `refund_quota`, `get_quota_info` acceptent déjà un paramètre `monthly_limit` — on les appelle avec 1 (free) ou 10 000 (payant).
4. **Paramètres optionnels partout** : watermark et branding sont des paramètres `None` par défaut → rendu PDF identique à l'octet près quand ils sont absents.
5. **Endpoints ajoutés, jamais réécrits** : `/webhooks/stripe` et `/billing/checkout` sont de nouvelles routes.
6. **Frontend additif** : nouvelle page `pricing`, aucun changement de `HomePage`/`AnalysisResults` sauf un bandeau discret de 3 lignes.
7. **Rollback en 10 secondes** : supprimer `STRIPE_SECRET_KEY` des variables d'environnement → le paywall disparaît, personne n'est bloqué.
8. **Branche dédiée** `feature/paywall` : `main` reste intact jusqu'à validation.

## 2. Phases

### Phase 0 — Filet de sécurité (30 min)
- [ ] Branche `feature/paywall` créée depuis `main`.
- [ ] Baseline des tests quota : `test_quota`, `test_cache`, `test_auth_isolation`, `test_cancel_analysis` (2 échecs connus de `test_quota` dus au rate limit slowapi, hors régression).
- [ ] Backup `quanta.db` (copie à froid).

### Phase 1 — Base de données (Jour 1) — fichier : `db.py`
- [ ] Colonnes ajoutées à `users` : `plan TEXT DEFAULT 'free'`, `stripe_customer_id TEXT`, `stripe_subscription_id TEXT`, `branding_name TEXT`, `branding_logo_path TEXT`.
- [ ] Nouvelle fonction `get_user_plan_and_limit(user_id) -> (plan, monthly_limit)` : free → 1, pro/agence → 10 000 ; si la colonne `plan` est absente → ('legacy', 15) = comportement actuel.
- [ ] `init_db` : les ajouts suivent la migration existante, dans le même try/except.

### Phase 2 — Stripe (Jours 1-2) — nouveaux fichiers + routes
- [ ] `requirements.txt` : + `stripe` (pin).
- [ ] Nouveau `app/billing.py` : `billing_enabled()`, `create_checkout_session()`, `verify_webhook()`, `create_portal_session()`. Import paresseux — sans clé, tout retourne None.
- [ ] `main.py` : endpoints `POST /webhooks/stripe` (checkout.session.completed → plan pro ; customer.subscription.deleted → plan free ; invoice.paid → no-op) et `POST /billing/checkout` + `POST /billing/portal` (auth).
- [ ] Dashboard Stripe : produit + 2 prix (19 €/mois, 150 €/mois), prix IDs en variables d'env `STRIPE_PRICE_PRO_ID`, `STRIPE_PRICE_AGENCY_ID`.

### Phase 3 — Paywall (Jour 3)
- [ ] `/analyze` : `plan, monthly_limit = get_user_plan_and_limit(user)` puis `check_and_increment_quota(user_id, monthly_limit)`. Cache et remboursement sur erreur inchangés.
- [ ] `/quota` : retourne aussi `plan` et `limit` (additif).
- [ ] Watermark : paramètre `watermark: str | None = None` dans `app/report_generator.py` + injection CSS overlay ; `/report` passe « Démo QUANTA » si plan = free. Rendu identique si None.
- [ ] Cas particulier : la **première analyse gratuite** doit sortir un PDF filigrané (elle consomme le quota free) — cohérence produit assumée.

### Phase 4 — Marque blanche agence (Jours 4-5)
- [ ] `/report` lit `branding_name`/`branding_logo_path` du user et les passe à `generate_pdf_report(..., branding_name=..., branding_logo_path=...)`.
- [ ] Page de garde : logo (si fourni) + « Préparé pour {branding_name} » ; rien ne change sans branding.
- [ ] Upload de logo : endpoint `POST /billing/branding` (auth, png/jpg ≤ 2 Mo, stocké dans `/data/branding/`).

### Phase 5 — Frontend (Jour 6) — additif uniquement
- [ ] Nouvelle page `quanta-frontend/app/pricing/page.tsx` (3 offres, CGV + mentions légales — obligatoire en France).
- [ ] Composant `UpgradeButton` → `POST /billing/checkout` (redirection Stripe Checkout).
- [ ] Bandeau discret dans la zone résultats quand `/quota` renvoie `remaining: 0` : « Quota épuisé — Passer Pro ».
- [ ] `next.config` : rien à changer ; `NEXT_PUBLIC_API_URL` déjà en place.

### Phase 6 — Validation & mise en ligne (Jour 7)
- [ ] Non-régression : rejouer les tests de la Phase 0 **sans** `STRIPE_SECRET_KEY` → mêmes résultats.
- [ ] Parcours Stripe test (clés test) : abonnement → quota illimité + PDF propre ; résiliation → retour free + filigrané.
- [ ] Webhook testé en local : `stripe listen --forward-to localhost:8000/webhooks/stripe`.
- [ ] Déploiement Railway : `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO_ID` ; webhook URL configurée côté Stripe.
- [ ] Mise en prod : activer les clés live, CGV en ligne.

## 3. Checklist de non-régression (à rejouer à chaque phase)

1. `python -m tests.test_cache` — cache hit ne consomme pas de quota.
2. `python -m tests.test_cancel_analysis` — annulation effective.
3. `python -m tests.test_auth_isolation` — isolation utilisateurs.
4. `/health` OK, upload → analyse → `/report` complet sans `STRIPE_SECRET_KEY`.
5. PDFs de référence (`report_dark.pdf`, `report_light.pdf`) régénérés identiques sans watermark/branding.

## 4. Risques & parades

| Risque | Parade |
|---|---|
| Migration users existante (recréation de table) | On n'y touche pas ; nos colonnes s'ajoutent après, même try/except |
| Webhook manqué (crash pendant l'événement) | Idempotence : `plan` déjà à 'pro' → no-op ; portail client pour réconcilier |
| Test rate-limité 429 (slowapi) | Limites désactivées ou contournées dans les tests (connu, préexistant) |
| Dépendance stripe absente en prod | Dans requirements.txt ; import paresseux = pas de crash si absent |
| Utilisateur payant devenu free avec analyses en cours | Les analyses en cours finissent ; seul le lancement suivant est bloqué |

## 5. Économie unitaire

Coût par analyse : ~0,02-0,05 € (API Groq) + compute Railway. Marge ≥ 95 %. Point mort : 1 abonné Pro couvre ~300 analyses/mois.
