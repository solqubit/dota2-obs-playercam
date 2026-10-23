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
    """Lo elegido si tiene URL; si no, lo otro si tiene URL; si no, None."""
    urls = {"camera": p.camera_url, "photo": p.photo_url}
    chosen = p.use if p.use in urls else "camera"
    other = "photo" if chosen == "camera" else "camera"
    if urls[chosen]:
        return chosen
    if urls[other]:
        return other
    return None
