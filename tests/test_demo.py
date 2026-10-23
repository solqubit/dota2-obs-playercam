import json
from pathlib import Path

import pytest

from overpower_cams.config import PLAYER_SCENES, source_name
from overpower_cams.demo import GRAPHICS, prepare_demo

ROOT = Path(__file__).resolve().parent.parent


def demo_folder(tmp_path):
    folder = tmp_path / "Una ruta con espacios y ñ" / "Camaraman"
    for relative in ("Ecenas/Camaraman.json", *GRAPHICS.values()):
        p = folder / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        if relative.endswith(".json"):
            p.write_bytes((ROOT / "obs/example-scene.json").read_bytes())
        else:
            p.write_bytes(b"test image")
    return folder


def test_reubica_los_31_graficos_sin_cambiar_parametros_ni_la_plantilla(tmp_path):
    folder = demo_folder(tmp_path)
    template = folder / "Ecenas/Camaraman.json"
    original = template.read_bytes()
    output = prepare_demo(folder)
    actual = json.loads(output.read_text(encoding="utf-8"))
    before = json.loads(original)
    sources = {s["name"]: s for s in actual["sources"]}
    assert actual["resolution"] == {"x": 3840, "y": 2160}
    assert sources["Juego"]["filters"] == next(s for s in before["sources"] if s["name"] == "Juego")["filters"]
    assert sources["Borde"]["settings"]["file"] == (folder / "Borde.png").as_posix()
    for scene in PLAYER_SCENES:
        assert sources[source_name("Fondo", scene)]["settings"]["file"] == (folder / GRAPHICS["background"]).as_posix()
        for kind in ("Camara", "Foto"):
            source = sources[source_name(kind, scene)]
            assert source["settings"]["url"] == ""
            assert source["filters"][0]["settings"]["image_path"] == (folder / GRAPHICS["mask"]).as_posix()
    assert template.read_bytes() == original
    second = prepare_demo(folder)
    assert second != output and output.exists()


def test_recursos_incompletos_no_generan_escena(tmp_path):
    folder = demo_folder(tmp_path)
    (folder / GRAPHICS["mask"]).unlink()
    with pytest.raises(ValueError, match="Falta Mascara"):
        prepare_demo(folder)
    assert not (folder / "Ecenas/Camaraman-lista.json").exists()
