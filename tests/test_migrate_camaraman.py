"""Tests de la migración de la colección Camaraman (tools/migrate_camaraman.py), sobre una colección mínima."""
import json
import re
import shutil
from pathlib import Path

import pytest

from tools import migrate_camaraman as mig

MIN = Path(__file__).resolve().parent / "data" / "camaraman_min.json"
ESCENAS = ["1 Hard carry", "1 Mid laner", "1 Offlaner", "1 Soft support", "1 Hard support",
           "2 Hard carry", "2 Mid laner", "2 Offlaner", "2 Soft support", "2 Hard support"]
SEP = " · "


@pytest.fixture
def coleccion(tmp_path):
    destino = tmp_path / "Camaraman.json"
    shutil.copy(MIN, destino)
    return destino


def _cargar(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _fuentes(col):
    return {s["name"]: s for s in col["sources"]}


def _items(col, escena):
    return [i["name"] for i in _fuentes(col)[escena]["settings"]["items"]]


def _correr(args, *, corriendo=False):
    return mig.main([str(a) for a in args], is_running=lambda exe: corriendo)


def test_informe_en_seco_lista_y_no_escribe(coleccion, capsys):
    antes = coleccion.read_bytes()
    assert _correr([coleccion]) == 0
    salida = capsys.readouterr().out
    assert coleccion.read_bytes() == antes
    assert not list(coleccion.parent.glob("*.bak"))
    assert "Camara Jugador URL" in salida and f"Camara{SEP}1 Hard carry" in salida   # renombres
    assert "2 Mid laner" in salida and "Marco" in salida and "Camara mid" in salida  # qué se borra y de dónde
    assert "Juego" in salida                                                         # transforms
    assert "Fondo texto" in salida                                                   # fuente huérfana


def test_apply_deja_las_10_escenas_con_4_fuentes_unicas(coleccion):
    assert _correr([coleccion, "--apply"]) == 0
    col = _cargar(coleccion)
    fuentes = _fuentes(col)
    nombres = [s["name"] for s in col["sources"]]
    assert len(nombres) == len(set(nombres))                      # sin duplicados
    uuids = [s["uuid"] for s in col["sources"]]
    assert len(uuids) == len(set(uuids))
    tipos = {"Camara": "browser_source", "Foto": "browser_source", "Fondo": "image_source", "Nombre": "text_gdiplus"}
    for esc in ESCENAS:
        items = _items(col, esc)
        assert items == [f"{p}{SEP}{esc}" for p in ("Camara", "Foto", "Fondo", "Nombre")] or \
            (esc == "1 Mid laner" and items[:4] == [f"{p}{SEP}{esc}" for p in ("Camara", "Foto", "Fondo", "Nombre")])
        for it in fuentes[esc]["settings"]["items"]:
            fuente = fuentes[it["name"]]
            assert it["source_uuid"] == fuente["uuid"]
            if SEP in it["name"]:
                assert fuente["id"] == tipos[it["name"].split(SEP)[0]]
        assert fuentes[f"Nombre{SEP}{esc}"]["settings"]["text"] == esc
        for p in ("Camara", "Foto"):
            f = fuentes[f"{p}{SEP}{esc}"]
            if esc != "1 Hard carry":                    # la plantilla conserva su URL
                assert f["settings"]["url"] == ""
            assert [x["id"] for x in f["filters"]] == ["mask_filter"]
        ids = [i["id"] for i in fuentes[esc]["settings"]["items"]]
        assert len(ids) == len(set(ids)) and fuentes[esc]["settings"]["id_counter"] >= max(ids)


def test_apply_conserva_la_plantilla_y_renombra_referencias(coleccion):
    original = _cargar(coleccion)
    uuid_cam = _fuentes(original)["Camara Jugador URL"]["uuid"]
    _correr([coleccion, "--apply"])
    col = _cargar(coleccion)
    fuentes = _fuentes(col)
    assert fuentes[f"Camara{SEP}1 Hard carry"]["uuid"] == uuid_cam            # se renombra, no se clona
    assert fuentes[f"Fondo{SEP}1 Hard carry"]["settings"]["file"] == _fuentes(original)["Fondo Texto"]["settings"]["file"]
    for viejo in ("Camara Jugador URL", "Foto Jugador URL", "Fondo Texto", "Nombre Jugador"):
        assert viejo not in fuentes
    assert f"Camara{SEP}1 Hard carry" in _items(col, "Prueba")              # referencia en otra escena
    assert f"Nombre{SEP}1 Hard carry" in _items(col, "Prueba")


def test_no_borra_fuentes_usadas_por_otra_escena(coleccion):
    _correr([coleccion, "--apply"])
    col = _cargar(coleccion)
    fuentes = _fuentes(col)
    for vivo in ("Marco", "Color", "Foto mid"):     # los usa Prueba
        assert vivo in fuentes
    assert _items(col, "Prueba").count("Marco") == 1
    for muerto in ("Camara Mid", "Camara mid", "Foto Mid", "Nombre Mid", "Nombre mid", "Fondo texto"):
        assert muerto not in fuentes
    assert "Navegador" in fuentes                    # lo que no es de la estructura vieja se respeta


def test_apply_pone_en_juego_la_transform_de_hard_carry(coleccion):
    _correr([coleccion, "--apply"])
    col = _cargar(coleccion)
    items = {i["name"]: i for i in _fuentes(col)["Juego"]["settings"]["items"]}
    ref = items["1 Hard carry"]
    claves = ["pos", "pos_rel", "scale", "scale_rel", "rot", "align", "scale_ref", "bounds_type", "bounds",
              "crop_left", "crop_top", "crop_right", "crop_bottom"]
    for esc in ESCENAS:
        for k in claves:
            assert items[esc][k] == ref[k], (esc, k)
    assert items["1 Hard carry"]["visible"] is True and items["2 Hard support"]["visible"] is False
    original = {i["name"]: i for i in _fuentes(_cargar(MIN))["Juego"]["settings"]["items"]}
    assert items["Borde"] == original["Borde"]                                # el Borde no se mueve
    assert items["Prueba"] == original["Prueba"]


def test_apply_deja_intactos_los_filtros_h_y_otros_filtros(coleccion):
    original = _fuentes(_cargar(MIN))
    _correr([coleccion, "--apply"])
    nuevo = _fuentes(_cargar(coleccion))
    assert [f["name"] for f in nuevo["Juego"]["filters"]] == ["H 4 habilidades", "H 5 habilidades", "H 6 habilidades"]
    assert nuevo["Juego"]["filters"] == original["Juego"]["filters"]
    assert nuevo["2 Soft support"]["filters"] == original["2 Soft support"]["filters"]


def test_apply_hace_copia_y_conserva_el_formato(coleccion):
    antes = coleccion.read_bytes()
    _correr([coleccion, "--apply"])
    bak = coleccion.with_name(coleccion.name + ".antes_v2.bak")
    assert bak.read_bytes() == antes
    texto = coleccion.read_text(encoding="utf-8")
    assert texto == json.dumps(json.loads(texto), ensure_ascii=False, indent=4)
    assert "máscara" in texto                                                  # sin escapes \u


def test_apply_es_idempotente(coleccion):
    _correr([coleccion, "--apply"])
    una_vez = coleccion.read_bytes()
    assert _correr([coleccion, "--apply"]) == 0
    assert coleccion.read_bytes() == una_vez


def test_con_obs_corriendo_se_rechaza_sin_escribir(coleccion, capsys):
    antes = coleccion.read_bytes()
    assert _correr([coleccion, "--apply"], corriendo=True) != 0
    assert "OBS" in capsys.readouterr().err
    assert coleccion.read_bytes() == antes
    assert not list(coleccion.parent.glob("*.bak"))


def test_ejemplo_limpio(coleccion, tmp_path):
    salida = tmp_path / "ejemplo.json"
    assert _correr([coleccion, "--example", salida]) == 0      # sin --apply la colección original no se toca
    assert coleccion.read_bytes() == MIN.read_bytes()
    texto = salida.read_text(encoding="utf-8")
    assert not re.search(r"(?i)\b[a-z]:[\\/]", texto)
    assert not re.search(r"(?i)https?://", texto)
    assert "Users" not in texto and "example.invalid" not in texto
    col = json.loads(texto)
    fuentes = _fuentes(col)
    assert "Prueba" not in fuentes and "Prueba" not in [e["name"] for e in col["scene_order"]]
    assert "Prueba" not in _items(col, "Juego")
    assert col["current_scene"] == col["current_program_scene"] == "Juego"
    assert [f["name"] for f in fuentes["Juego"]["filters"]] == ["H 4 habilidades", "H 5 habilidades", "H 6 habilidades"]
    assert all(f["id"] == "move_source_filter" for f in fuentes["Juego"]["filters"])
    for esc in ESCENAS:
        assert _items(col, esc) == [f"{p}{SEP}{esc}" for p in ("Camara", "Foto", "Fondo", "Nombre")]
        for p in ("Camara", "Foto"):
            f = fuentes[f"{p}{SEP}{esc}"]
            assert f["settings"]["url"] == ""
            assert [(x["id"], x["settings"]["image_path"]) for x in f["filters"]] == [("mask_filter", "")]
        assert fuentes[f"Fondo{SEP}{esc}"]["settings"]["file"] == ""
    assert col["AuxAudioDevice1"]["settings"] == {"device_id": "default"}
    sobrantes = {n for n, s in fuentes.items() if s["id"] != "scene"} - {"Captura de juego", "Borde"}
    assert all(SEP in n for n in sobrantes)                    # nada de Marco, Color, Navegador...
    assert fuentes["Borde"]["settings"]["file"] == ""


def test_ejemplo_con_apply_tambien_migra_la_original(coleccion, tmp_path):
    salida = tmp_path / "ejemplo.json"
    _correr([coleccion, "--apply", "--example", salida])
    assert f"Camara{SEP}2 Mid laner" in _fuentes(_cargar(coleccion))
    assert "Prueba" in _fuentes(_cargar(coleccion))            # la migrada conserva Prueba
    assert "Prueba" not in _fuentes(_cargar(salida))


def test_ejemplo_se_rechaza_si_pisaria_la_coleccion(coleccion):
    assert _correr([coleccion, "--example", coleccion]) != 0
    assert coleccion.read_bytes() == MIN.read_bytes()
