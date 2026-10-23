"""Datos por jugador (nombre, cámara, foto) y nombres de equipo."""
from __future__ import annotations

from dataclasses import dataclass

USES = ("camera", "photo")


@dataclass
class PlayerConfig:
    name: str = ""
    camera_url: str = ""
    photo_url: str = ""
    use: str = "camera"   # "camera" | "photo"


@dataclass
class TeamsConfig:
    team1: str = ""
    team2: str = ""


def effective_use(p: PlayerConfig) -> str | None:
    """Respeta la fuente elegida; sin URL queda en blanco, sin cambiar a la otra."""
    urls = {"camera": p.camera_url, "photo": p.photo_url}
    chosen = p.use if p.use in urls else "camera"
    return chosen if urls[chosen].strip() else None
