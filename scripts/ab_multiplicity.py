"""A/B P0 (pilier crédibilité) : impact de la correction de multiplicité
sur le DATASET REEL L2_tobit.dta (data/uploads/, jamais commité).

Preuve chiffrée demandée par le protocole symbole :
  - paires significatives p<0.05 BRUT vs Holm-Bonferroni (FWER) vs
    Benjamini-Hochberg (FDR), sur les paires de corrélation réelles ;
  - implémentation QUANTA validée contre l'oracle statsmodels ;
  - illustration du faux-positif attendu sous H0 (n_tests * alpha).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from statsmodels.stats.multitest import multipletests

from app.compute.upload_validation import load_and_diagnose
from app.compute.correlation_fast import compute_correlation_pairs
from app.compute.multiplicity import (
    benjamini_hochberg,
    count_significant_pairs,
    apply_fdr_correction_to_pairs,
    holm_bonferroni,
)

DATA = ROOT / "data" / "uploads" / "L2_tobit.dta"
ALPHA = 0.05

if __name__ == "__main__":
    ok = True
    file_bytes = DATA.read_bytes()
    diag = load_and_diagnose(file_bytes, "L2_tobit.dta")
    df = diag["dataframe"]
    numeric_cols = diag["numeric_cols"]
    n_tests = len(numeric_cols) * (len(numeric_cols) - 1) // 2

    fast = compute_correlation_pairs(df, numeric_cols, "spearman")
    pairs = fast["pairs"]
    p_raw = np.array([pairs[k]["p_value"] for k in pairs], dtype=float)

    q_holm = holm_bonferroni(p_raw)
    q_bh = benjamini_hochberg(p_raw)

    # 1) implémentation == oracle statsmodels sur les p réelles
    ref_holm = multipletests(p_raw, method="holm")[1]
    ref_bh = multipletests(p_raw, method="fdr_bh")[1]
    match_holm = bool(np.allclose(q_holm, ref_holm, atol=1e-12))
    match_bh = bool(np.allclose(q_bh, ref_bh, atol=1e-12))

    # 2) impact sur la famille réelle
    n_sig_raw = int((p_raw < ALPHA).sum())
    n_sig_holm = int((q_holm < ALPHA).sum())
    n_sig_bh = int((q_bh < ALPHA).sum())
    faux_positifs_attendus = n_tests * ALPHA

    print("=" * 72)
    print("CORRECTION DE MULTIPLICITE sur L2_tobit reel")
    print("=" * 72)
    print(f"famille: {n_tests} paires Spearman (p<0.05 brut)")
    print(f"sig. BRUT (comme les IA du marche) : {n_sig_raw}")
    print(f"sig. Holm-Bonferroni (FWER)        : {n_sig_holm}")
    print(f"sig. Benjamini-Hochberg (FDR)      : {n_sig_bh}")
    print(f"faux positifs attendus sous H0     : ~{faux_positifs_attendus:.0f}")
    print(f"implementations == oracle statsmodels: Holm={match_holm}, BH={match_bh}")

    # 3) branchement payload : p_adjusted ajoute, brut preserve
    corrected = apply_fdr_correction_to_pairs(dict(pairs), method="bh")
    counts = count_significant_pairs(corrected)
    sample_key = min(corrected, key=lambda k: corrected[k]["p_adjusted"])
    print(f"payload: p_adjusted ajoute a {len(corrected)} paires, brut intact: "
          f"{all(corrected[k]['p_value'] == pairs[k]['p_value'] for k in pairs)}")
    print(f"paire la plus robuste: {sample_key} "
          f"(r={corrected[sample_key]['r']}, p={corrected[sample_key]['p_value']}, "
          f"q={corrected[sample_key]['p_adjusted']})")
    print(f"counts: {counts}")

    ok = match_holm and match_bh and bool(counts["significant_raw"] >= n_sig_bh)
    print("CONCLUSION:", "OK" if ok else "ECHEC")
    sys.exit(0 if ok else 1)
