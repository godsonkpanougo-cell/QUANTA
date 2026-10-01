"""Test de régression P1-bis : app.compute.acm_plot_fast.

Verrouille :
  - select_modalities : comportement prod sous le plafond (tout labellisé),
    top-N par contribution au-delà, repli par ordre sans contributions ;
  - build_acm_plot : rendu byte-à-byte IDENTIQUE à compute._generate_acm_plot
    sous le plafond (matplotlib déterministe), PNG valide au-delà ;
  - contributions_rank_map : conversion DataFrame prince -> {modalite: score}.
Test rapide (aucun LLM, aucun réseau).
"""
from __future__ import annotations

import base64

import numpy as np
import pandas as pd
import pytest

from app.compute.acm_plot_fast import (
    DEFAULT_MAX_LABELED,
    build_acm_plot,
    contributions_rank_map,
    select_modalities,
)

CATS = [f"var{j}" for j in range(4)]
INERTIA = [34.8, 32.8, 32.4]


def _coords(n_vars: int = 4, levels: int = 5, seed: int = 1):
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


def test_select_under_cap_all_labeled():
    coords = _coords()  # 20 <= 25
    labeled, gray = select_modalities(coords, None)
    assert len(labeled) == len(coords) == 20
    assert gray == []
    assert [m["modalite"] for m in labeled] == [m["modalite"] for m in coords]


def test_select_over_cap_top_n_by_contribution():
    coords = _coords(n_vars=6, levels=30)  # 180
    rng = np.random.default_rng(7)
    contribs = {m["modalite"]: float(rng.random()) for m in coords}
    labeled, gray = select_modalities(coords, contribs, max_labeled=25)
    assert len(labeled) == 25
    assert len(gray) == 155
    assert len(labeled) + len(gray) == len(coords)
    expected_top = {
        name
        for name, _ in sorted(contribs.items(), key=lambda kv: -kv[1])[:25]
    }
    assert {m["modalite"] for m in labeled} == expected_top


def test_select_over_cap_without_contributions_uses_order():
    coords = _coords(n_vars=6, levels=30)
    labeled, gray = select_modalities(coords, None)
    assert [m["modalite"] for m in labeled] == [m["modalite"] for m in coords[:25]]
    assert len(gray) == 155


def test_contributions_rank_map_from_prince_df():
    df = pd.DataFrame(
        {"0": [0.4, 0.1], "1": [0.2, 0.3], "2": [0.9, 0.9]},
        index=["var0_a", "var1_b"],
    )
    out = contributions_rank_map(df)
    assert out == {"var0_a": pytest.approx(0.6), "var1_b": pytest.approx(0.4)}
    assert contributions_rank_map(None) == {}


def test_build_under_cap_matches_prod_bytes():
    from app.compute.compute import _generate_acm_plot

    coords = _coords(seed=1)
    prod_b64 = _generate_acm_plot(coords, INERTIA, CATS)
    fast_b64 = build_acm_plot(coords, INERTIA, CATS)
    assert prod_b64 and fast_b64
    assert base64.b64decode(fast_b64) == base64.b64decode(prod_b64)


def test_build_over_cap_returns_valid_png():
    coords = _coords(n_vars=6, levels=30)
    rng = np.random.default_rng(7)
    contribs = {m["modalite"]: float(rng.random()) for m in coords}
    b64 = build_acm_plot(coords, INERTIA, CATS, contributions_map=contribs)
    assert b64
    raw = base64.b64decode(b64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(b64) > 1000


def test_default_cap_value():
    assert DEFAULT_MAX_LABELED == 25
