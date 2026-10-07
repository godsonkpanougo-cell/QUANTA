"""
V6 (audit §8.2) — sortie de sous-processus bornée.

_read_output_tail() doit lire AU PLUS N octets de la queue du flux, quelle
que soit la taille réelle de la sortie du worker. Les logs de diagnostic
existent déjà ailleurs sous forme de troncatures [-6000:]/[-3000:] : ce
test verrouille le mécanisme de lecture bornée qui les alimente.
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


def test_tail_bornee_sur_grande_sortie():
    """Une sortie de 1 Mo ne doit faire lire que la queue bornée."""
    marker = "FIN_WORKER_MARK"
    with tempfile.TemporaryFile() as f:
        f.write(b"x" * (1024 * 1024))
        f.write(marker.encode())
        tail = main._read_output_tail(f)

    assert tail.endswith(marker), "la queue doit contenir la fin de la sortie"
    assert len(tail.encode("utf-8", errors="replace")) <= main.SUBPROCESS_OUTPUT_TAIL_BYTES + len(marker), (
        f"lecture non bornée : {len(tail)} caractères lus"
    )


def test_tail_integre_sur_petite_sortie():
    """Une sortie plus petite que le cap doit être retournée telle quelle."""
    with tempfile.TemporaryFile() as f:
        f.write("petite sortie avec accents é à ç\n".encode())
        tail = main._read_output_tail(f)
    assert tail == "petite sortie avec accents é à ç\n"


def test_tail_bornes_personnalisees():
    """Le paramètre max_bytes borne explicitement la lecture."""
    with tempfile.TemporaryFile() as f:
        f.write(b"ABCDEFGH" * 1000)  # 8000 octets
        tail = main._read_output_tail(f, max_bytes=100)
    assert len(tail.encode()) <= 100
    assert tail.endswith("ABCDEFGH")


def test_tail_decodage_utf8_partiel():
    """Une coupe au milieu d'un caractère multibyte ne doit pas lever
    d'erreur de décodage (errors='replace')."""
    with tempfile.TemporaryFile() as f:
        f.write("é".encode("utf-8") * 50)  # 100 octets, 'é' = 2 octets
        f.write(b"END")
        # Coupe à un nombre impair d'octets : coupe au milieu d'un 'é'
        tail = main._read_output_tail(f, max_bytes=21)
    assert tail.endswith("END")
