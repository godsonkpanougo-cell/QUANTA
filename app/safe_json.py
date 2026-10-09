"""
QUANTA — app/safe_json.py
V9/A1 — normalisation JSON des résultats d'analyse.

Module SANS AUCUNE DÉPENDANCE (stdlib seule). numpy est détecté par duck
typing (objets exposant .tolist() / .item()), jamais par import ni par
isinstance : importer ce module — ou db.py qui l'importe — ne tire JAMAIS
numpy dans sys.modules.

    python -c "import sys, db; print('numpy' in sys.modules)"  ->  False

API utilisées, vérifiées sur l'environnement installé (G9) :
  - math.isfinite(float) : stdlib ;
  - objet.tolist() : ndarray numpy -> list Python, scalaires numpy -> natif
    (np.float64('nan').tolist() -> float('nan'), np.array([...]).tolist()
    -> list) ;
  - objet.item()   : scalaires numpy (np.bool_/np.integer/np.floating) ->
    bool/int/float natif (repli pour un objet sans .tolist()) ;
  - les types natifs Python (bool/int/float/str/list/dict) n'exposent NI
    .tolist() NI .item() (vérifié) : aucun risque de confusion.

Points de passage (V9) :
  (a) sortie de orchestrator.run_full_analysis ;
  (b) lecture db.get_analysis / db.get_analysis_internal /
      db.find_cached_analysis (lignes héritées déjà stockées avec NaN).
"""
from __future__ import annotations

import math
from typing import Any


def sanitize_nonfinite(obj: Any) -> Any:
    """
    Remplace récursivement les valeurs non finies (NaN, +inf, -inf) par None,
    et convertit les scalaires/tableaux numpy en types natifs JSON.

    Motif : json.dumps accepte NaN par défaut (littéral `NaN` stocké, JSON non
    strict) et tout sérialiseur strict (starlette allow_nan=False) lèverait
    ValueError -> 500.
    """
    if isinstance(obj, dict):
        return {k: sanitize_nonfinite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_nonfinite(v) for v in obj]
    # Duck typing numpy, sans import : les tableaux exposent .tolist()
    # (-> list, repris récursivement) et les scalaires .tolist()/.item()
    # (-> natif, repris récursivement).
    tolist = getattr(obj, "tolist", None)
    if callable(tolist):
        return sanitize_nonfinite(tolist())
    item = getattr(obj, "item", None)
    if callable(item):
        return sanitize_nonfinite(item())
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    return obj
