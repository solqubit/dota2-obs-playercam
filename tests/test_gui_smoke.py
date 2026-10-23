"""Pruebas de humo de la ventana: sin OBS real, sin Steam real, sin %APPDATA% real y
con el servidor GSI en un puerto libre (port=0)."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # antes de crear QApplication

import shutil  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtWidgets import QLabel, QMessageBox  # noqa: E402

from overpower_cams import app, config, i18n, paths  # noqa: E402
from overpower_cams.dota_keys import parse_player_keys  # noqa: E402
from overpower_cams.gsi_server import GsiServer  # noqa: E402
from overpower_cams.gui.page_settings import SettingsPage  # noqa: E402
from overpower_cams.players import PlayerConfig, TeamsConfig  # noqa: E402
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
        assert win.obs_detail.text() == "127.0.0.1:4455"
        assert parts.obs.connected is False
        assert "sin datos" in win.dota_label.text() and win.dota_detail.text() == "nunca"
        assert "fuera de partida" in win.game_label.text()
        assert win.on_air_label.text() == "Al aire: ninguna cámara"
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
        win.side_selector.buttons[2].click()
        win.hide_button.click()
        win.wait_background(5)
        st = parts.storage.load_state(1)
        assert (st.radiant_team, st.mode) == (2, "hidden")
        assert parts.engine.status().radiant_team == 2
        assert parts.engine.status().mode == "hidden"
        assert parts.local_input._worker is None         # con "Ocultar todo" no se escucha
        win.tick()
        assert win.side_selector.buttons[2].isChecked()
        assert win.on_air_label.text() == "Al aire: nada (Ocultar todo)"
        win.auto_button.click()
        assert parts.local_input._worker is not None
    finally:
        win.close()
    assert parts.local_input._worker is None


def test_selector_de_bando_usa_los_nombres_de_equipo(qapp, appdata):
    Storage(paths.app_data_dir()).save_teams(TeamsConfig("Team Liquid", ""))
    parts, win = _armar(_obs_cerrado())
    try:
        textos = [b.text() for b in win.side_selector.buttons.values()]
        assert textos == ["Team Liquid", "Equipo 2"]       # vacío: "Equipo 2"
        parts.storage.save_teams(TeamsConfig("Team Liquid", "Gaimin Gladiators"))
        win.tick()                                       # se actualiza si cambian
        assert win.side_selector.buttons[2].text() == "Gaimin Gladiators"
        win.side_selector.buttons[2].click()
        qapp.processEvents()
        assert any("Radiant es: Gaimin Gladiators" in l for l in win.event_lines())
    finally:
        win.close()


def test_menu_lateral_recorre_las_5_paginas(qapp, appdata):
    parts, win = _armar(_obs_cerrado())
    try:
        assert list(win.nav_buttons) == ["players", "checks", "scene", "events", "settings"]
        assert win.current_page() == "players"
        for key, button in win.nav_buttons.items():
            button.click()
            assert win.current_page() == key and button.isChecked()
            assert win.stack.currentWidget() is win.pages[key]
        assert win.pages["settings"] is win.settings_page
        # Task 11 cambia las páginas de relleno por las reales
        nueva = QLabel("nueva")
        win.set_page("scene", nueva)
        assert win.pages["scene"] is nueva and win.stack.indexOf(nueva) == 2
        win.show_page("scene")
        assert win.stack.currentWidget() is nueva
    finally:
        win.close()


def test_insignia_de_revision_cuenta_pendientes(qapp, appdata):
    parts, win = _armar(_obs_cerrado())
    try:
        win.run_checks()
        _esperar(qapp, win)
        pendientes = sum(r.status in ("warn", "error") for r in win.check_results)
        assert pendientes > 0
        assert win.checks_badge.text() == str(pendientes) and not win.checks_badge.isHidden()
        assert win.checks_badge.height() == 18 and win.checks_badge.width() >= 18   # pastilla redonda
        win._render_checks([])
        assert win.checks_badge.isHidden()
    finally:
        win.close()


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
        # otra dirección u otra escena principal: sí
        win.apply_settings(Settings(4460, "otra", None, 1, main_scene="Otra", obs_host="10.0.0.5"))
        assert win.obs is not actual and parts.sink.obs is win.obs
        assert (win.obs.host, win.obs.main_scene) == ("10.0.0.5", "Otra")
        win.tick()
        assert win.obs_detail.text() == "10.0.0.5:4460"
        assert not any("otra" in l for l in win.event_lines())   # nunca la contraseña
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


def test_pagina_de_ajustes(qapp, monkeypatch):
    s = Settings(obs_port=4455, obs_password="secreto", dota_dir=None, default_radiant_team=1)
    pm = PortraitModel({"r1": [-0.4, 0.03, 3]})
    olvidados = []
    page = SettingsPage(s, pm, teams=TeamsConfig("Liquid", "GG"),
                        on_forget_portraits=lambda: olvidados.append(True))
    assert page.password_edit.text() == "secreto"
    assert page.main_scene_edit.text() == "Juego" and page.host_edit.text() == "127.0.0.1"
    assert [page.team_combo.itemText(i) for i in range(2)] == ["Liquid", "GG"]
    page.password_edit.setText("nueva")
    page.port_edit.setValue(4456)
    page.team_combo.setCurrentIndex(1)
    page.mode_combo.setCurrentIndex(page.mode_combo.findData("hidden"))
    page.main_scene_edit.setText("  Partida ")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    page.forget_button.click()
    assert pm.as_dict() == {} and olvidados == [True]
    assert page.values() == Settings(4456, "nueva", None, 2, language="es", main_scene="Partida",
                                     default_mode="hidden")
    assert s.obs_password == "secreto"                   # no toca el original
    page.main_scene_edit.setText(" ")
    page.host_edit.setText("")
    assert (page.values().main_scene, page.values().obs_host) == ("Juego", "127.0.0.1")
    page.revert_button.click()                           # descarta lo no guardado
    assert page.values() == replace(s, language="es")
    page.close()


def test_pagina_de_ajustes_no_pisa_la_carpeta_elegida_en_revision(qapp, tmp_path, monkeypatch):
    s = Settings()
    page = SettingsPage(s, PortraitModel({}))
    page.port_edit.setValue(4460)                        # cambios sin guardar
    assert page.is_dirty()
    s.dota_dir = str(tmp_path / "elegida en Revisión")   # la ventana la cambia desde Revisión
    assert page.values().dota_dir == s.dota_dir
    page.refresh_dota()
    assert page.dota_label.text() == s.dota_dir
    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                        lambda *a, **k: str(dota))
    page._browse_dota()                                  # elegida en la página: esa manda
    assert page.values().dota_dir == str(dota)
    page.close()


def test_carpeta_de_revision_sobrevive_a_ajustes_sin_guardar(qapp, appdata, tmp_path, monkeypatch):
    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                        lambda *a, **k: str(dota))
    parts, win = _armar(_obs_cerrado())
    try:
        win.show_page("settings")
        win.settings_page.port_edit.setValue(4460)      # sin guardar
        win.show_page("checks")
        win._browse_dota()                               # elegida desde Revisión
        win.show_page("settings")
        assert win.settings_page.dota_label.text() == str(dota)
        win.settings_page.save_button.click()
        assert parts.storage.load_settings().dota_dir == str(dota)
        assert parts.storage.load_settings().obs_port == 4460
    finally:
        win.close()


def test_ajustes_guarda_main_scene_desde_la_pagina(qapp, appdata):
    parts, win = _armar(_obs_cerrado())
    try:
        win.show_page("settings")
        win.settings_page.main_scene_edit.setText("Partida")
        win.settings_page.save_button.click()
        assert parts.storage.load_settings().main_scene == "Partida"
        assert win.obs.main_scene == "Partida" and parts.sink.obs is win.obs
    finally:
        win.close()


def test_abrir_ajustes_con_explicacion(qapp, appdata):
    parts, win = _armar(_obs_cerrado())
    try:
        win.open_settings(intro="Falta algo")
        assert win.current_page() == "settings"
        assert win.settings_page.intro_label.text() == "Falta algo"
        assert not win.settings_page.intro_label.isHidden()
        win.open_settings()
        assert win.settings_page.intro_label.isHidden()
    finally:
        win.close()


def test_olvidar_retratos_desde_ajustes_los_guarda(qapp, appdata, monkeypatch):
    Storage(paths.app_data_dir()).save_portraits({"r1": [-0.4, 0.03, 3]})
    parts, win = _armar(_obs_cerrado())
    assert parts.portraits.as_dict() != {}
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    try:
        win.show_page("settings")
        win.settings_page.forget_button.click()
        qapp.processEvents()
        assert parts.storage.load_portraits(None) == {}
        assert any("Retratos olvidados" in l for l in win.event_lines())
    finally:
        win.close()


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
    storage = Storage(paths.app_data_dir())
    jugadores = storage.load_players()
    jugadores["1 Offlaner"] = PlayerConfig(name="Ceb", camera_url="https://vdo.ninja/?view=x")
    storage.save_players(jugadores)
    parts, win = _armar(fake)
    try:
        win.tick()
        _esperar(qapp, win)                              # conecta a OBS (falso)
        payload = gsi_payload("r3")
        payload["map"]["clock_time"] = 754
        assert _post(parts.gsi.server_port, payload) == 200
        assert fake.is_enabled("1 Offlaner", "Juego") is True and fake.is_enabled("Borde") is True
        win.tick()
        qapp.processEvents()
        assert win.on_air_label.text() == "Al aire: Ceb · 1 Offlaner · Test2 · 4 habilidades"
        assert "datos llegando" in win.dota_label.text() and win.dota_detail.text() == "hace 0 s"
        assert "en juego" in win.game_label.text() and win.game_detail.text() == "12:34"
        fin = gsi_payload(None, state="DOTA_GAMERULES_STATE_POST_GAME")
        fin["map"]["clock_time"] = 2400
        assert _post(parts.gsi.server_port, fin) == 200
        win.tick()
        assert "fuera de partida" in win.game_label.text() and win.game_detail.text() == "—"
        assert _post(parts.gsi.server_port, payload) == 200
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
    page = SettingsPage(Settings(), PortraitModel({}))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                        lambda *a, **k: str(cualquiera))
    page._browse_dota()
    assert page.values().dota_dir is None and len(avisos) == 1
    assert "falta game" in avisos[0][2]
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                        lambda *a, **k: str(dota))
    page._browse_dota()
    assert page.values().dota_dir == str(dota) and len(avisos) == 1
    page.close()


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

def test_ventana_en_ingles(qapp, appdata):
    i18n.set_language("en")                      # el fixture de conftest lo vuelve a "es"
    parts, win = _armar(_obs_cerrado())
    try:
        assert win.windowTitle() == "OverPower · Dota Player Cams" == config.app_name()
        assert [b.text() for b in win.nav_buttons.values()] == [
            "Players", "Checks", "OBS scene", "Events", "Settings"]
        assert win.recheck_button.text() == "↻ Re-check everything"
        assert (win.auto_button.text(), win.hide_button.text()) == ("Automatic", "Hide all")
        assert [b.text() for b in win.side_selector.buttons.values()] == ["Team 1", "Team 2"]
        labels = {lbl.text() for lbl in win.findChildren(QLabel)}
        assert {"Radiant is", "Mode", "Checks", "Events", "Settings", "OBS scene"} <= labels
        assert win.on_air_label.text() == "On air: no camera"
        win.tick()
        _esperar(qapp, win)
        win.tick()
        assert "reconnecting" in win.obs_label.text() and "no data" in win.dota_label.text()
        assert win.dota_detail.text() == "never"
        win.run_checks()
        _esperar(qapp, win)
        obs_row = next(r for r in win.check_results if r.id == "obs")
        assert obs_row.title == "OBS and WebSocket"
        assert obs_row.detail.startswith("Couldn't connect to OBS at 127.0.0.1:")
        assert "Tools → WebSocket Server Settings" in obs_row.instructions
    finally:
        win.close()


def test_pagina_de_ajustes_en_ingles_y_combo_de_idioma(qapp):
    i18n.set_language("en")
    page = SettingsPage(Settings(language=None), PortraitModel({}))
    try:
        assert page.show_button.text() == "Show"
        labels = {lbl.text() for lbl in page.findChildren(QLabel)}
        assert {"OBS port", "Dota folder", "Language / Idioma", "Main scene", "OBS address",
                "Radiant at startup", "Initial mode"} <= labels
        assert [page.team_combo.itemText(i) for i in range(2)] == ["Team 1", "Team 2"]
        combo = page.language_combo
        assert [combo.itemText(i) for i in range(combo.count())] == ["Español", "English"]
        assert combo.currentData() == "en"           # sin idioma guardado: el que está en uso
        combo.setCurrentIndex(0)
        assert page.values().language == "es"
    finally:
        page.close()


def test_combo_de_idioma_muestra_el_guardado(qapp):
    page = SettingsPage(Settings(language="en"), PortraitModel({}))
    try:
        assert page.language_combo.currentData() == "en"
    finally:
        page.close()


def _con_idioma(parts, code):
    return replace(parts.settings, language=code)


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


def test_reiniciar_ahora_desde_la_pagina_cierra_y_vuelve_a_abrir(qapp, appdata, monkeypatch):
    parts, win = _armar(_obs_cerrado())
    orden = []
    monkeypatch.setattr(win, "ask_restart", lambda code: True)
    win._relaunch = lambda: orden.append(("relanzar", parts.gsi._httpd is None))
    win.show_page("settings")
    combo = win.settings_page.language_combo
    combo.setCurrentIndex(combo.findData("en"))
    win.settings_page.save_button.click()
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


def test_estado_inicial_usa_el_modo_de_ajustes(qapp, appdata):
    Storage(paths.app_data_dir()).save_settings(Settings(default_mode="hidden"))
    parts, win = _armar(_obs_cerrado())
    try:
        assert parts.state.mode == "hidden" and parts.engine.status().mode == "hidden"
        assert win.hide_button.isChecked()
    finally:
        win.close()


def test_comando_para_reabrir(monkeypatch):
    import sys
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.relaunch_command() == [sys.executable, "-m", "overpower_cams.app"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths.relaunch_command() == [sys.executable]
