"""Prepara una colección de demo para la carpeta elegida, sin tocar OBS ni ajustes."""
from __future__ import annotations

import json
from pathlib import Path

from .config import PLAYER_SCENES, source_name

GRAPHICS = {
    "Borde": "Borde.png",
    "mask": "Mascara camara.png",
    "background": "Marcos/Marco sin camara.png",
}


def prepare_demo(folder: Path) -> Path:
    """Reubica todos los gráficos; crea otro JSON y conserva la plantilla original."""
    folder = Path(folder).resolve()
    template = folder / "Ecenas" / "Camaraman.json"
    for relative in ("Ecenas/Camaraman.json", *GRAPHICS.values()):
        if not (folder / relative).is_file():
            raise ValueError(f"Falta {relative}. Elige la carpeta Camaraman completa del ZIP.")
    collection = json.loads(template.read_text(encoding="utf-8-sig"))
    sources = {s["name"]: s for s in collection["sources"]}
    sources["Borde"]["settings"]["file"] = (folder / GRAPHICS["Borde"]).as_posix()
    for scene in PLAYER_SCENES:
        sources[source_name("Fondo", scene)]["settings"]["file"] = (
            folder / GRAPHICS["background"]).as_posix()
        for kind in ("Camara", "Foto"):
            source = sources[source_name(kind, scene)]
            source["settings"]["url"] = ""
            masks = [f for f in source.get("filters", [])
                     if f.get("id") in ("mask_filter", "mask_filter_v2")]
            if not masks:
                raise ValueError(f"Falta la máscara de {source['name']} en la plantilla.")
            for mask in masks:
                mask["settings"]["image_path"] = (folder / GRAPHICS["mask"]).as_posix()
    collection["name"] = "Camaraman Demo"
    output = folder / "Ecenas" / "Camaraman-lista.json"
    # Crear un nombre nuevo si el usuario conserva una preparación anterior.
    for index in range(1, 10000):
        candidate = output if index == 1 else output.with_stem(f"Camaraman-lista-{index}")
        try:
            with candidate.open("x", encoding="utf-8") as stream:
                json.dump(collection, stream, ensure_ascii=False, indent=4)
                stream.write("\n")
            return candidate
        except FileExistsError:
            continue
    raise ValueError("Demasiadas escenas preparadas en esta carpeta.")


def main() -> int:
    """Asistente independiente: no inicia GSI ni se conecta a OBS."""
    import sys
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Preparar demo Camaraman")
    initial = Path(sys.executable).parent.parent / "Camaraman"
    folder = QFileDialog.getExistingDirectory(
        None, "Elige la carpeta Camaraman / Choose the Camaraman folder", str(initial))
    if not folder:
        return 0
    try:
        output = prepare_demo(Path(folder))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        QMessageBox.critical(None, "Demo Camaraman", f"No se pudo preparar / Could not prepare:\n{exc}")
        return 1
    QMessageBox.information(
        None, "Demo Camaraman",
        f"Escena preparada / Scene prepared:\n{output}\n\n"
        "OBS: Colección de escenas → Importar / Scene Collection → Import.\n"
        "Lienzo base / Base canvas: 3840 × 2160.\n"
        "La salida puede ser 1080p o QHD sin cambiar los filtros.\n"
        "Output can be 1080p or QHD without changing the filters.\n\n"
        "Instala Move Transition 3.2.1 y reinicia OBS antes de importar.\n"
        "Install Move Transition 3.2.1 and restart OBS before importing.")
    return 0
