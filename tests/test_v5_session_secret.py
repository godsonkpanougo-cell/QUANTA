"""
V5 (audit §8.2) — fail-fast SESSION_SECRET_KEY.

En PRODUCTION, l'absence de SESSION_SECRET_KEY doit faire échouer le
démarrage (raise au chargement de main). En DÉVELOPPEMENT, l'absence ne
doit JAMAIS bloquer (le poste de Godson doit continuer à tourner).

Les tests lancent un sous-processus `python -c "import main"` avec
l'environnement contrôlé : c'est le vrai chemin de démarrage, pas une
simulation.
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Variables qui influencent la détection d'environnement / la clé : on les
# neutralise TOUTES dans les sous-processus pour un comportement déterministe.
CONTROLLED_VARS = (
    "SESSION_SECRET_KEY", "QUANTA_ENV", "ENVIRONMENT", "APP_ENV",
    "RENDER", "RENDER_SERVICE_NAME",
)


def _run_startup(extra_env: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in CONTROLLED_VARS}
    # Les variables contrôlées sont posées À VIDE plutôt que supprimées :
    # main.py:119 appelle load_dotenv() qui recharge .env pendant l'import
    # (une clé SESSION_SECRET_KEY locale s'y trouve) et python-dotenv
    # n'écrase pas une variable déjà présente — la valeur vide tient donc
    # jusqu'au fail-fast testé. Cause identifiée par un 1er run en échec.
    env.update({k: "" for k in CONTROLLED_VARS})
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_demarrage_refuse_en_prod_sans_session_secret_key():
    """Production + clé absente = import de main doit ÉCHOUER avec le
    message V5 explicite (pas un simple warning)."""
    proc = _run_startup({"ENVIRONMENT": "production"})
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, (
        "le démarrage en production sans SESSION_SECRET_KEY doit échouer\n"
        f"sortie : {combined[-2000:]}"
    )
    assert "SESSION_SECRET_KEY" in combined, (
        f"le message d'erreur doit nommer SESSION_SECRET_KEY\nsortie : {combined[-2000:]}"
    )


def test_demarrage_autorise_en_prod_avec_session_secret_key():
    """Production + clé présente = le démarrage doit aboutir."""
    proc = _run_startup({
        "ENVIRONMENT": "production",
        "SESSION_SECRET_KEY": "cle-de-test-unique-et-non-secrete",
    })
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, (
        f"le démarrage en production avec clé doit réussir\nsortie : {combined[-2000:]}"
    )


def test_dev_sans_session_secret_key_ne_bloque_pas():
    """Développement + clé absente = warning seul, le démarrage ABOUTIT
    (le poste de travail de Godson ne doit jamais être bloqué)."""
    proc = _run_startup({})  # aucun marqueur ni prod ni dev -> défaut dev
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, (
        f"le démarrage en dev sans clé ne doit pas bloquer\nsortie : {combined[-2000:]}"
    )
    assert "SESSION_SECRET_KEY" in combined, (
        f"l'avertissement dev doit mentionner SESSION_SECRET_KEY\nsortie : {combined[-2000:]}"
    )
