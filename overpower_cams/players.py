"""Datos por jugador (nombre, cámara, foto, si se muestra) y nombres de equipo."""
from __future__ import annotations

from dataclasses import dataclass

USES = ("camera", "photo")


@dataclass
class PlayerConfig:
    name: str = ""
    camera_url: str = ""
    photo_url: str = ""
    use: str = "camera"   # "camera" | "photo"
    visible: bool = True  # «Mostrar»: False = al elegirlo no sale nada al aire


@dataclass
class TeamsConfig:
    team1: str = ""
    team2: str = ""


def is_visible(p: PlayerConfig | None) -> bool:
    """Si el jugador sale al aire al elegirlo (sin datos, sí)."""
    return p is None or p.visible is not False


def effective_use(p: PlayerConfig) -> str | None:
    """Respeta la fuente elegida; sin URL queda en blanco, sin cambiar a la otra."""
    urls = {"camera": p.camera_url, "photo": p.photo_url}
    chosen = p.use if p.use in urls else "camera"
    return chosen if urls[chosen].strip() else None
