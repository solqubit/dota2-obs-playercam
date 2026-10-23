"""Pruebas de humo de la ventana: sin OBS real, sin Steam real, sin %APPDATA% real y
con el servidor GSI en un puerto libre (port=0)."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # antes de crear QApplication

import shutil  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from overpower_cams import app, config, paths  # noqa: E402
from overpower_cams.dota_keys import parse_player_keys  # noqa: E402
from overpower_cams.gsi_server import GsiServer  # noqa: E402
from overpower_cams.gui.settings_dialog import SettingsDialog  # noqa: E402
from overpower_cams.portraits import PortraitModel  # noqa: E402
from overpower_cams.storage import Settings, Storage  # noqa: E402
from tests.conftest import FakeObsClient  # noqa: E402

DATA = Path(__file__).parent / "data"


class FakeListener:
    def __init__(self, **callbacks):
        self.callbacks = callbacks

    def start(self):
        pass

    def stop(self):
        pass


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return tmp_path


def _obs_cerrado():
    fake = FakeObsClient()
    fake.connect_error = ConnectionRefusedError("OBS cerrado")
    return fake


def _armar(fake, steam=None):
    storage = Storage(paths.app_data_dir())
    parts = app.build_app(storage, steam=steam, obs_client_factory=fake.factory, gsi_port=0,
                          keyboard_listener=FakeListener, mouse_listener=FakeListener,
                          get_rect=lambda: None, legacy_portraits=None)
    parts.gsi.start()
    win = app.create_window(parts, is_running=lambda exe: False)
    return parts, win


def _esperar(qapp, win):
    win.wait_background(5)
    qapp.processEvents()


def _steam_con_teclas(tmp_path):
    cfg = tmp_path / "Steam" / "userdata" / "123" / "570" / "remote" / "cfg"
    cfg.mkdir(parents=True)
    shutil.copy(DATA / "dotakeys_ejemplo.lst", cfg / "dotakeys_personal.lst")
    return tmp_path / "Steam", cfg / "dotakeys_personal.lst"


def test_ventana_se_arma_sin_obs(qapp, appdata):
    parts, win = _armar(_obs_cerrado())
    try:
        assert win.windowTitle() == config.APP_NAME
        assert str(paths.app_data_dir()).startswith(str(appdata))
        win.show()
        win.tick()                       # un ciclo del timer: lanza el intento de conexión
        _esperar(qapp, win)
        win.tick()
        texto = win.obs_label.text()
        assert "OBS" in texto and "reconectando" in texto
        assert parts.obs.connected is False
        assert "sin datos" in win.dota_label.text()
        assert win.timer.isActive()
        # las revisiones llegan desde otro hilo y arman una fila por revisión
        assert [r.id for r in win.check_results] == [
            "dota", "gsi_cfg", "gsi_data", "keys", "obs", "scene", "player_scenes",
            "move_filters", "scene_images", "portraits"]
        assert next(r for r in win.check_results if r.id == "obs").status == "error"
    finally:
        win.close()
    assert parts.gsi._httpd is None      # al cerrar se detiene el servidor GSI


def test_obs_conectado_se_ve_en_la_barra(qapp, appdata):
    fake = FakeObsClient()
    parts, win = _armar(fake)
    try:
        win.tick()
        _esperar(qapp, win)
        win.tick()
        assert parts.obs.connected is True
        assert "conectado" in win.obs_label.text() and "reconectando" not in win.obs_label.text()
        # OBS se cierra con la app quieta: el chequeo periódico lo detecta
        fake.dead = True
        fake.connect_error = ConnectionRefusedError("OBS cerrado")
        win._last_obs_try = float("-inf")
        win.tick()
        _esperar(qapp, win)
        win.tick()
        assert parts.obs.connected is False
        assert "reconectando" in win.obs_label.text()
    finally:
        win.close()


def test_eventos_de_otros_hilos_entran_por_senal(qapp, appdata):
    parts, win = _armar(_obs_cerrado())
    try:
        hilos = [threading.Thread(target=parts.events.post, args=(f"evento {i}",)) for i in range(60)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        qapp.processEvents()
        lineas = win.event_lines()
        assert len(lineas) == 50                         # solo los últimos 50
        assert all(len(l.split("  ", 1)[0]) == 8 for l in lineas)   # HH:MM:SS
    finally:
        win.close()


def test_bando_y_modo_se_guardan(qapp, appdata):
    parts, win = _armar(_obs_cerrado())
    try:
        win.dire_button.click()
        win.hide_button.click()
        win.wait_background(5)
        st = parts.storage.load_state(1)
        assert (st.radiant_team, st.mode) == (2, "hidden")
        assert parts.engine.status().radiant_team == 2
        assert parts.engine.status().mode == "hidden"
        assert parts.local_input._worker is None         # con "Ocultar todo" no se escucha
        win.tick()
        assert win.team1_label.text() == "Equipo 1 (Dire)"
        assert win.team2_label.text() == "Equipo 2 (Radiant)"
        win.auto_button.click()
        assert parts.local_input._worker is not None
    finally:
        win.close()
    assert parts.local_input._worker is None


def test_ajustes_nuevos_crean_otro_obs(qapp, appdata):
    parts, win = _armar(_obs_cerrado())
    try:
        viejo = parts.obs
        nuevo = Settings(obs_port=4460, obs_password="otra", dota_dir=None, default_radiant_team=2)
        win.apply_settings(nuevo)
        assert win.obs is not viejo
        assert parts.sink.obs is win.obs                 # el motor ya manda al OBS nuevo
        assert (win.obs.port, win.obs.password) == (4460, "otra")
        assert parts.storage.load_settings() == nuevo
        # mismo puerto y contraseña: no se reemplaza
        actual = win.obs
        win.apply_settings(Settings(4460, "otra", None, 1))
        assert win.obs is actual
    finally:
        win.close()


def test_recarga_teclas_si_cambia_el_archivo(qapp, appdata, tmp_path):
    steam, keys = _steam_con_teclas(tmp_path)
    parts, win = _armar(_obs_cerrado(), steam=steam)
    try:
        antes = dict(parts.engine._player_keys)
        assert antes == parse_player_keys(keys.read_text(encoding="utf-8"))
        texto = ('"KeyBindings"\n{\n\t"Keys"\n\t{\n\t\t"SpectatorCameraFocusPlayer1"\n'
                 '\t\t{\n\t\t\t"Key"\t\t"F5"\n\t\t}\n\t}\n}\n')
        keys.write_text(texto, encoding="utf-8")
        st = keys.stat()
        os.utime(keys, (st.st_atime, st.st_mtime + 10))
        win.tick()
        win.wait_background(5)
        qapp.processEvents()
        assert parts.engine._player_keys == parse_player_keys(texto) == {0x74: "r1"}
        assert any("Teclas de Dota recargadas" in l for l in win.event_lines())
    finally:
        win.close()


def test_puerto_ocupado_avisa_y_no_arranca(qapp, monkeypatch):
    ocupado = socket.socket()
    ocupado.bind(("127.0.0.1", 0))
    ocupado.listen()
    avisos = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: avisos.append(a))
    try:
        gsi = GsiServer(engine=None, port=ocupado.getsockname()[1])
        assert app.start_gsi_or_warn(gsi) is False
        assert "en uso por otra copia de la app, la consola u otro programa" in avisos[0][2]
        assert str(ocupado.getsockname()[1]) in avisos[0][2]
    finally:
        ocupado.close()


def test_dialogo_de_ajustes(qapp, monkeypatch):
    s = Settings(obs_port=4455, obs_password="secreto", dota_dir=None, default_radiant_team=1)
    pm = PortraitModel({"r1": [-0.4, 0.03, 3]})
    dlg = SettingsDialog(s, pm)
    assert dlg.password_edit.text() == "secreto"
    dlg.password_edit.setText("nueva")
    dlg.port_spin.setValue(4456)
    dlg.team_combo.setCurrentIndex(1)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    dlg.forget_button.click()
    assert pm.as_dict() == {} and dlg.portraits_forgotten
    assert dlg.values() == Settings(4456, "nueva", None, 2, language="es")   # el idioma en uso
    assert s.obs_password == "secreto"                   # no toca el original
    dlg.close()


def _post(port, payload):
    import json
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{port}/", data=json.dumps(payload).encode(),
                                 method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status


def test_post_de_gsi_enciende_camara_y_se_ve_en_la_ventana(qapp, appdata):
    from tests.conftest import fake_camaraman, gsi_payload
    fake = fake_camaraman()
    parts, win = _armar(fake)
    try:
        win.tick()
        _esperar(qapp, win)                              # conecta a OBS (falso)
        assert _post(parts.gsi.server_port, gsi_payload("r3")) == 200
        assert fake.is_enabled("1 Offlaner", "Juego") is True and fake.is_enabled("Borde") is True
        win.tick()
        qapp.processEvents()
        assert "1 Offlaner" in win.on_air_label.text()
        assert "datos llegando" in win.dota_label.text()
        assert "en juego" in win.game_label.text()
        assert any("→ 1 Offlaner" in l for l in win.event_lines())
        # "Ocultar todo" apaga la cámara y los acompañantes
        win.hide_button.click()
        win.wait_background(5)
        assert fake.is_enabled("1 Offlaner", "Juego") is False and fake.is_enabled("Borde") is False
    finally:
        win.close()


def test_arreglo_pide_confirmacion_y_avisa_si_se_niega(qapp, appdata, tmp_path, monkeypatch):
    parts, win = _armar(_obs_cerrado())
    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    parts.settings.dota_dir = str(dota)
    avisos = []
    respuesta = [QMessageBox.StandardButton.No]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: respuesta[0])
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(("info", a[2])))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(("warn", a[2])))
    try:
        win.run_checks()
        _esperar(qapp, win)
        gsi_row = next(r for r in win.check_results if r.id == "gsi_cfg")
        assert gsi_row.status == "error" and gsi_row.fix_label == "Arreglar"
        win._confirm_fix(gsi_row)                        # el usuario dice que no
        _esperar(qapp, win)
        assert not paths.gsi_cfg_path(dota).exists() and avisos == []
        respuesta[0] = QMessageBox.StandardButton.Yes
        win._confirm_fix(gsi_row)
        _esperar(qapp, win)
        assert paths.gsi_cfg_path(dota).read_text(encoding="utf-8") == config.GSI_CFG_TEXT
        assert avisos[0][0] == "info"
        assert next(r for r in win.check_results if r.id == "gsi_cfg").status == "ok"
        # un arreglo que no se puede hacer (FixRefused) se muestra como aviso
        parts.settings.dota_dir = None                   # sin Steam: no hay carpeta de Dota
        win._confirm_fix(gsi_row)
        _esperar(qapp, win)
        assert avisos[-1] == ("warn", "Primero hay que elegir la carpeta de Dota")
    finally:
        win.close()


def test_sin_contrasena_y_obs_la_pide_abre_ajustes_una_vez(qapp, appdata, monkeypatch):
    from obsws_python.error import OBSSDKError
    fake = FakeObsClient()
    fake.connect_error = OBSSDKError("authentication enabled but no password provided")
    parts, win = _armar(fake)
    abiertos = []
    monkeypatch.setattr(win, "open_settings", lambda intro=None: abiertos.append(intro))
    try:
        for _ in range(2):
            win._last_obs_try = float("-inf")
            win.tick()
            _esperar(qapp, win)
        assert "falta la contraseña" in win.obs_label.text()
        assert len(abiertos) == 1 and "contraseña de OBS" in abiertos[0]
    finally:
        win.close()


def test_buscar_dota_en_ajustes_rechaza_una_carpeta_que_no_es_dota(qapp, tmp_path, monkeypatch):
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a))
    cualquiera = tmp_path / "Documentos"
    cualquiera.mkdir()
    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    dlg = SettingsDialog(Settings(), PortraitModel({}))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                        lambda *a, **k: str(cualquiera))
    dlg._browse_dota()
    assert dlg.values().dota_dir is None and len(avisos) == 1
    assert "falta game" in avisos[0][2]
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                        lambda *a, **k: str(dota))
    dlg._browse_dota()
    assert dlg.values().dota_dir == str(dota) and len(avisos) == 1
    dlg.close()


def test_buscar_dota_en_la_ventana_rechaza_una_carpeta_que_no_es_dota(qapp, appdata, tmp_path,
                                                                     monkeypatch):
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a))
    cualquiera = tmp_path / "Documentos"
    cualquiera.mkdir()
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                        lambda *a, **k: str(cualquiera))
    parts, win = _armar(FakeObsClient())
    try:
        win._browse_dota()
        assert parts.settings.dota_dir is None and win._settings.dota_dir is None
        assert Storage(paths.app_data_dir()).load_settings().dota_dir is None
        assert len(avisos) == 1 and "falta game" in avisos[0][2]
    finally:
        win.close()


# ---------------------------------------------------------------------------
# Idioma
# ---------------------------------------------------------------------------
from overpower_cams import i18n  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402


def test_ventana_en_ingles(qapp, appdata):
    i18n.set_language("en")                      # el fixture de conftest lo vuelve a "es"
    parts, win = _armar(_obs_cerrado())
    try:
        assert win.windowTitle() == "OverPower · Dota Player Cams" == config.app_name()
        assert win.settings_button.text() == "⚙ Settings"
        assert win.recheck_button.text() == "↻ Re-check everything"
        assert (win.auto_button.text(), win.hide_button.text()) == ("Automatic", "Hide all")
        labels = {lbl.text() for lbl in win.findChildren(QLabel)}
        assert {"CHECKS", "LIVE", "RECENT EVENTS", "Team 1 side", "Status", "Mode"} <= labels
        assert win.team1_label.text() == "Team 1 (Radiant)"
        assert "On air:" in win.on_air_label.text()
        win.tick()
        _esperar(qapp, win)
        win.tick()
        assert "reconnecting" in win.obs_label.text() and "no data" in win.dota_label.text()
        win.run_checks()
        _esperar(qapp, win)
        obs_row = next(r for r in win.check_results if r.id == "obs")
        assert obs_row.title == "OBS and WebSocket"
        assert obs_row.detail.startswith("Couldn't connect to OBS at 127.0.0.1:")
        assert "Tools → WebSocket Server Settings" in obs_row.instructions
    finally:
        win.close()


def test_dialogo_de_ajustes_en_ingles_y_combo_de_idioma(qapp):
    i18n.set_language("en")
    dlg = SettingsDialog(Settings(language=None), PortraitModel({}))
    try:
        assert dlg.windowTitle() == "Settings · OverPower · Dota Player Cams"
        assert dlg.show_button.text() == "Show"
        labels = {lbl.text() for lbl in dlg.findChildren(QLabel)}
        assert {"OBS port", "Dota folder", "Language / Idioma"} <= labels
        combo = dlg.language_combo
        assert [combo.itemText(i) for i in range(combo.count())] == ["Español", "English"]
        assert combo.currentData() == "en"           # sin idioma guardado: el que está en uso
        combo.setCurrentIndex(0)
        assert dlg.values().language == "es"
    finally:
        dlg.close()


def test_combo_de_idioma_muestra_el_guardado(qapp):
    dlg = SettingsDialog(Settings(language="en"), PortraitModel({}))
    try:
        assert dlg.language_combo.currentData() == "en"
    finally:
        dlg.close()


def _con_idioma(parts, code):
    s = parts.settings
    return Settings(s.obs_port, s.obs_password, s.dota_dir, s.default_radiant_team, language=code)


def test_cambiar_idioma_guarda_y_ofrece_reiniciar(qapp, appdata, monkeypatch):
    parts, win = _armar(_obs_cerrado())
    preguntas, relanzados = [], []
    monkeypatch.setattr(win, "ask_restart", lambda code: preguntas.append(code) or False)
    win._relaunch = lambda: relanzados.append(True)
    try:
        win.apply_settings(_con_idioma(parts, "es"))   # mismo idioma: no pregunta
        assert preguntas == [] and parts.storage.load_settings().language == "es"
        win.apply_settings(_con_idioma(parts, "en"))   # "Más tarde"
        assert preguntas == ["en"] and relanzados == []
        assert parts.storage.load_settings().language == "en"
        assert i18n.get_language() == "es"            # el idioma no cambia hasta reiniciar
        assert not win._closed
    finally:
        win.close()


def test_reiniciar_ahora_cierra_y_vuelve_a_abrir(qapp, appdata, monkeypatch):
    parts, win = _armar(_obs_cerrado())
    orden = []
    monkeypatch.setattr(win, "ask_restart", lambda code: True)
    win._relaunch = lambda: orden.append(("relanzar", parts.gsi._httpd is None))
    win.apply_settings(_con_idioma(parts, "en"))
    assert orden == [("relanzar", True)]               # el puerto GSI ya se liberó al relanzar
    assert win._closed
    assert parts.storage.load_settings().language == "en"


def test_aviso_de_reinicio_sale_en_el_idioma_nuevo(qapp, appdata, monkeypatch):
    parts, win = _armar(_obs_cerrado())
    vistos = []

    def exec_(box):
        vistos.append((box.text(), sorted(b.text() for b in box.buttons())))
        return 0
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    try:
        assert win.ask_restart("en") is False          # se cerró sin elegir
        assert win.ask_restart("es") is False
    finally:
        win.close()
    assert vistos[0] == ("The new language applies after restarting the app.", ["Later", "Restart now"])
    assert vistos[1] == ("El idioma nuevo se aplica al reiniciar la app.",
                         ["Más tarde", "Reiniciar ahora"])


def test_apply_language_usa_el_guardado_o_el_de_windows(monkeypatch):
    monkeypatch.setattr(app, "detect_default", lambda: "en")
    s = Settings()
    assert app.apply_language(s) == "en" and i18n.get_language() == "en"
    assert s.language is None                          # el detectado no se guarda solo
    assert app.apply_language(Settings(language="es")) == "es" and i18n.get_language() == "es"


def test_comando_para_reabrir(monkeypatch):
    import sys
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.relaunch_command() == [sys.executable, "-m", "overpower_cams.app"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths.relaunch_command() == [sys.executable]
