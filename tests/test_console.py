"""La consola delgada no necesita Qt y no arranca nada al importarse."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(code: str) -> str:
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_la_consola_no_importa_pyside6():
    _run("import console, sys; assert 'PySide6' not in sys.modules")


def test_importar_la_consola_no_arranca_nada():
    out = _run("import console, threading;"
               "assert threading.active_count() == 1;"
               "print('listo')")
    assert out.strip() == "listo"   # sin banner ni salida: todo va bajo __main__


def test_la_consola_avisa_el_bando_y_el_modo_al_arrancar():
    import console as consola
    from overpower_cams.storage import LiveState
    oculto = consola.startup_lines(LiveState(2, "hidden"))
    assert "Radiant = Equipo 2" in oculto[0] and "Dire = Equipo 1" in oculto[0]
    assert oculto[1] == "[AUTO] Modo: Ocultar todo — escribe 'auto' para reanudar"
    auto = consola.startup_lines(LiveState(1, "auto"))
    assert "Automático" in auto[1]
