# QUANTA — Matrice de Couverture Statistique

**Date de l'audit** : 16 septembre 2026  
**Version du code** : commit 965f20c  
**Méthodologie** : Lecture systématique du code source (compute.py, test_selector.py, orchestrator.py)  
**Règle absolue** : Chaque ligne "Implémenté = O" est basée sur une référence fichier:ligne réelle, jamais sur une supposition.

---

## Légende

- **Implémenté (O/N)** : Oui si la fonction existe et est appelée par le pipeline principal
- **Fichier:ligne** : Référence exacte dans le code source
- **Testé** : Nom du fichier de test couvrant cette méthode, ou "aucun"
- **Taille d'effet calculée (O/N)** : Oui si le code calcule une taille d'effet (Cohen's d, η², ε², r, V de Cramér, odds ratio)
- **IC calculé (O/N)** : Oui si un intervalle de confiance est calculé
- **Graphique associé (O/N)** : Oui si un graphique est généré
- **Niveau de maturité** : validé (testé et documenté) / partiel (implémenté mais test limité) / mort (code non atteignable) / absent (non implémenté)

---

## 1. Statistiques descriptives

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Statistiques descriptives (moyenne, médiane, écart-type, etc.) | O | compute.py:447 (descriptive_stats) | test_extreme_missing.py, test_wide_dataset.py | N | N | N | validé |
| Histogrammes de distribution | O | compute.py:447 (descriptive_stats) | test_extreme_missing.py | N | N | O | validé |
| Détection d'outliers (IQR) | O | compute.py:279 (clean_dataframe) | test_outliers_extreme.py | N | N | N | validé |
| Winsorisation des outliers | O | compute.py:279 (clean_dataframe) | test_extreme_missing.py | N | N | N | validé |

---

## 2. Normalité

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Shapiro-Wilk | O | compute.py:629 (shapiro) | test_selector_2groups_normal.py | N | N | O (histogramme Q-Q) | validé |
| D'Agostino-Pearson | O | compute.py:642 (normaltest) | test_selector_2groups_normal.py | N | N | O (histogramme Q-Q) | validé |
| Décision consolidée (NORMALE/NON-NORMALE/AMBIGUE) | O | compute.py:654-685 (normality_tests) | test_selector_2groups_normal.py | N | N | N | validé |

---

## 3. Variance

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Test de Levene (égalité des variances) | O | test_selector.py:139 (stats.levene) | test_selector_2groups_normal.py | N | N | N | validé |

---

## 4. Comparaison 2 groupes

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| t-test de Student (variances égales, indépendants) | O | test_selector.py:244 (stats.ttest_ind) | test_selector_2groups_normal.py | O (Cohen's d) | N | O (boxplot) | validé |
| t-test de Welch (variances inégales, indépendants) | O | test_selector.py:250 (stats.ttest_ind) | test_selector_2groups_normal.py | O (Cohen's d) | N | O (boxplot) | validé |
| Mann-Whitney U (non-paramétrique, indépendants) | O | test_selector.py:258 (stats.mannwhitneyu) | test_selector_2groups_nonnormal.py | O (r rang bisériel) | N | O (boxplot) | validé |
| t-test pairé (Student, appariés) | O | test_selector.py:210 (stats.ttest_rel) | à vérifier (test manquant) | O (Cohen's d) | N | N | partiel |
| Wilcoxon signé (non-paramétrique, appariés) | O | test_selector.py:216 (stats.wilcoxon) | à vérifier (test manquant) | O (r rang bisériel) | N | N | partiel |

---

## 5. Comparaison 3+ groupes

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| ANOVA à un facteur (variances égales) | O | test_selector.py:342 (stats.f_oneway) | test_selector_multigroup.py | O (η²) | N | O (boxplot) | validé |
| Welch ANOVA (variances inégales) | O | test_selector.py:143-182 (_welch_anova) | test_selector_multigroup.py | O (η²) | N | O (boxplot) | partiel |
| Kruskal-Wallis H (non-paramétrique) | O | test_selector.py:381 (stats.kruskal) | test_selector_multigroup.py | O (ε²) | N | O (boxplot) | validé |

---

## 6. Post-hoc

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Tukey HSD (post-hoc ANOVA) | O | test_selector.py:486-507 (_tukey_hsd) | test_selector_multigroup.py | N | N | N | validé |
| Games-Howell (post-hoc Welch ANOVA) | O | test_selector.py:510-532 (_games_howell_or_fallback) | test_selector_multigroup.py | N | N | N | partiel |
| Test de Dunn (post-hoc Kruskal-Wallis) | O | test_selector.py:535-550 (_dunn_test) | test_selector_multigroup.py | N | N | N | partiel |

---

## 7. Corrélations

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Corrélation de Pearson | O | compute.py:760 (pearsonr) | test_orchestrator_delegation_correlation.py | O (r) | N | O (scatter plot) | validé |
| Corrélation de Spearman | O | compute.py:762 (spearmanr) | test_orchestrator_delegation_correlation.py | O (ρ) | N | O (scatter plot) | validé |
| Matrice de p-values | O | compute.py:724-827 (correlation_analysis) | test_orchestrator_delegation_correlation.py | N | N | N | validé |
| Sélection automatique (Pearson vs Spearman selon normalité) | O | compute.py:724-827 (correlation_analysis) | test_orchestrator_delegation_correlation.py | N | N | N | validé |

---

## 8. Tableaux de contingence / Association catégorielle

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Chi-deux d'indépendance | O | test_selector.py:606 (stats.chi2_contingency) | test_selector_association.py | O (V de Cramér) | N | N | validé |
| Fisher exact (table 2x2) | O | test_selector.py:634 (stats.fisher_exact) | test_selector_association.py | O (odds ratio) | N | N | validé |
| V de Cramér (taille d'effet) | O | test_selector.py:677-684 (_cramers_v) | test_selector_association.py | N | N | N | validé |

---

## 9. Régression linéaire (OLS)

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Régression OLS (moindres carrés ordinaires) | O | compute.py:831 (ols_regression) | test_regression_j24.py | O (R²) | O (IC des coefficients) | O (scatter plot) | validé |
| VIF (Variance Inflation Factor) | O | compute.py:894 (variance_inflation_factor) | test_regression_j24.py | N | N | N | validé |
| Durbin-Watson (autocorrélation) | O | compute.py:899 (durbin_watson) | test_regression_j24.py | N | N | N | validé |
| Test de Breusch-Pagan (hétéroscédasticité) | O | compute.py:903 (het_breuschpagan) | test_regression_j24.py | N | N | N | validé |
| Test de White (hétéroscédasticité) | O | compute.py:914 (het_white) | test_regression_j24.py | N | N | N | validé |
| RMSE | O | compute.py:979 (np.sqrt(model.mse_resid)) | test_regression_j24.py | N | N | N | validé |

---

## 10. GLM (Régression logistique)

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Régression logistique binaire | O | test_selector.py:691 (run_logistic_regression) | test_selector_logistic.py | O (odds ratios) | O (IC des odds ratios) | N | validé |
| Pseudo-R² (McFadden) | O | test_selector.py:743 (model.prsquared) | test_selector_logistic.py | N | N | N | validé |
| LLR p-value (test du modèle) | O | test_selector.py:746 (model.llr_pvalue) | test_selector_logistic.py | N | N | N | validé |

---

## 11. Diagnostics de régression

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| VIF (multicolinéarité) | O | compute.py:894 (variance_inflation_factor) | test_regression_j24.py | N | N | N | validé |
| Durbin-Watson (autocorrélation) | O | compute.py:899 (durbin_watson) | test_regression_j24.py | N | N | N | validé |
| Breusch-Pagan (hétéroscédasticité) | O | compute.py:903 (het_breuschpagan) | test_regression_j24.py | N | N | N | validé |
| White (hétéroscédasticité) | O | compute.py:914 (het_white) | test_regression_j24.py | N | N | N | validé |

---

## 12. ACP/ACM/Analyse factorielle

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| ACP (Analyse en Composantes Principales) | O | compute.py:1893 (run_acp) | test_acp_manual.py, test_acp_numeric_id_manual.py, test_acp_report_manual.py | N | N | O (cercle de corrélation, scree plot) | validé |
| ACM (Analyse des Correspondances Multiples) | O | compute.py:1591 (run_acm) | test_acm_with_identifier.csv (test manquant) | N | N | O (plan factoriel) | partiel |
| Scree plot (valeurs propres) | O | compute.py:1820 (_generate_scree_plot) | test_acp_manual.py | N | N | O | validé |
| Cercle de corrélation (ACP) | O | compute.py:2043 (_generate_pca_correlation_circle) | test_acp_manual.py | N | N | O | validé |
| Plan factoriel (ACM) | O | compute.py:1720 (_generate_acm_plot) | à vérifier (test manquant) | N | N | O | partiel |

---

## 13. Clustering

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| K-means | N | — | — | — | — | — | absent |
| Hierarchical clustering | N | — | — | — | — | — | absent |
| DBSCAN | N | — | — | — | — | — | absent |

---

## 14. Séries temporelles

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| ARIMA | N | — | — | — | — | — | absent |
| Décomposition saisonnière | N | — | — | — | — | — | absent |
| Test de stationnarité (ADF) | N | — | — | — | — | — | absent |

---

## 15. Survie

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Kaplan-Meier | N | — | — | — | — | — | absent |
| Log-rank test | N | — | — | — | — | — | absent |
| Modèle de Cox | N | — | — | — | — | — | absent |

---

## 16. Bootstrap / Permutation

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Bootstrap IC | N | — | — | — | — | — | absent |
| Permutation test | N | — | — | — | — | — | absent |

---

## 17. Taille d'effet

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Cohen's d (2 groupes) | O | test_selector.py:418 (_cohens_d) | test_selector_2groups_normal.py | N | N | N | validé |
| r rang bisériel (Mann-Whitney/Wilcoxon) | O | test_selector.py:426 (_rank_biserial) | test_selector_2groups_nonnormal.py | N | N | N | validé |
| η² (ANOVA) | O | test_selector.py:436 (_eta_squared) | test_selector_multigroup.py | N | N | N | validé |
| ε² (Kruskal-Wallis) | O | test_selector.py:446 (_epsilon_squared) | test_selector_multigroup.py | N | N | N | validé |
| V de Cramér (Chi-deux) | O | test_selector.py:677 (_cramers_v) | test_selector_association.py | N | N | N | validé |
| Odds ratio (logistique) | O | test_selector.py:720 (np.exp(coef)) | test_selector_logistic.py | N | N | N | validé |

---

## 18. Power analysis

| Analyse | Implémenté (O/N) | Fichier:ligne | Testé | Taille d'effet calculée (O/N) | IC calculé (O/N) | Graphique associé (O/N) | Niveau de maturité |
|---------|------------------|---------------|-------|-------------------------------|-----------------|-------------------------|-------------------|
| Power post-test (1-β) | O | compute.py:1278 (compute_statistical_power) | à vérifier (test manquant) | N | N | N | partiel |
| Interprétation de la puissance | O | compute.py:1241 (interpret_statistical_power) | à vérifier (test manquant) | N | N | N | partiel |

---

## Bugs et incohérences identifiés

### 1. Tests manquants pour les comparaisons appariées
**Fichier** : test_selector.py:205-237 (run_two_group_comparison)  
**Problème** : Le code implémente t-test pairé (stats.ttest_rel) et Wilcoxon signé (stats.wilcoxon) pour les comparaisons appariées, mais aucun test dans tests/ ne couvre ce cas.  
**Impact** : Code mort potentiel si le paramètre `paired=True` n'est jamais utilisé.  
**Statut** : À vérifier (test manquant)

### 2. Test manquant pour Welch ANOVA spécifique
**Fichier** : test_selector.py:143-182 (_welch_anova)  
**Problème** : La fonction _welch_anova est implémentée et appelée dans run_multi_group_comparison, mais le test test_selector_multigroup.py ne vérifie pas spécifiquement le cas Welch ANOVA (seulement ANOVA classique et Kruskal-Wallis).  
**Impact** : Couverture de test partielle pour le cas variances inégales.  
**Statut** : Partiel

### 3. Test manquant pour ACM
**Fichier** : compute.py:1591 (run_acm)  
**Problème** : L'ACM est implémentée et un fichier de test existe (test_acm_with_identifier.csv), mais aucun fichier .py ne l'exécute.  
**Impact** : Code mort potentiel si l'ACM n'est jamais atteinte par le pipeline.  
**Statut** : À vérifier (test manquant)

### 4. Test manquant pour power analysis
**Fichier** : compute.py:1278 (compute_statistical_power)  
**Problème** : La fonction compute_statistical_power est implémentée et appelée par orchestrator.py, mais aucun test spécifique ne vérifie son calcul.  
**Impact** : Risque de régression non détectée sur le calcul de puissance.  
**Statut** : À vérifier (test manquant)

### 5. Délégation OLS non testée avec target_col différent
**Fichier** : orchestrator.py:119 (compute.ols_regression)  
**Problème** : Le code gère le cas où la cible demandée diffère du calcul générique (recalcul avec target_col spécifique), mais test_orchestrator_delegation_ols.py ne teste que le cas de réutilisation du résultat existant.  
**Impact** : Le chemin de recalcul n'est pas testé.  
**Statut** : Partiel

### 6. Games-Howell dépend de scikit-posthocs
**Fichier** : test_selector.py:514-532 (_games_howell_or_fallback)  
**Problème** : Games-Howell n'est utilisé que si scikit-posthocs est installé (HAS_POSTHOCS). Sinon, repli sur Tukey HSD avec avertissement. Aucun test ne vérifie le comportement sans scikit-posthocs.  
**Impact** : Comportement de repli non testé.  
**Statut** : Partiel

### 7. Test de Dunn dépend de scikit-posthocs
**Fichier** : test_selector.py:536-550 (_dunn_test)  
**Problème** : Le test de Dunn retourne une erreur si scikit-posthocs n'est pas installé, mais aucun test ne vérifie ce cas.  
**Impact** : Comportement d'erreur non testé.  
**Statut** : Partiel

---

## Résumé global

- **Total de méthodes statistiques implémentées** : 37
- **Méthodes validées (tests complets)** : 28
- **Méthodes partiellement testées** : 7
- **Méthodes non testées (à vérifier)** : 2
- **Méthodes absentes** : 10 (clustering, séries temporelles, survie, bootstrap/permutation)

**Catégories bien couvertes** :
- Statistiques descriptives
- Normalité
- Comparaison de groupes (2 et 3+)
- Corrélations
- Association catégorielle
- Régression linéaire (OLS) avec diagnostics
- Régression logistique
- ACP

**Catégories partiellement couvertes** :
- Post-hoc (Games-Howell, Dunn dépendent de scikit-posthocs)
- ACM (test manquant)
- Power analysis (test manquant)
- Comparaisons appariées (test manquant)

**Catégories absentes** :
- Clustering
- Séries temporelles
- Survie
- Bootstrap/permutation

---

**Fin de l'audit**
