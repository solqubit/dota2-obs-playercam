"""La escena de OBS de ejemplo (obs/example-scene.json) sirve tal cual para la app."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

from overpower_cams.config import CAMERAS_TEAM1, CAMERAS_TEAM2, COMPANIONS, SCENE_NAME
from overpower_cams.obs_link import ObsLink

EJEMPLO = Path(__file__).resolve().parent.parent / "obs" / "example-scene.json"


def _coleccion():
    return json.loads(EJEMPLO.read_text(encoding="utf-8"))


class ClienteDesdeColeccion:
    """Responde como OBS a partir de la colección de escenas exportada (solo lectura)."""

    def __init__(self, coleccion):
        self.escenas = {s["name"]: s["settings"]["items"]
                        for s in coleccion["sources"] if s["id"] == "scene"}
        self.grupos = {g["name"]: g["settings"]["items"] for g in coleccion["groups"]}
        self.encendidos = []

    def _lista(self, items):
        # OBS ignora al cargar las copias de compatibilidad de los grupos
        return SimpleNamespace(scene_items=[
            {"sourceName": i["name"], "sceneItemId": i["id"], "isGroup": i["name"] in self.grupos}
            for i in items if not i.get("group_item_backup")])

    def get_scene_item_list(self, name):
        return self._lista(self.escenas[name])

    def get_group_scene_item_list(self, name):
        return self._lista(self.grupos[name])

    def set_scene_item_enabled(self, contenedor, item_id, enabled):
        self.encendidos.append((contenedor, item_id, enabled))

    def disconnect(self):
        pass


def test_la_app_encuentra_camaras_y_acompanantes():
    obs = ObsLink("127.0.0.1", 4455, "", client_factory=lambda **kw: ClienteDesdeColeccion(_coleccion()))
    assert obs.connect()
    rep = obs.load_items()
    assert rep.scene_found
    assert rep.missing_cameras == []
    assert rep.missing_companions == []


def test_cada_camara_es_un_grupo_con_su_vdo_adentro():
    col = _coleccion()
    grupos = {g["name"]: [i["name"] for i in g["settings"]["items"]] for g in col["groups"]}
    for cam in CAMERAS_TEAM1 + CAMERAS_TEAM2:
        assert grupos[cam] == [cam.replace("CAM_", "VDO_")]


def test_arranca_todo_oculto():
    col = _coleccion()
    escena = next(s for s in col["sources"] if s["name"] == SCENE_NAME)
    visibles = {i["name"] for i in escena["settings"]["items"]
                if i["visible"] and not i.get("group_item_backup")}
    assert not visibles & set(CAMERAS_TEAM1 + CAMERAS_TEAM2 + COMPANIONS)


def test_sin_rutas_ni_datos_personales():
    texto = EJEMPLO.read_text(encoding="utf-8")
    assert not re.search(r"(?i)\b[a-z]:[\\/]", texto)        # rutas de disco
    assert not re.search(r"(?i)https?://", texto)             # enlaces a terceros
    col = json.loads(texto)
    for s in col["sources"]:
        if s["name"] in COMPANIONS:
            assert "file" not in s["settings"]                # la app ofrece "Arreglar"
    assert col["AuxAudioDevice1"]["settings"] == {"device_id": "default"}
