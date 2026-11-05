"""Cámara asistida en la ventana: tecla capturada (tecla física -> nombre de Dota), el diálogo y su fila
de Revisión. Sin Steam/Dota reales: todo en tmp_path."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # antes de crear QApplication

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

from overpower_cams import app, paths  # noqa: E402
from overpower_cams.checks import CheckResult  # noqa: E402
from overpower_cams.gui import checks_mixin  # noqa: E402
from overpower_cams.gui.assisted_dialog import AssistedKeyDialog, native_key_to_dota  # noqa: E402
from overpower_cams.gui.checks_mixin import pending_count  # noqa: E402
from overpower_cams.gui.widgets import StatusIcon  # noqa: E402
from overpower_cams.storage import Storage  # noqa: E402
from conftest import FakeObsClient  # noqa: E402

K = Qt.Key
KP = Qt.KeyboardModifier.KeypadModifier
NONE = Qt.KeyboardModifier.NoModifier
ASIST = "dota_toggle_assisted_camera_operator"


E = 0x100   # bit "extendida" del código de exploración (como lo entrega Qt en Windows)
F4, F11, TAB, SHIFT_L, ESC = 0x3E, 0x57, 0x0F, 0x2A, 0x01


@pytest.mark.parametrize("scan, vk, nombre", [
    (0x3B, 0x70, "F1"), (F4, 0x73, "F4"), (0x44, 0x79, "F10"), (F11, 0x7A, "F11"), (0x58, 0x7B, "F12"),
    (0x1E, 0x41, "A"), (0x10, 0x41, "Q"),          # AZERTY: la tecla de la Q escribe «a»: es Q
    (0x2C, 0x5A, "Z"), (0x02, 0x31, "1"), (0x0B, 0x30, "0"),
    # teclado español: la tecla física manda, no el carácter que escribe
    (0x0C, 0xDB, "-"),          # escribe «'» en ES; para Dota es «-»
    (0x0D, 0xDD, "="),          # escribe «¡» en ES
    (0x27, 0xC0, "SEMICOLON"),  # escribe «ñ» en ES
    (0x1A, 0xBA, "["),          # escribe «`» en ES
    (0x29, 0xDC, "`"),          # escribe «º» en ES
    (0x35, 0xBD, "/"),          # escribe «-» en ES
    (0x2B, 0xBF, "\\"),          # escribe «ç» en ES
    # teclado numérico sin Bloq Num (Qt diría End/Up…): sin bit extendido
    (0x4F, 0x23, "KP_END"), (0x48, 0x26, "KP_UPARROW"), (0x52, 0x2D, "KP_INS"),
    (0x4C, 0x0C, "KP_5"), (0x53, 0x2E, "KP_DEL"),
    # con Bloq Num: misma tecla física, mismo nombre
    (0x4F, 0x61, "KP_END"), (0x4C, 0x65, "KP_5"),
    (0x4A, 0x6D, "KP_MINUS"), (0x4E, 0x6B, "KP_PLUS"), (0x37, 0x6A, "KP_MULTIPLY"),
    (E | 0x35, 0x6F, "KP_SLASH"), (E | 0x1C, 0x0D, "KP_ENTER"),
    # bloque de navegación dedicado: con bit extendido
    (E | 0x4F, 0x23, "END"), (E | 0x47, 0x24, "HOME"), (E | 0x52, 0x2D, "INS"),
    (E | 0x53, 0x2E, "DEL"), (E | 0x49, 0x21, "PGUP"), (E | 0x51, 0x22, "PGDN"),
    (E | 0x48, 0x26, "UPARROW"), (E | 0x4B, 0x25, "LEFTARROW"),
    (0x39, 0x20, "SPACE"), (TAB, 0x09, "TAB"), (0x1C, 0x0D, "ENTER"), (0x0E, 0x08, "BACKSPACE"),
    # sin código de exploración: solo teclas virtuales que no dependen de la distribución
    (0, 0x73, "F4"), (0, 0x61, "KP_END"),
])
def test_native_key_to_dota(scan, vk, nombre):
    assert native_key_to_dota(scan, vk) == nombre


@pytest.mark.parametrize("scan, vk", [
    (SHIFT_L, 0x10), (0x1D, 0x11), (0x38, 0x12), (E | 0x38, 0xA5), (E | 0x5B, 0x5B),   # modificadores
    (ESC, 0x1B), (0x56, 0xE2),          # Escape; la tecla «<» de los teclados europeos
    (E | 0x37, 0x2C),                   # Imprimir pantalla
    (0, 0xDB), (0, 0x41), (0, 0),       # sin código de exploración y tecla de distribución
])
def test_native_key_to_dota_rechaza_lo_que_no_tiene_nombre_seguro(scan, vk):
    assert native_key_to_dota(scan, vk) is None


def _press(dlg, scan, vk=0, key=K.Key_unknown, mods=NONE):
    ev = QKeyEvent(QEvent.Type.KeyPress, int(key), mods, scan, vk, 0)
    dlg.event(ev)
    return ev


def _conflictos(key):
    return {"F4": ["Seleccionar mensajero"], "F10": ["Menú de comentarista"]}.get(key.upper(), [])


def test_dialogo_tecla_libre_permite_guardar(qapp):
    dlg = AssistedKeyDialog(None, None, _conflictos)
    assert "Pulsa la tecla que quieres usar para la cámara asistida" in dlg.prompt_label.text()
    assert not dlg.save_button.isEnabled() and not dlg.remove_button.isVisibleTo(dlg)
    _press(dlg, F11, 0x7A, K.Key_F11)
    assert dlg.key == "F11" and dlg.key_label.text() == "F11"
    assert dlg.save_button.isEnabled() and "libre" in dlg.status_label.text().lower()
    dlg.save_button.click()
    assert dlg.result() == QDialog.DialogCode.Accepted and dlg.remove_requested is False


def test_dialogo_tecla_ocupada_bloquea_guardar_y_dice_quien(qapp):
    dlg = AssistedKeyDialog(None, "F11", _conflictos)
    assert dlg.key_label.text() == "F11" and dlg.remove_button.isVisibleTo(dlg)
    _press(dlg, F4, 0x73, K.Key_F4)
    assert dlg.key == "F4" and not dlg.save_button.isEnabled()
    assert "Seleccionar mensajero" in dlg.status_label.text()
    _press(dlg, SHIFT_L, 0x10, K.Key_Shift)          # solo un modificador: no cambia nada
    assert dlg.key == "F4" and "solos no sirven" in dlg.status_label.text()
    _press(dlg, TAB, 0x09, K.Key_Tab)                # Tab no mueve el foco: es la tecla
    assert dlg.key == "TAB" and dlg.save_button.isEnabled()


def test_dialogo_rechaza_tecla_con_modificador_y_tecla_sin_nombre(qapp):
    dlg = AssistedKeyDialog(None, None, _conflictos)
    _press(dlg, F11, 0x7A, K.Key_F11, Qt.KeyboardModifier.ShiftModifier)
    assert dlg.key is None and "sin modificadores" in dlg.status_label.text()
    _press(dlg, F11, 0x7A, K.Key_F11, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    assert dlg.key is None and not dlg.save_button.isEnabled()
    _press(dlg, 0x56, 0xE2, K.Key_Less)                # «<» del teclado español: sin nombre seguro
    assert dlg.key is None and "Dota no conoce esa tecla" in dlg.status_label.text()
    _press(dlg, 0x4F, 0x23, K.Key_End, NONE)           # Num 1 sin Bloq Num, sin KeypadModifier
    assert dlg.key == "KP_END"
    _press(dlg, E | 0x4F, 0x23, K.Key_End, KP)         # Fin dedicada aunque Qt diga Keypad
    assert dlg.key == "END"


def test_dialogo_tecla_espanola_usa_la_posicion_us_y_su_conflicto(qapp):
    dlg = AssistedKeyDialog(None, None, lambda k: ["Repetición: más lento"] if k == "-" else [])
    _press(dlg, 0x0C, 0xDB, K.Key_Apostrophe)          # en ES escribe «'»
    assert dlg.key == "-" and "Repetición: más lento" in dlg.status_label.text()
    assert not dlg.save_button.isEnabled()


def test_dialogo_escape_cancela_y_quitar(qapp):
    dlg = AssistedKeyDialog(None, "F11", _conflictos)
    _press(dlg, ESC, 0x1B, K.Key_Escape)
    assert dlg.result() == QDialog.DialogCode.Rejected
    dlg = AssistedKeyDialog(None, "F11", _conflictos)
    dlg.remove_button.click()
    assert dlg.result() == QDialog.DialogCode.Accepted and dlg.remove_requested is True


def test_dialogo_misma_tecla_actual_no_hace_falta_guardar(qapp):
    dlg = AssistedKeyDialog(None, "F11", _conflictos)
    assert not dlg.save_button.isEnabled()           # todavía no eligió otra
    _press(dlg, F11, 0x7A, K.Key_F11)
    assert not dlg.save_button.isEnabled()


def test_info_no_cuenta_como_pendiente_y_su_icono_se_dibuja(qapp):
    res = [CheckResult("assisted_camera", "info", "t", "d"), CheckResult("x", "warn", "t", "d")]
    assert pending_count(res) == 1
    icon = StatusIcon("info")
    icon.grab()                                      # pinta sin errores


# ---------- en la ventana ----------

class FakeListener:
    def __init__(self, **callbacks):
        pass

    def start(self):
        pass

    def stop(self):
        pass


@pytest.fixture
def ventana(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    fake = FakeObsClient()
    fake.connect_error = ConnectionRefusedError("OBS cerrado")
    storage = Storage(paths.app_data_dir())
    parts = app.build_app(storage, steam=None, obs_client_factory=fake.factory, gsi_port=0,
                          keyboard_listener=FakeListener, mouse_listener=FakeListener,
                          get_rect=lambda: None, legacy_portraits=None)
    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    parts.settings.dota_dir = str(dota)
    win = app.create_window(parts, is_running=lambda exe: True)    # Dota abierto: igual se puede
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(("info", a[2])))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(("warn", a[2])))
    try:
        yield win, dota, avisos
    finally:
        win.close()


def _row(win, cid):
    return next(r for r in win.check_results if r.id == cid)


def test_fila_configurar_abre_el_dialogo_y_guarda(ventana, qapp, monkeypatch):
    win, dota, avisos = ventana
    win.run_checks()
    win.wait_background(5)
    r = _row(win, "assisted_camera")
    assert r.status == "info" and r.fix_label == "Configurar…"
    abiertos = []

    class FakeDialog:
        def __init__(self, parent, current, conflicts):
            abiertos.append(current)
            self.key, self.remove_requested = "F11", False

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(checks_mixin, "AssistedKeyDialog", FakeDialog)
    botones = win._row_buttons(r)
    assert [b.text() for b in botones] == ["Configurar…"]
    botones[0].click()
    win.wait_background(5)
    assert abiertos == [None]
    assert f'bind "F11" "{ASIST}"' in paths.autoexec_path(dota).read_text(encoding="utf-8")
    assert avisos and avisos[0][0] == "info" and "consola" in avisos[0][1]
    assert any("Cámara asistida" in line and "F11" in line for line in win.event_lines())
    r = _row(win, "assisted_camera")
    assert r.status == "ok" and r.fix_label == "Cambiar…"


def test_quitar_desde_la_ventana_y_error_se_avisa(ventana, qapp, monkeypatch):
    win, dota, avisos = ventana
    cfg = paths.autoexec_path(dota)
    cfg.parent.mkdir(parents=True)
    cfg.write_text(f"echo hola\nbind F11 {ASIST}\n", encoding="utf-8")
    win._apply_assisted(None)                        # Quitar
    win.wait_background(5)
    assert cfg.read_text(encoding="utf-8") == "echo hola\n"
    assert _row(win, "assisted_camera").status == "info"
    win._apply_assisted(None)                        # ya no está: aviso, sin romper nada
    win.wait_background(5)
    assert avisos[-1][0] == "warn"


def test_el_dialogo_recibe_los_conflictos_reales(ventana, qapp, monkeypatch, tmp_path):
    win, dota, avisos = ventana
    cfg = paths.user_keys_default_path(dota)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('"config"\n{\n\t"bindings"\n\t{\n\t\t"F10" "return_to_tools_from_engine"\n\t}\n}\n',
                   encoding="utf-8")
    vistos = {}

    class FakeDialog:
        def __init__(self, parent, current, conflicts):
            vistos["F10"] = conflicts("f10")
            vistos["F11"] = conflicts("F11")

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(checks_mixin, "AssistedKeyDialog", FakeDialog)
    win._open_assisted_dialog()
    assert vistos["F11"] == [] and "return_to_tools_from_engine" in vistos["F10"][0]
    assert not paths.autoexec_path(dota).exists()


def test_fila_en_aviso_ofrece_ver_instrucciones(ventana, qapp, monkeypatch):
    win, dota, avisos = ventana
    r = CheckResult("assisted_camera", "warn", "Cámara asistida", "F4 también la usa…", "Cambiar…",
                    "Los atajos de Dota le ganan")
    botones = win._row_buttons(r)
    assert [b.text() for b in botones] == ["Cambiar…", "Ver instrucciones"]
    botones[1].click()
    assert avisos[-1] == ("info", "Los atajos de Dota le ganan")
    ok = CheckResult("assisted_camera", "ok", "Cámara asistida", "F11 activa…", "Cambiar…", "x")
    assert [b.text() for b in win._row_buttons(ok)] == ["Cambiar…"]
