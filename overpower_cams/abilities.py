"""Habilidades de un jugador según GSI -> preset del HUD (filtro `H 4/5/6 habilidades`).

Sin E/S. En el GSI de espectador la sección es `abilities.team2.player0.ability0…`
(la misma forma que `player` y `hero`, que recorre `engine.iter_players`).
"""
from .config import HUD_FILTERS

HUD_MIN = min(HUD_FILTERS)   # 4
HUD_MAX = max(HUD_FILTERS)   # 6


def count_abilities(player_abilities: dict) -> int | None:
    """Cantidad de habilidades que ocupan un lugar en el HUD, o None si no hay datos.

    # provisional hasta Task 2: cuenta las entradas `abilityN` (dict) que no sean
    # `special_bonus*` ni `generic_hidden`; la regla final sale de capturas reales.
    """
    if not isinstance(player_abilities, dict):
        return None
    total = 0
    for key, ab in player_abilities.items():
        if not (str(key).startswith("ability") and isinstance(ab, dict)):
            continue
        name = str(ab.get("name", ""))
        if name.startswith("special_bonus") or name == "generic_hidden":
            continue
        total += 1
    return total or None


def hud_preset(count: int | None) -> int:
    """Preset del HUD (4, 5 o 6): sin datos -> 4; fuera de rango -> el extremo más cercano."""
    if count is None:
        return HUD_MIN
    return max(HUD_MIN, min(HUD_MAX, int(count)))
