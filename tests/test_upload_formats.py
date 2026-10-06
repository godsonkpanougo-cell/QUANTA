"""Contrat upload formats — verrouille le support .xls (incident 06/10).

Le backend whitelistait déjà .xls et load_and_diagnose appelle pd.read_excel,
mais le moteur xlrd (requis par pandas pour les .xls ; openpyxl ne lit que
.xlsx) était absent de requirements.txt → tout .xls échouait en prod avec
« Impossible de lire le fichier : Missing optional dependency 'xlrd' ».
Le frontend, lui, n'offrait même pas .xls dans le sélecteur (corrigé).
"""

from main import ALLOWED_UPLOAD_EXTENSIONS


def test_whitelist_backend_contient_xls():
    assert "xls" in ALLOWED_UPLOAD_EXTENSIONS
    assert "xlsx" in ALLOWED_UPLOAD_EXTENSIONS


def test_moteur_xlrd_disponible():
    """Le moteur de lecture .xls doit être installé — sinon pd.read_excel
    lève ImportError au premier .xls téléversé."""
    import xlrd

    version = getattr(xlrd, "__VERSION__", "0")
    major = int(str(version).split(".")[0])
    # xlrd >= 2.0 : lit .xls exclusivement (openpyxl couvre .xlsx)
    assert major >= 2, f"xlrd {version} trop ancien pour lire les .xls modernes"
