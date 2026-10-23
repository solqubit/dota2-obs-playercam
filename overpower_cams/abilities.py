"""Habilidades de un jugador según GSI -> preset del HUD (filtro `H 4/5/6 habilidades`).

Sin E/S (salvo cargar una vez el catálogo de innatas al importar). En el GSI de espectador la
sección es `abilities.team2.player0.ability0…` (la misma forma que `player` y `hero`, que
recorre `engine.iter_players`).

Regla (validada con una captura real de espectador): lugares del HUD = cantidad de entradas
`abilityN` (dict) de GSI, SIN contar los nombres que sean:
  - `generic_hidden` (ranura vacía/oculta),
  - `special_bonus*` (talentos),
  - innatas que usan el icono separado o están ocultas. Ser pasiva NO basta para
    descartarla: FORCE_NO_INNATE_UI permite que una innata pasiva ocupe un espacio
    normal (Nature's Guise de Treant).
GSI no manda esos indicadores: `data/innate_abilities.json` guarda los comportamientos
de Valve para las innatas de todos los héroes. Se regenera con `tools/update_innates.py
--refresh` tras parches. Las habilidades nuevas de Shard/Cetro y las robadas/devoradas
cuentan cuando aparecen en GSI, sin sumar espacios por tener un objeto. No se filtra
por nivel, cooldown, can_cast o ability_active: no describen la visibilidad en el HUD.
"""
import json

from .config import HUD_FILTERS
from .paths import resource_path

HUD_MIN = min(HUD_FILTERS)   # 4
HUD_MAX = max(HUD_FILTERS)   # 6


# DOTA_ABILITY_BEHAVIOR (uint64), de los indicadores del propio juego.
HIDDEN = 1
PASSIVE = 2
INNATE_UI = 1 << 43
FORCE_NO_INNATE_UI = 1 << 49


def innate_uses_hud_slot(behavior: int) -> bool:
    """Clasifica una innata por su UI, sin excepciones por nombre de héroe."""
    if behavior & (HIDDEN | INNATE_UI):
        return False
    return not behavior & PASSIVE or bool(behavior & FORCE_NO_INNATE_UI)


def _cargar_innatas_sin_espacio() -> frozenset[str]:
    try:
        ruta = resource_path("overpower_cams/data/innate_abilities.json")
        data = json.loads(ruta.read_text(encoding="utf-8"))
        current = {name for name, flags in data["abilities"].items()
                   if not innate_uses_hud_slot(int(flags))}
        return frozenset(current | set(data["legacy_non_slots"]))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return frozenset()


NON_SLOT_INNATES = _cargar_innatas_sin_espacio()


def count_abilities(player_abilities: dict) -> int | None:
    """Cantidad de habilidades que ocupan un lugar en el HUD, o None si no hay datos
    (entrada inválida o ninguna habilidad contable). Ver la regla en el docstring del módulo."""
    if not isinstance(player_abilities, dict):
        return None
    total = 0
    for key, ab in player_abilities.items():
        if not (str(key).startswith("ability") and str(key)[7:].isdigit() and isinstance(ab, dict)):
            continue
        name = str(ab.get("name", ""))
        if (not name or name == "generic_hidden" or name.startswith("special_bonus")
                or name in NON_SLOT_INNATES):
            continue
        total += 1
    return total or None


def hud_preset(count: int | None) -> int:
    """Preset del HUD (4, 5 o 6): sin datos -> 4; fuera de rango -> el extremo más cercano."""
    if count is None:
        return HUD_MIN
    return max(HUD_MIN, min(HUD_MAX, int(count)))
