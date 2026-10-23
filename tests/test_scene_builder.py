"""Tests de scene_builder: crear escenas de jugador copiando la plantilla en vivo."""
import pytest

from overpower_cams import scene_builder
from overpower_cams.config import source_name
from overpower_cams.scene_builder import SceneBuildError, clean_transform, clone_player_scenes
from tests.conftest import FakeObsClient

PLANTILLA = "1 Hard carry"
KINDS = ("Camara", "Foto", "Fondo", "Nombre")
MASCARA = {"kind": "mask_filter_v2", "enabled": True, "settings": {"image_path": "m.png", "opacity": 0.5}}
TRANSFORM_ITEM = {"positionX": 431.0, "positionY": 1778.0, "scaleX": 0.2, "scaleY": 0.2}


def _fake(extra_scenes=()):
    scenes = {"Juego": {"Captura": None, PLANTILLA: None, "Borde": None},
              PLANTILLA: {source_name(k, PLANTILLA): None for k in KINDS}}
    for s in extra_scenes:
        scenes[s] = {source_name(k, s): None for k in KINDS}
    inputs = {source_name("Camara", PLANTILLA): {"url": "https://cam", "width": 1920},
              source_name("Foto", PLANTILLA): {"url": "https://foto"},
              source_name("Fondo", PLANTILLA): {"file": "fondo.png"},
              source_name("Nombre", PLANTILLA): {"text": "Carry", "font": {"size": 40}}}
    kinds = {source_name("Camara", PLANTILLA): "browser_source",
             source_name("Foto", PLANTILLA): "browser_source",
             source_name("Fondo", PLANTILLA): "image_source",
             source_name("Nombre", PLANTILLA): "text_gdiplus_v3"}
    c = FakeObsClient(scenes=scenes, scene="Juego", inputs=inputs,
                      filters={source_name("Camara", PLANTILLA): {"Mascara": MASCARA}})
    c.input_kinds.update(kinds)
    c.transforms[("Juego", c.id_of(PLANTILLA, "Juego"))] = dict(TRANSFORM_ITEM, rotation=3.0)
    c.transforms[(PLANTILLA, c.id_of(source_name("Camara", PLANTILLA)))] = {
        "positionX": 10.0, "positionY": 20.0, "scaleX": 0.5, "scaleY": 0.5}
    c.enabled[(PLANTILLA, c.id_of(source_name("Camara", PLANTILLA)))] = True
    c.enabled[(PLANTILLA, c.id_of(source_name("Foto", PLANTILLA)))] = False
    c.ops.clear()
    return c


def test_crea_escena_con_las_cuatro_fuentes_y_settings():
    c = _fake()
    creadas = clone_player_scenes(c, "Juego", PLANTILLA, ["2 Mid laner"])
    assert creadas == ["2 Mid laner"]
    for k in KINDS:
        assert c.is_enabled(source_name(k, "2 Mid laner"), "2 Mid laner") is not None
    assert c.inputs[source_name("Camara", "2 Mid laner")] == {"url": "", "width": 1920}
    assert c.inputs[source_name("Foto", "2 Mid laner")] == {"url": ""}
    assert c.inputs[source_name("Fondo", "2 Mid laner")] == {"file": "fondo.png"}
    assert c.inputs[source_name("Nombre", "2 Mid laner")] == {"text": "2 Mid laner", "font": {"size": 40}}
    assert c.input_kinds[source_name("Fondo", "2 Mid laner")] == "image_source"
    # la plantilla no cambia
    assert c.inputs[source_name("Camara", PLANTILLA)]["url"] == "https://cam"
    assert c.inputs[source_name("Nombre", PLANTILLA)]["text"] == "Carry"


def test_copia_transform_visibilidad_y_filtros_dentro_de_la_escena():
    c = _fake()
    clone_player_scenes(c, "Juego", PLANTILLA, ["2 Mid laner"])
    cam = source_name("Camara", "2 Mid laner")
    key = ("2 Mid laner", c.id_of(cam, "2 Mid laner"))
    assert c.transforms[key]["positionX"] == 10.0 and c.transforms[key]["scaleX"] == 0.5
    assert c.is_enabled(cam, "2 Mid laner") is True
    assert c.is_enabled(source_name("Foto", "2 Mid laner"), "2 Mid laner") is False
    assert c.filters[cam]["Mascara"] == MASCARA


def test_item_en_principal_apagado_con_transform_de_la_plantilla():
    c = _fake()
    clone_player_scenes(c, "Juego", PLANTILLA, ["2 Mid laner"])
    assert c.is_enabled("2 Mid laner", "Juego") is False
    key = ("Juego", c.id_of("2 Mid laner", "Juego"))
    assert c.transforms[key]["positionX"] == 431.0
    assert c.transforms[key]["scaleY"] == 0.2 and c.transforms[key]["rotation"] == 3.0


def test_destino_existente_no_se_toca():
    c = _fake(extra_scenes=["1 Mid laner"])
    c.inputs[source_name("Nombre", "1 Mid laner")] = {"text": "Mio"}
    antes = list(c.ops)
    creadas = clone_player_scenes(c, "Juego", PLANTILLA, ["1 Mid laner", PLANTILLA])
    assert creadas == []
    assert c.ops == antes and c.created == []
    assert c.inputs[source_name("Nombre", "1 Mid laner")] == {"text": "Mio"}


def test_fallo_a_medias_lanza_error_claro_y_no_sigue():
    c = _fake()
    c.inputs["Foto · 2 Offlaner"] = {}   # nombre ocupado: CreateInput falla (nombres únicos)
    with pytest.raises(SceneBuildError) as e:
        clone_player_scenes(c, "Juego", PLANTILLA, ["2 Mid laner", "2 Offlaner", "2 Soft support"])
    assert e.value.target == "2 Offlaner"
    assert e.value.created == ["2 Mid laner"]
    assert "2 Soft support" not in c.scenes     # no continúa con el resto
    assert "1 Hard carry" in c.scenes           # y nada existente se altera


def test_sin_plantilla_falla_sin_crear_nada():
    c = _fake()
    with pytest.raises(SceneBuildError):
        clone_player_scenes(c, "Juego", "No existe", ["2 Mid laner"])
    assert "2 Mid laner" not in c.scenes


def test_clean_transform_quita_solo_lectura_y_bounds_invalidos():
    bruto = {"positionX": 1.0, "scaleX": 2.0, "sourceWidth": 100.0, "sourceHeight": 50.0,
             "width": 200.0, "height": 100.0, "boundsType": "OBS_BOUNDS_NONE",
             "boundsWidth": 1.0, "boundsHeight": 1.0}
    assert clean_transform(bruto) == {"positionX": 1.0, "scaleX": 2.0, "boundsType": "OBS_BOUNDS_NONE"}
    con = dict(bruto, boundsType="OBS_BOUNDS_STRETCH", boundsWidth=300.0, boundsHeight=200.0)
    assert clean_transform(con)["boundsWidth"] == 300.0
    chico = dict(con, boundsHeight=0.0)
    out = clean_transform(chico)
    assert "boundsWidth" not in out and "boundsHeight" not in out
