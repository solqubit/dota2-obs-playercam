"""Comprueba el cierre nativo: una aserción aprobada no garantiza que Python salga bien."""
import os
from pathlib import Path
import subprocess
import sys


def test_pagina_ajustes_termina_el_proceso_sin_fallo_nativo():
    # Este caso aprobaba sus aserciones y luego abortaba en pyside6.abi3.dll.
    # Un proceso hijo permite comprobar el cierre real de Qt, fuera de pytest.
    result = subprocess.run(
        [sys.executable, "-B", "-X", "faulthandler", "-m", "pytest",
         "-p", "no:cacheprovider", "tests/test_gui_smoke.py::test_pagina_de_ajustes", "-q"],
        cwd=Path(__file__).resolve().parent.parent,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
