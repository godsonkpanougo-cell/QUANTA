"""A/B de non-régression P1-bis : boucle prod vs correlation_fast.

Compare, sur plusieurs régimes de données (sans/avec NaN, pearson/spearman,
petit/grand) :
  1. identité des paires : mêmes clés, mêmes r (±1e-4), mêmes p (±1e-4),
     mêmes n, mêmes décisions/strength/direction ;
  2. identité des paires significatives (même liste triée par |r| après sort) ;
  3. timings (gain attendu sur le régime grand sans NaN).
Script A/B (comme test_correlation_timing.py) : jetable, ne se branche pas
dans l'app sans mandat du directeur.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from app.compute.correlation_fast import choose_method, compute_correlation_pairs
from app.compute.compute import correlation_analysis


def prod_pairs_and_significant(df, numeric_cols, method):
    """Réplique FIDÈLE de la boucle prod (~753-790), sans plots ni heatmap."""
    pairs = {}
    significant_pairs = []
    for i, c1 in enumerate(numeric_cols):
        for j, c2 in enumerate(numeric_cols):
            if i < j:
                s1 = df[c1].dropna()
                s2 = df[c2].dropna()
                common = s1.index.intersection(s2.index)
                if len(common) >= 3:
                    if method == "pearson":
                        r, p = pearsonr(s1[common], s2[common])
                    else:
                        r, p = spearmanr(s1[common], s2[common])
                    pair_key = f"{c1} x {c2}"
                    pairs[pair_key] = {
                        "r": round(float(r), 4),
                        "p_value": round(float(p), 5),
                        "n": len(common),
                        "decision": "Corrélation significative (p<0.05)" if p < 0.05
                                    else "Pas de corrélation significative",
                        "strength": (
                            "Très forte" if abs(r) >= 0.8 else
                            "Forte"      if abs(r) >= 0.6 else
                            "Modérée"    if abs(r) >= 0.4 else
                            "Faible"     if abs(r) >= 0.2 else "Négligeable"
                        ),
                        "direction": "Positive" if r > 0 else "Négative",
                    }
                    if p < 0.05:
                        significant_pairs.append((pair_key, c1, c2, abs(r)))
    return pairs, significant_pairs


def compare(df, numeric_cols, method, label):
    print("=" * 72)
    print(f"RÉGIME : {label} (method={method})")
    print("=" * 72)

    normality = {c: {"conclusion": "NORMALE"} for c in numeric_cols}
    # La comparaison impose la MÊME méthode des deux côtés (le choix de
    # méthode réel en prod vient des résultats de normalité ; ici on teste
    # l'identité du calcul pour une méthode donnée).
    t0 = time.time()
    ref_pairs, ref_sig = prod_pairs_and_significant(df, numeric_cols, method)
    t_ref = time.time() - t0

    t0 = time.time()
    fast = compute_correlation_pairs(df, numeric_cols, method)
    t_fast = time.time() - t0

    ok_keys = set(ref_pairs) == set(fast["pairs"])
    max_dr = max_dp = 0.0
    identical_fields = True
    for key, ref in ref_pairs.items():
        got = fast["pairs"].get(key)
        if got is None:
            identical_fields = False
            break
        max_dr = max(max_dr, abs(ref["r"] - got["r"]))
        max_dp = max(max_dp, abs(ref["p_value"] - got["p_value"]))
        for f in ("n", "decision", "strength", "direction"):
            if ref[f] != got[f]:
                identical_fields = False
                print(f"  CHAMP DIFFÉRENT {key}.{f}: {ref[f]!r} vs {got[f]!r}")

    sig_ref_sorted = sorted(ref_sig, key=lambda x: x[0])
    sig_fast_sorted = sorted(fast["significant_pairs"], key=lambda x: x[0])
    sig_ok = [x[0] for x in sig_ref_sorted] == [x[0] for x in sig_fast_sorted]

    print(f"paires: {len(ref_pairs)} | clés identiques: {ok_keys} | "
          f"champs identiques: {identical_fields}")
    print(f"max delta r: {max_dr:.2e} | max delta p: {max_dp:.2e}")
    print(f"paires significatives identiques (même ordre trié): {sig_ok} "
          f"({len(ref_sig)} paires)")
    print(f"temps boucle prod : {t_ref:.3f}s")
    print(f"temps fast ({fast['path']}) : {t_fast:.3f}s  -> gain {t_ref / max(t_fast, 1e-9):.1f}x")
    ok = ok_keys and identical_fields and max_dr <= 1e-4 and max_dp <= 1e-4 and sig_ok
    print(f"VERDICT RÉGIME : {'OK' if ok else 'ÉCHEC'}")
    return ok


if __name__ == "__main__":
    from scipy.stats import pearsonr, spearmanr

    all_ok = True
    rng = np.random.default_rng(42)

    # Régime 1 : petit, sans NaN, pearson
    n, k = 60, 6
    df1 = pd.DataFrame(rng.normal(size=(n, k)), columns=[f"v{i}" for i in range(k)])
    cols1 = list(df1.columns)
    all_ok &= compare(df1, cols1, "pearson", "petit sans NaN (pearson)")

    # Régime 2 : avec NaN (dropna par paire -> fallback boucle fidèle)
    df2 = df1.copy()
    mask = rng.random(df2.shape) < 0.10
    for c in df2.columns:
        df2.loc[df2.sample(frac=0.1, random_state=1).index, c] = np.nan
    all_ok &= compare(df2, cols1, "pearson", "avec ~10% NaN (fallback fidèle)")

    # Régime 3 : grand sans NaN, pearson (le régime prod L2_tobit)
    n, k = 800, 45
    X = rng.normal(size=(n, k))
    X[:, 1] = X[:, 0] * 0.9 + rng.normal(scale=0.1, size=n)   # corrélations fortes
    X[:, 2] = -X[:, 0] * 0.7 + rng.normal(scale=0.2, size=n)
    df3 = pd.DataFrame(X, columns=[f"x{i}" for i in range(k)])
    cols3 = list(df3.columns)
    all_ok &= compare(df3, cols3, "pearson", "grand sans NaN 45 var = 990 paires (pearson)")

    # Régime 4 : grand sans NaN, spearman
    all_ok &= compare(df3, cols3, "spearman", "grand sans NaN 45 var (spearman)")

    # Régime 5 : non-normalité mixte (strength/direction sur Spearman)
    X5 = rng.normal(size=(n, k))
    X5[:, 0] = np.abs(X5[:, 0])          # distribution asymétrique
    df5 = pd.DataFrame(X5, columns=cols3)
    all_ok &= compare(df5, cols3, "spearman", "asymétrique spearman")

    print("\n" + "=" * 72)
    print(f"CONCLUSION GLOBALE : {'TOUT OK' if all_ok else 'AU MOINS UN ÉCHEC'}")
    print("=" * 72)
    sys.exit(0 if all_ok else 1)
