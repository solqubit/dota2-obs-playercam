"""La escena de OBS de ejemplo v2 (obs/example-scene.json) sirve tal cual para la app."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

from overpower_cams.config import (
    COMPANIONS, DEFAULT_MAIN_SCENE, HUD_FILTERS, MOVE_FILTER_KIND, PLAYER_SCENES, source_name,
)
from overpower_cams.obs_link import ObsLink

EJEMPLO = Path(__file__).resolve().parent.parent / "obs" / "example-scene.json"
TIPOS = {"Camara": "browser_source", "Foto": "browser_source", "Fondo": "image_source",
         "Nombre": "text_gdiplus"}


def _coleccion():
    return json.loads(EJEMPLO.read_text(encoding="utf-8"))


def _fuentes(col):
    return {s["name"]: s for s in col["sources"]}


class ClienteDesdeColeccion:
    """Responde como OBS a partir de la colección de escenas exportada (solo lectura)."""

    def __init__(self, coleccion):
        self.escenas = {s["name"]: s["settings"]["items"]
                        for s in coleccion["sources"] if s["id"] == "scene"}

    def get_scene_item_list(self, name):
        return SimpleNamespace(scene_items=[
            {"sourceName": i["name"], "sceneItemId": i["id"], "isGroup": False}
            for i in self.escenas[name]])

    def disconnect(self):
        pass


def test_la_app_encuentra_las_escenas_de_jugador_y_el_borde_en_juego():
    obs = ObsLink("127.0.0.1", 4455, "", main_scene=DEFAULT_MAIN_SCENE,
                  client_factory=lambda **kw: ClienteDesdeColeccion(_coleccion()))
    assert obs.connect()
    found = obs.find_scene_items(DEFAULT_MAIN_SCENE)
    assert [n for n in PLAYER_SCENES + COMPANIONS if n not in found] == []


def test_juego_mas_diez_escenas_de_jugador_con_sus_cuatro_fuentes():
    col = _coleccion()
    fuentes = _fuentes(col)
    escenas = [n for n, s in fuentes.items() if s["id"] == "scene"]
    assert sorted(escenas) == sorted([DEFAULT_MAIN_SCENE] + PLAYER_SCENES)    # sin escenas de más ni Prueba
    assert "Prueba" not in fuentes and "canvases" not in col
    for esc in PLAYER_SCENES:
        items = [i["name"] for i in fuentes[esc]["settings"]["items"]]
        assert items == [source_name(k, esc) for k in TIPOS]
        for k, tipo in TIPOS.items():
            assert fuentes[source_name(k, esc)]["id"] == tipo


def test_borde_y_captura_de_dota_en_juego():
    fuentes = _fuentes(_coleccion())
    items = [i["name"] for i in fuentes[DEFAULT_MAIN_SCENE]["settings"]["items"]]
    assert "Borde" in items and "Captura de juego" in items
    assert fuentes["Borde"]["settings"]["file"] == ""                # la app ofrece "Arreglar"
    captura = fuentes["Captura de juego"]
    assert captura["id"] == "game_capture" and captura["settings"]["window"].endswith("dota2.exe")


def test_filtros_h_de_move_source_en_juego():
    filtros = _fuentes(_coleccion())[DEFAULT_MAIN_SCENE]["filters"]
    assert [f["name"] for f in filtros] == [HUD_FILTERS[n] for n in (4, 5, 6)]
    assert all(f["id"] == MOVE_FILTER_KIND for f in filtros)


def test_mascaras_sin_ruta_y_textos_con_el_nombre_de_la_escena():
    fuentes = _fuentes(_coleccion())
    for esc in PLAYER_SCENES:
        for k in ("Camara", "Foto"):
            f = fuentes[source_name(k, esc)]
            assert f["settings"]["url"] == ""
            assert [(x["id"], x["settings"]["image_path"]) for x in f["filters"]] == [("mask_filter", "")]
        assert fuentes[source_name("Fondo", esc)]["settings"]["file"] == ""
        assert fuentes[source_name("Nombre", esc)]["settings"]["text"] == esc   # sin nombres reales


def test_sin_rutas_ni_datos_personales():
    texto = EJEMPLO.read_text(encoding="utf-8")
    assert not re.search(r"(?i)\b[a-z]:[\/]", texto)        # rutas de disco
    assert not re.search(r"(?i)https?://", texto)             # enlaces a terceros
    assert "Users" not in texto and "damia" not in texto.lower()
    col = json.loads(texto)
    assert not [k for k in col if "AudioDevice" in k and col[k]["settings"] != {"device_id": "default"}]
    assert col["current_scene"] == col["current_program_scene"] == DEFAULT_MAIN_SCENE
