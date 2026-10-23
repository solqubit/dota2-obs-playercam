"""La regeneración aplica la misma regla a héroes futuros y conserva los datos ante errores."""
import json

import pytest

from overpower_cams.abilities import FORCE_NO_INNATE_UI, PASSIVE
from tools import update_innates as tool


def test_metadata_actual_reemplaza_la_clasificacion_anterior():
    metadata = {"heroes": 2, "abilities": {
        "future_innate": {"behavior": str(PASSIVE | FORCE_NO_INNATE_UI), "innate": True},
        "normal_passive": {"behavior": str(PASSIVE), "innate": False},
    }}
    previous = {"abilities": {"future_innate": str(PASSIVE)},
                "legacy_non_slots": ["older_innate", "normal_passive"]}
    catalog = tool.build_catalog(metadata, previous)
    assert catalog["abilities"] == {"future_innate": str(PASSIVE | FORCE_NO_INNATE_UI)}
    assert catalog["legacy_non_slots"] == ["older_innate"]


def test_innata_que_desaparece_sigue_reconocida_en_repeticiones():
    catalog = tool.build_catalog(
        {"heroes": 1, "abilities": {"new_innate": {"behavior": "2", "innate": True}}},
        {"abilities": {"old_innate": "2", "old_visible_innate": "4"}})
    assert catalog["legacy_non_slots"] == ["old_innate"]


def test_actualizacion_fallida_no_modifica_el_catalogo(tmp_path, monkeypatch):
    path = tmp_path / "innate_abilities.json"
    path.write_text('{"catalogo": "anterior"}', encoding="utf-8")
    monkeypatch.setattr(tool, "DESTINO", path)

    def fail():
        raise OSError("Valve no disponible")

    monkeypatch.setattr(tool, "fetch_metadata", fail)
    with pytest.raises(OSError):
        tool.main(["--refresh"])
    assert json.loads(path.read_text()) == {"catalogo": "anterior"}


def test_metadata_vacia_se_rechaza():
    with pytest.raises(ValueError):
        tool.build_catalog({"heroes": 0, "abilities": {}}, {})
