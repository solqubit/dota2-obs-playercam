"""error.log del .exe: sin ventana (los avisos se reemplazan por un falso)."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys  # noqa: E402

import pytest  # noqa: E402

from overpower_cams import app  # noqa: E402


@pytest.fixture(autouse=True)
def _aviso_nuevo(monkeypatch):
    monkeypatch.setattr(app, "_crash_shown", False)


def _boom():
    try:
        raise RuntimeError("se rompió algo")
    except RuntimeError:
        return sys.exc_info()


def test_write_error_log_agrega_fecha_y_traceback(tmp_path):
    path = app.write_error_log(*_boom(), base=tmp_path)
    assert path == tmp_path / "error.log"
    app.write_error_log(*_boom(), base=tmp_path)            # se agrega, no se pisa
    texto = path.read_text(encoding="utf-8")
    assert texto.count("RuntimeError: se rompió algo") == 2
    assert texto.count("Traceback (most recent call last)") == 2
    assert texto.startswith("=== 20")                       # fecha y hora


def test_write_error_log_no_lanza_si_no_puede_escribir(tmp_path):
    assert app.write_error_log(*_boom(), base=tmp_path / "no_existe") is None


def test_handle_crash_avisa_una_sola_vez_pero_anota_siempre(tmp_path):
    avisos = []
    app.handle_crash(*_boom(), base=tmp_path, show=avisos.append)
    app.handle_crash(*_boom(), base=tmp_path, show=avisos.append)
    assert avisos == [tmp_path / "error.log"]
    assert (tmp_path / "error.log").read_text(encoding="utf-8").count("RuntimeError: se rompió algo") == 2


def test_excepthook_instalado_anota_en_el_error_log(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(app, "_show_crash", lambda path: None)
    original = sys.excepthook
    monkeypatch.setattr(sys, "excepthook", original)        # se restaura al terminar
    app.install_excepthook()
    sys.excepthook(*_boom())
    log = tmp_path / "OverPowerCamarasDota" / "error.log"
    assert "se rompió algo" in log.read_text(encoding="utf-8")


def test_main_anota_el_error_de_arranque(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(app, "_show_crash", lambda path: None)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(app, "_run", lambda: (_ for _ in ()).throw(RuntimeError("falló al arrancar")))
    assert app.main() == 1
    log = tmp_path / "OverPowerCamarasDota" / "error.log"
    assert "falló al arrancar" in log.read_text(encoding="utf-8")
