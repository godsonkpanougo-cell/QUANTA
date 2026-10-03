"""A/B ACM plots (auditeur) : prod _generate_acm_plot vs acm_plot_fast.

Cas 1 : 20 modalités (<= cap 25) -> parité attendue (hash PNG identique).
Cas 2 : 180 modalités + contributions -> timing prod vs fast plafonné.
Cas 3 : 180 modalités SANS contributions -> plafond par ordre de liste.
Script jetable : preuve collée dans le rapport, supprimé ensuite.
"""
from __future__ import annotations

import base64
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from app.compute.acm_plot_fast import build_acm_plot, select_modalities
from app.compute.compute import _generate_acm_plot

INERTIA = [34.8, 32.8, 32.4]
CATS = [f"var{j}" for j in range(6)]


def make_coords(n_vars: int, levels: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    return [
        {
            "modalite": f"var{j}_lvl{i}",
            "dim1": round(float(rng.normal()), 4),
            "dim2": round(float(rng.normal()), 4),
        }
        for j in range(n_vars)
        for i in range(levels)
    ]


def h(b64: str | None) -> str:
    if not b64:
        return "None"
    return hashlib.sha256(base64.b64decode(b64)).hexdigest()[:12]


if __name__ == "__main__":
    ok = True

    # CAS 1 : sous le plafond -> parité byte-à-byte attendue
    coords20 = make_coords(n_vars=4, levels=5, seed=1)  # 20 modalités
    t0 = time.time()
    prod_b64 = _generate_acm_plot(coords20, INERTIA, CATS)
    t_prod = time.time() - t0
    t0 = time.time()
    fast_b64 = build_acm_plot(coords20, INERTIA, CATS)
    t_fast = time.time() - t0
    same = h(prod_b64) == h(fast_b64)
    print("CAS 1 (20 modalités, <= cap 25) : parité")
    print(f"  prod hash={h(prod_b64)} ({t_prod:.2f}s)")
    print(f"  fast hash={h(fast_b64)} ({t_fast:.2f}s)")
    print(f"  HASH IDENTIQUES: {same}")
    ok &= bool(prod_b64 and fast_b64) and same

    # CAS 2 : 180 modalités + contributions -> timing
    coords180 = make_coords(n_vars=6, levels=30, seed=42)
    rng = np.random.default_rng(7)
    contribs = {m["modalite"]: float(rng.random()) for m in coords180}
    labeled, gray = select_modalities(coords180, contribs, 25)
    print(f"\nCAS 2 (180 modalités, cap 25) : labeled={len(labeled)}, gray={len(gray)}")
    t0 = time.time()
    prod_b64 = _generate_acm_plot(coords180, INERTIA, CATS)
    t_prod = time.time() - t0
    t0 = time.time()
    fast_b64 = build_acm_plot(coords180, INERTIA, CATS, contributions_map=contribs)
    t_fast = time.time() - t0
    print(f"  prod: {len(prod_b64)} car ({t_prod:.2f}s) hash={h(prod_b64)}")
    print(f"  fast: {len(fast_b64)} car ({t_fast:.2f}s) hash={h(fast_b64)}")
    print(f"  gain: {t_prod / max(t_fast, 1e-9):.1f}x")
    ok &= bool(prod_b64 and fast_b64)

    # CAS 3 : 180 modalités SANS contributions (ordre de liste)
    fast_b64 = build_acm_plot(coords180, INERTIA, CATS)
    labeled, gray = select_modalities(coords180, None, 25)
    print(f"\nCAS 3 (sans contributions) : labeled={len(labeled)}, gray={len(gray)}, "
          f"fast rendu: {bool(fast_b64)}")
    ok &= bool(fast_b64)

    print("\nCONCLUSION GLOBALE:", "OK" if ok else "ECHEC")
    sys.exit(0 if ok else 1)
