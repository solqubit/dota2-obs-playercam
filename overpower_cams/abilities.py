"""Habilidades de un jugador según GSI -> preset del HUD (filtro `H 4/5/6 habilidades`).

Sin E/S (salvo cargar una vez la lista de innatas al importar). En el GSI de espectador la
sección es `abilities.team2.player0.ability0…` (la misma forma que `player` y `hero`, que
recorre `engine.iter_players`).

Regla (validada con una captura real de espectador): lugares del HUD = cantidad de entradas
`abilityN` (dict) de GSI, SIN contar los nombres que sean:
  - `generic_hidden` (ranura vacía/oculta),
  - `special_bonus*` (talentos),
  - innatas pasivas: GSI sí lista las innatas (p. ej. `lion_to_hell_and_back`,
    `storm_spirit_galvanized`) pero las pasivas se ven como un icono chico aparte, no como
    lugar del HUD. Las innatas activas (`invoker_invoke`, `kez_switch_weapons`,
    `lone_druid_spirit_bear`…) sí ocupan lugar y cuentan.
GSI no marca las innatas, así que se usa `data/innate_passives.json` (innatas con
comportamiento Passive, generado por `tools/update_innates.py` desde OpenDota dotaconstants,
MIT; hay que regenerarlo tras parches). Las habilidades robadas/devoradas (Rubick, Doom)
cuentan porque GSI las lista como `abilityN` normales.
"""
import json

from .config import HUD_FILTERS
from .paths import resource_path

HUD_MIN = min(HUD_FILTERS)   # 4
HUD_MAX = max(HUD_FILTERS)   # 6


def _cargar_innatas_pasivas() -> frozenset[str]:
    try:
        ruta = resource_path("overpower_cams/data/innate_passives.json")
        return frozenset(json.loads(ruta.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return frozenset()


INNATE_PASSIVES = _cargar_innatas_pasivas()


def count_abilities(player_abilities: dict) -> int | None:
    """Cantidad de habilidades que ocupan un lugar en el HUD, o None si no hay datos
    (entrada inválida o ninguna habilidad contable). Ver la regla en el docstring del módulo."""
    if not isinstance(player_abilities, dict):
        return None
    total = 0
    for key, ab in player_abilities.items():
        if not (str(key).startswith("ability") and isinstance(ab, dict)):
            continue
        name = str(ab.get("name", ""))
        if (name == "generic_hidden" or name.startswith("special_bonus")
                or name in INNATE_PASSIVES):
            continue
        total += 1
    return total or None


def hud_preset(count: int | None) -> int:
    """Preset del HUD (4, 5 o 6): sin datos -> 4; fuera de rango -> el extremo más cercano."""
    if count is None:
        return HUD_MIN
    return max(HUD_MIN, min(HUD_MAX, int(count)))
