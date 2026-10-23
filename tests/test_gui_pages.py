"""Páginas Jugadores y Escena OBS: cada edición se guarda y llega a OBS (falso), las habilidades y
la fila al aire salen del motor, Probar activa el filtro y Crear escenas copia la plantilla."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # antes de crear QApplication

from dataclasses import replace  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402

from overpower_cams import app, i18n, paths, scene_builder  # noqa: E402
from overpower_cams.config import PLAYER_SCENES, source_name  # noqa: E402
from overpower_cams.players import PlayerConfig, TeamsConfig  # noqa: E402
from overpower_cams.scene_builder import SceneBuildError  # noqa: E402
from overpower_cams.storage import Storage  # noqa: E402
from tests.conftest import FakeObsClient, filtros_camaraman, layout_camaraman  # noqa: E402


class FakeListener:
    def __init__(self, **callbacks):
        pass

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


def _inputs(borde_file=""):
    out = {"Borde": {"file": borde_file}}
    for s in PLAYER_SCENES:
        out[source_name("Camara", s)] = {"url": ""}
        out[source_name("Foto", s)] = {"url": ""}
        out[source_name("Fondo", s)] = {"file": ""}
        out[source_name("Nombre", s)] = {"text": s}
    return out


def _fake(sin_escenas=(), omitir_filtros=(), borde_file=""):
    """Colección Camaraman; las escenas de `sin_escenas` no existen en OBS (ni en `Juego`)."""
    scenes = layout_camaraman(skip_scenes=sin_escenas)
    inputs = _inputs(borde_file)
    for s in sin_escenas:
        del scenes[s]
        for k in ("Camara", "Foto", "Fondo", "Nombre"):
            inputs.pop(source_name(k, s))
    return FakeObsClient(scenes=scenes, scene="Juego", inputs=inputs,
                         filters=filtros_camaraman(omitir_filtros))


def _armar(fake):
    storage = Storage(paths.app_data_dir())
    parts = app.build_app(storage, steam=None, obs_client_factory=fake.factory, gsi_port=0,
                          keyboard_listener=FakeListener, mouse_listener=FakeListener,
                          get_rect=lambda: None, legacy_portraits=None)
    win = app.create_window(parts, is_running=lambda exe: False)
    return parts, win


def _esperar(qapp, win):
    win.wait_background(5)
    qapp.processEvents()


def _conectar(qapp, win):
    win.tick()
    _esperar(qapp, win)
    win.tick()
    _esperar(qapp, win)


def _editar(edit, texto):
    edit.setText(texto)
    edit.editingFinished.emit()


# ---------------------------------------------------------------- Jugadores

def test_editar_nombre_guarda_y_cambia_el_texto_en_obs(qapp, appdata):
    fake = _fake()
    parts, win = _armar(fake)
    try:
        _conectar(qapp, win)
        assert parts.obs.connected
        page = win.pages["players"]
        assert page is win.players_page
        assert list(page.rows) == PLAYER_SCENES
        _editar(page.rows["1 Mid laner"].name_edit, "SumaiL")
        _esperar(qapp, win)
        assert parts.storage.load_players()["1 Mid laner"].name == "SumaiL"
        assert fake.inputs["Nombre · 1 Mid laner"]["text"] == "SumaiL"
        # sin cambios no se vuelve a guardar ni a mandar
        fake.inputs["Nombre · 1 Mid laner"]["text"] = "otro"
        page.rows["1 Mid laner"].name_edit.editingFinished.emit()
        _esperar(qapp, win)
        assert fake.inputs["Nombre · 1 Mid laner"]["text"] == "otro"
    finally:
        win.close()


def test_editar_links_cambia_la_url_y_reaplica_camara_o_foto(qapp, appdata):
    fake = _fake()
    parts, win = _armar(fake)
    try:
        _conectar(qapp, win)
        row = win.players_page.rows["1 Mid laner"]
        row.use_selector.buttons["photo"].click()            # quiere Foto, pero no hay links
        _editar(row.camera_edit, "https://vdo.ninja/?view=cam")
        _esperar(qapp, win)
        assert fake.inputs["Camara · 1 Mid laner"]["url"] == "https://vdo.ninja/?view=cam"
        parts.obs.apply("1 Mid laner", "test")              # Foto elegida vacía: no usar cámara
        assert fake.is_enabled("Camara · 1 Mid laner", "1 Mid laner") is False
        assert fake.is_enabled("Foto · 1 Mid laner", "1 Mid laner") is False
        _editar(row.photo_edit, "https://vdo.ninja/?view=foto")   # aparece la foto elegida
        _esperar(qapp, win)
        p = parts.storage.load_players()["1 Mid laner"]
        assert (p.camera_url, p.photo_url, p.use) == ("https://vdo.ninja/?view=cam",
                                                      "https://vdo.ninja/?view=foto", "photo")
        assert fake.inputs["Foto · 1 Mid laner"]["url"] == "https://vdo.ninja/?view=foto"
        assert fake.is_enabled("Foto · 1 Mid laner", "1 Mid laner") is True
        assert fake.is_enabled("Camara · 1 Mid laner", "1 Mid laner") is False
    finally:
        win.close()


def test_cambiar_a_foto_guarda_y_cambia_en_obs_si_esta_al_aire(qapp, appdata):
    storage = Storage(paths.app_data_dir())
    jugadores = storage.load_players()
    jugadores["1 Offlaner"] = PlayerConfig("Ceb", "https://vdo.ninja/?view=c", "https://vdo.ninja/?view=f")
    storage.save_players(jugadores)
    fake = _fake()
    parts, win = _armar(fake)
    try:
        _conectar(qapp, win)
        parts.obs.apply("1 Offlaner", "test")
        assert fake.is_enabled("Camara · 1 Offlaner", "1 Offlaner") is True
        row = win.players_page.rows["1 Offlaner"]
        assert row.name_edit.text() == "Ceb" and row.use_selector.buttons["camera"].isChecked()
        row.use_selector.buttons["photo"].click()
        _esperar(qapp, win)
        assert parts.storage.load_players()["1 Offlaner"].use == "photo"
        assert fake.is_enabled("Foto · 1 Offlaner", "1 Offlaner") is True
        assert fake.is_enabled("Camara · 1 Offlaner", "1 Offlaner") is False
    finally:
        win.close()


def test_sin_obs_guarda_avisa_y_lo_aplica_al_reconectar(qapp, appdata):
    fake = _fake()
    fake.connect_error = ConnectionRefusedError("OBS cerrado")
    parts, win = _armar(fake)
    try:
        _conectar(qapp, win)
        assert not parts.obs.connected
        page = win.players_page
        _editar(page.rows["2 Hard support"].name_edit, "Seleri")
        _editar(page.rows["2 Hard support"].camera_edit, "https://vdo.ninja/?view=s")
        _esperar(qapp, win)
        assert parts.storage.load_players()["2 Hard support"].name == "Seleri"
        assert any("al reconectar" in line for line in win.event_lines())
        fake.connect_error = None                            # OBS abre
        win._last_obs_try = float("-inf")
        _conectar(qapp, win)
        assert parts.obs.connected
        assert fake.inputs["Nombre · 2 Hard support"]["text"] == "Seleri"
        assert fake.inputs["Camara · 2 Hard support"]["url"] == "https://vdo.ninja/?view=s"
        # los que nunca se tocaron y están vacíos no pisan lo que tiene OBS
        assert fake.inputs["Nombre · 1 Hard carry"]["text"] == "1 Hard carry"
    finally:
        win.close()


def test_habilidades_y_fila_al_aire_salen_del_motor(qapp, appdata):
    parts, win = _armar(_fake())
    try:
        page = win.players_page
        st = replace(parts.engine.status(), camera="1 Mid laner",
                     abilities={"1 Mid laner": 6, "2 Offlaner": 5})
        page.refresh_live(st)
        rows = page.rows
        assert rows["1 Mid laner"].abilities_label.text() == "6"
        assert rows["2 Offlaner"].abilities_label.text() == "5"
        assert rows["1 Hard carry"].abilities_label.text() == "—"
        assert rows["1 Mid laner"].property("onair") is True
        assert "●" in rows["1 Mid laner"].role_label.text()
        assert rows["1 Hard carry"].property("onair") is False
        assert "●" not in rows["1 Hard carry"].role_label.text()
        page.refresh_live(replace(st, camera=None))
        assert rows["1 Mid laner"].property("onair") is False
    finally:
        win.close()


def test_nombre_de_equipo_actualiza_barra_ajustes_y_bando(qapp, appdata):
    parts, win = _armar(_fake())
    try:
        page = win.players_page
        assert page.side_hints[1].text() == "→ Radiant" and page.side_hints[2].text() == "→ Dire"
        _editar(page.team_edits[1], "Team Liquid")
        assert parts.storage.load_teams() == TeamsConfig("Team Liquid", "")
        assert win.side_selector.buttons[1].text() == "Team Liquid"
        assert win.live_bar.radiant_label.text() == "Radiant: Team Liquid"
        assert win.live_bar.dire_label.text() == "Dire: Equipo 2"
        assert win.settings_page.team_combo.itemText(0) == "Team Liquid"
        win.side_selector.buttons[2].click()
        qapp.processEvents()
        assert page.side_hints[1].text() == "→ Dire" and page.side_hints[2].text() == "→ Radiant"
        assert win.live_bar.radiant_label.text() == "Radiant: Equipo 2"
        assert win.live_bar.dire_label.text() == "Dire: Team Liquid"
    finally:
        win.close()


# ---------------------------------------------------------------- Escena OBS

def test_probar_activa_el_filtro_y_se_desactiva_sin_obs_o_sin_filtro(qapp, appdata):
    fake = _fake(omitir_filtros=("H 6 habilidades",))
    parts, win = _armar(fake)
    try:
        page = win.pages["scene"]
        assert page is win.scene_page
        assert not any(b.isEnabled() for b in page.test_buttons.values())   # sin conectar
        _conectar(qapp, win)
        win.show_page("scene")
        _esperar(qapp, win)
        win.tick()
        assert page.test_buttons[5].isEnabled() and not page.test_buttons[6].isEnabled()
        assert "456" in page.filter_details[5].text() and "1819" in page.filter_details[5].text()
        page.test_buttons[5].click()
        _esperar(qapp, win)
        assert ("filter_enabled", "H 5 habilidades", True) in fake.ops
        assert fake.filter_settings("H 5 habilidades")["source"] == "1 Hard carry"
    finally:
        win.close()


def test_crear_escenas_pide_confirmacion_y_copia_la_plantilla(qapp, appdata, monkeypatch):
    fake = _fake(sin_escenas=("2 Offlaner", "2 Hard support"))
    llamadas, preguntas, avisos = [], [], []
    original = scene_builder.clone_player_scenes

    def espia(client, main, **kw):
        llamadas.append(kw.get("targets"))
        return original(client, main, **kw)
    monkeypatch.setattr(scene_builder, "clone_player_scenes", espia)
    respuesta = [QMessageBox.StandardButton.No]

    def pregunta(*a, **k):
        preguntas.append(a[2])
        return respuesta[0]
    monkeypatch.setattr(QMessageBox, "question", pregunta)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(("info", a[2])))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(("warn", a[2])))
    parts, win = _armar(fake)
    try:
        _conectar(qapp, win)
        page = win.scene_page
        assert page.create_button.isEnabled()
        page.create_button.click()                           # dice que no
        _esperar(qapp, win)
        assert "2 Offlaner" in preguntas[0] and "2 Hard support" in preguntas[0]
        assert llamadas == [] and "2 Offlaner" not in fake.scenes
        respuesta[0] = QMessageBox.StandardButton.Yes
        page.create_button.click()
        _esperar(qapp, win)
        assert llamadas == [["2 Offlaner", "2 Hard support"]]
        assert "2 Offlaner" in fake.scenes and ("scene_create", "2 Hard support") in fake.ops
        assert avisos and avisos[-1][0] == "info"
        assert not page.create_button.isEnabled()           # ya no falta nada
    finally:
        win.close()


def test_crear_escenas_fallida_nombra_la_que_quedo_a_medias(qapp, appdata, monkeypatch):
    fake = _fake(sin_escenas=("2 Offlaner",))

    def falla(client, main, **kw):
        raise SceneBuildError("2 Offlaner", [], RuntimeError("rechazado"))
    monkeypatch.setattr(scene_builder, "clone_player_scenes", falla)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a[2]))
    parts, win = _armar(fake)
    try:
        _conectar(qapp, win)
        win.scene_page.create_button.click()
        _esperar(qapp, win)
        assert len(avisos) == 1
        assert "2 Offlaner" in avisos[0] and "bórrala en OBS" in avisos[0]
    finally:
        win.close()


def test_escena_muestra_borde_y_estado_de_las_escenas(qapp, appdata, tmp_path):
    borde = tmp_path / "Borde.png"
    borde.write_bytes(b"png")
    fake = _fake(sin_escenas=("2 Offlaner",), borde_file=str(borde))
    parts, win = _armar(fake)
    try:
        _conectar(qapp, win)
        page = win.scene_page
        assert page.borde_path.full_text() == str(borde)
        assert page.scene_icons["1 Hard carry"].status == "ok"
        assert page.scene_icons["2 Offlaner"].status == "error"
        assert page.borde_browse_button.isEnabled()
    finally:
        win.close()


def test_paginas_en_ingles(qapp, appdata):
    i18n.set_language("en")
    parts, win = _armar(_fake())
    try:
        labels = {lbl.text() for lbl in win.findChildren(QLabel)}
        assert {"Role", "Name", "Camera URL", "Photo URL", "Use",
                "Abilities"} <= labels
        row = win.players_page.rows["1 Hard carry"]
        assert row.use_selector.buttons["camera"].text() == "Camera"
        assert win.scene_page.test_buttons[4].text() == "Test"
    finally:
        win.close()
