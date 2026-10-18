import json
import pathlib

import pytest

from overpower_cams.config import PORTRAIT_PITCH, SLOTS
from overpower_cams.portraits import PortraitModel

DATA = pathlib.Path(__file__).parent / "data"


def _centro_px(slot):
    """Centro por defecto de un retrato, en fracción del alto (1080 px)."""
    k = 5 - int(slot[1:]) if slot[0] == "r" else int(slot[1:]) - 1
    off = 128 / 1080 if slot[0] == "r" else 139 / 1080
    d = off + k * PORTRAIT_PITCH
    return -d if slot[0] == "r" else d


def test_offsets_por_defecto():
    o = PortraitModel({}).row_offsets()
    assert o["r"] == pytest.approx(128 / 1080)
    assert o["d"] == pytest.approx(139 / 1080)


def test_toda_la_zona_de_cada_retrato():
    m = PortraitModel({})
    for slot in SLOTS:
        c = _centro_px(slot)
        for dx in range(-30, 31, 5):
            assert m.portrait_at(c + dx / 1080, 0.02) == slot, (slot, dx)


def test_reloj_y_mapa():
    m = PortraitModel({})
    assert m.portrait_at(0.0, 0.02) is None
    assert m.portrait_at(-0.2, 0.3) is None


def test_clicks_reales_de_ejemplo():
    portraits = json.loads((DATA / "input_map_ejemplo.json").read_text(encoding="utf-8"))["portraits"]
    m = PortraitModel(portraits)
    assert len(portraits) == 10
    for slot, (x, y, _n) in portraits.items():
        assert m.portrait_at(x, y) == slot


def test_learn_promedia_y_topa_n():
    m = PortraitModel({})
    m.learn("r1", -0.30, 0.02)
    assert m.as_dict()["r1"] == [-0.30, 0.02, 1]
    m.learn("r1", -0.32, 0.04)
    assert m.as_dict()["r1"] == [-0.31, 0.03, 2]
    for _ in range(20):
        m.learn("r1", -0.31, 0.03)
    assert m.as_dict()["r1"][2] == 10


def test_learn_afina_los_offsets():
    m = PortraitModel({})
    m.learn("r5", -0.14, 0.02)           # el retrato real está algo más afuera
    assert m.row_offsets()["r"] > 128 / 1080
    assert m.portrait_at(-0.14, 0.02) == "r5"


def test_forget_y_forget_all_y_as_dict_es_copia():
    m = PortraitModel({"r1": [-0.3, 0.02, 2], "d1": [0.13, 0.02, 1]})
    assert m.forget("r1") is True
    assert m.forget("r1") is False
    d = m.as_dict()
    assert list(d) == ["d1"]
    d["d1"][0] = 99                       # no debe afectar al modelo
    assert m.as_dict()["d1"][0] == 0.13
    m.forget_all()
    assert m.as_dict() == {}


def test_ignora_entradas_corruptas():
    sucio = {
        "r1": "hola", "r2": [1, 2], "r3": [1, 2, 3, 4], "r4": [None, 0.02, 1],
        "r5": [float("nan"), 0.02, 1], "d1": [True, 0.02, 1], "d2": [0.2, 0.02, 0],
        "xx": [0.2, 0.02, 1], "d3": [0.25, 0.02, "3"], "d4": [0.29, 0.02, 2],
    }
    m = PortraitModel(sucio)
    assert list(m.as_dict()) == ["d4"]
    assert m.portrait_at(0.29, 0.02) == "d4"
    assert PortraitModel("basura").as_dict() == {}
    assert PortraitModel(None).as_dict() == {}


def test_n_enorme_se_topa_al_cargar():
    m = PortraitModel({"d1": [0.13, 0.02, 10**9]})
    assert m.as_dict()["d1"][2] == 10
    m.row_offsets()                       # no debe agotar la memoria
