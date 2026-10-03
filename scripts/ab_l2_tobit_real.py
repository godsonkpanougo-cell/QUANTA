"""A/B sur le DATASET REEL L2_tobit.dta (fourni par Godson le 01/10/2026).

Objectif : preuves de non-regression + timings des 2 optimisations P1-bis
sur les vraies donnees de la run prod 0090a4af, AVANT branchement :
  1. Correlation : correlation_analysis prod (boucle + heatmap + scatters)
     vs compute_correlation_pairs (fast) -> r/p/paires significatives/top-5.
  2. ACM : run_acm prod complet (fit + coords + plots en boucle) vs
     build_acm_plot (fast, plafond 25 modalites par contribution).
  3. Budget projete Render (CPU Render ~16x plus lent que local, mesure
     plots ACM prod 307 ms/modalite vs 19 ms local).

Le dataset utilisateur n'est JAMAIS commite (data/uploads/ est gitignore).
"""
from __future__ import annotations

import base64
import hashlib
import io
import re
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compute.upload_validation import load_and_diagnose
from app.compute.correlation_fast import compute_correlation_pairs
from app.compute.acm_plot_fast import build_acm_plot, contributions_rank_map
from app.compute.compute import correlation_analysis, run_acm

DATA = ROOT / "data" / "uploads" / "L2_tobit.dta"
RENDER_SLOWDOWN = 16.0  # 307 ms/modalite Render vs 19 ms local (run 0090a4af)


def h(b64):
    if not b64:
        return "None"
    return hashlib.sha256(base64.b64decode(b64)).hexdigest()[:12]


def prod_pairs_and_significant(df, numeric_cols, method):
    """Replique FIDELE de la boucle prod (~753-790), sans plots ni heatmap."""
    from scipy.stats import pearsonr, spearmanr
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


def ab_correlation(df, numeric_cols, method):
    print("=" * 72)
    print(f"CORRELATION {method.upper()} sur donnees reelles")
    print("=" * 72)
    normality = {}
    if method == "pearson":
        normality = {c: {"conclusion": "NORMALE"} for c in numeric_cols}

    t0 = time.time()
    prod = correlation_analysis(df, numeric_cols, normality, theme="dark")
    t_prod_full = time.time() - t0

    t0 = time.time()
    loop_pairs, loop_sig = prod_pairs_and_significant(df, numeric_cols, method)
    t_loop = time.time() - t0

    t0 = time.time()
    fast = compute_correlation_pairs(df, numeric_cols, method)
    t_fast = time.time() - t0

    ok = prod.get("method") == method
    ok_keys = set(loop_pairs) == set(fast["pairs"])
    max_dr = max_dp = max_dpm = 0.0
    identical_fields = True
    diffs = []
    for key, ref in loop_pairs.items():
        got = fast["pairs"].get(key)
        if got is None:
            identical_fields = False
            diffs.append(f"paire manquante {key}")
            break
        max_dr = max(max_dr, abs(ref["r"] - got["r"]))
        max_dp = max(max_dp, abs(ref["p_value"] - got["p_value"]))
        for f in ("n", "decision", "strength", "direction"):
            if ref[f] != got[f]:
                identical_fields = False
                diffs.append(f"{key}.{f}: {ref[f]!r} vs {got[f]!r}")
    # p_matrix prod (BANCHEE apres branchement) vs fast brut, hors diagonal :
    # la prod initialise la diagonale a 1.0 (np.ones jamais ecrasee) ; le
    # module fast expose p=0 sur la diagonale -> compute.py la reforce a 1.0
    # pour non-regression payload (fill_diagonal). Comparaison hors diagonale.
    ref_pm = prod["p_matrix"]
    for c1, row in ref_pm.items():
        for c2, pv in row.items():
            if c1 == c2:
                continue
            fv = fast["p_matrix"].get(c1, {}).get(c2)
            if fv is not None:
                max_dpm = max(max_dpm, abs(float(pv) - float(fv)))

    sig_ref_sorted = sorted(loop_sig, key=lambda x: x[0])
    sig_fast_sorted = sorted(fast["significant_pairs"], key=lambda x: x[0])
    sig_ok = [x[0] for x in sig_ref_sorted] == [x[0] for x in sig_fast_sorted]

    # top-5 scatter prod (clefs des scatters generes) vs top-5 fast par |r|
    top5_fast = [x[0] for x in sorted(fast["significant_pairs"],
                                      key=lambda x: x[3], reverse=True)[:5]]
    top5_prod = list(prod["scatter_plots"].keys())
    top5_ok = top5_prod == top5_fast

    print(f"methode prod={prod.get('method')} | paires={len(loop_pairs)}")
    print(f"clefs identiques: {ok_keys} | champs identiques: {identical_fields} "
          f"({len(diffs)} ecarts)")
    print(f"max delta r: {max_dr:.2e} | max delta p: {max_dp:.2e} "
          f"| max delta p_matrix: {max_dpm:.2e}")
    print(f"paires significatives identiques: {sig_ok} ({len(loop_sig)} paires)")
    print(f"top-5 scatter identiques: {top5_ok}")
    print(f"temps chemin prod complet (boucle+heatmap+5 scatters): {t_prod_full:.3f}s")
    print(f"temps boucle prod seule: {t_loop:.3f}s -> projete Render ~{t_loop * RENDER_SLOWDOWN:.1f}s")
    print(f"temps fast ({fast['path']}): {t_fast:.3f}s -> projete Render ~{t_fast * RENDER_SLOWDOWN:.1f}s")
    print(f"GAIN boucle: {t_loop / max(t_fast, 1e-9):.1f}x (local)")
    ok = (ok and ok_keys and identical_fields and max_dr <= 1e-4
          and max_dp <= 1e-4 and sig_ok and top5_ok)
    print(f"VERDICT: {'OK' if ok else 'ECHEC'}")
    return ok, {"t_loop": t_loop, "t_fast": t_fast, "t_prod_full": t_prod_full,
                "n_sig": len(loop_sig)}


def ab_acm(df, cat_cols):
    print("=" * 72)
    print("ACM sur donnees reelles : run_acm prod vs build_acm_plot fast")
    print("=" * 72)
    buf = io.StringIO()
    t0 = time.time()
    with redirect_stdout(buf):
        res = run_acm(df, cat_cols)
    t_prod_total = time.time() - t0
    timings = dict(re.findall(r"TIMING - ([\w ]+): ([\d.]+)s", buf.getvalue()))
    for k, v in timings.items():
        print(f"  prod {k.strip()}: {v}s")
    if res.get("status") != "ok":
        print(f"ACM PROD EN ERREUR: {res.get('error')}")
        return False, {}
    coords = res["modalities_coords"]
    inertia = res["inertia_pct"]
    t_plots_prod = float(timings.get("ACM plots generation", "0"))
    t_fit_prod = float(timings.get("ACM fit MCA", "0"))
    t_coords_prod = float(timings.get("ACM column_coordinates", "0"))
    print(f"modalites={len(coords)} | prod plan hash={h(res['plan_factoriel'])}")

    # Fast : refit MCA strictement identique aux params prod + plot plafonne
    import prince
    df_cat = df[cat_cols].dropna().astype(str)
    n_comp = min(5, len(cat_cols) - 1)
    n_iter = min(10, len(df_cat) - 1)
    t0 = time.time()
    mca = prince.MCA(n_components=n_comp, n_iter=n_iter, random_state=42,
                     engine="sklearn").fit(df_cat)
    t_fit_local = time.time() - t0
    cmap = contributions_rank_map(mca.column_contributions_)
    t0 = time.time()
    fast_b64 = build_acm_plot(coords, inertia, cat_cols, theme="dark",
                              contributions_map=cmap)
    t_fast_plot = time.time() - t0

    n = len(coords)
    parity = (h(fast_b64) == h(res["plan_factoriel"])) if n <= 25 else None
    print(f"n_modalites={n} -> plafond {'NON actif (<=25), parite attendue' if parity is not None else 'ACTIF (>25)'}")
    print(f"refit MCA local (params prod): {t_fit_local:.3f}s")
    print(f"prod plots: {t_plots_prod:.3f}s (hash {h(res['plan_factoriel'])})")
    print(f"fast plots: {t_fast_plot:.3f}s (hash {h(fast_b64)})")
    if parity is not None:
        print(f"PARITE BYTE-A-BYTE: {parity}")
    print(f"GAIN plots: {t_plots_prod / max(t_fast_plot, 1e-9):.1f}x (local)")
    print(f"projete Render: prod plots ~{t_plots_prod * RENDER_SLOWDOWN:.1f}s "
          f"-> fast ~{t_fast_plot * RENDER_SLOWDOWN:.1f}s")
    ok = bool(fast_b64) and (parity is None or parity)
    print(f"VERDICT: {'OK' if ok else 'ECHEC'}")
    return ok, {"n": n, "t_plots_prod": t_plots_prod, "t_fast_plot": t_fast_plot,
                "t_fit": t_fit_local, "parity": parity}


if __name__ == "__main__":
    file_bytes = DATA.read_bytes()
    t0 = time.time()
    diag = load_and_diagnose(file_bytes, "L2_tobit.dta")
    t_diag = time.time() - t0
    if "error" in diag:
        print(f"ERREUR CHARGEMENT: {diag['error']}")
        sys.exit(1)
    df = diag["dataframe"]
    numeric_cols = diag["numeric_cols"]
    cat_cols = diag["cat_cols"]
    print("=" * 72)
    print("DIAGNOSTIC load_and_diagnose (chemin prod exact)")
    print("=" * 72)
    print(f"shape: {diag['n_rows']} x {diag['n_cols']} (charge en {t_diag:.2f}s)")
    print(f"numeric_cols: {len(numeric_cols)} -> {len(numeric_cols) * (len(numeric_cols) - 1) // 2} paires")
    print(f"cat_cols: {len(cat_cols)} | id_cols: {len(diag['id_cols'])} "
          f"({diag['id_cols']}) | freetext: {len(diag['freetext_cols'])}")
    print(f"reclassifiees numerique->categoriel: {len(diag['reclassified_as_categorical'])}")

    all_ok = True
    ok_s, m_s = ab_correlation(df, numeric_cols, "spearman")
    all_ok &= ok_s
    ok_p, m_p = ab_correlation(df, numeric_cols, "pearson")
    all_ok &= ok_p
    ok_a, m_a = ab_acm(df, cat_cols)
    all_ok &= ok_a

    print("=" * 72)
    print("BUDGET PROJETE RENDER (extrapolation x16, pipeline statistique seul)")
    print("=" * 72)
    if ok_a and ok_s:
        # Prod: boucle correlation (estimee via boucle locale) + fit/coords/plots ACM
        prod_render = (m_s["t_loop"] + m_p["t_loop"]) * RENDER_SLOWDOWN \
            + (m_a["t_fit"] + 0.5 + m_a["t_plots_prod"]) * RENDER_SLOWDOWN
        fast_render = (m_s["t_fast"] + m_p["t_fast"]) * RENDER_SLOWDOWN \
            + (m_a["t_fit"] + 0.5 + m_a["t_fast_plot"]) * RENDER_SLOWDOWN
        print(f"avant optimisations (projete): {prod_render:.1f}s")
        print(f"apres optimisations (projete): {fast_render:.1f}s")
        print(f"gain attendu: {prod_render - fast_render:.1f}s")
    print("CONCLUSION GLOBALE:", "OK" if all_ok else "ECHEC")
    sys.exit(0 if all_ok else 1)
