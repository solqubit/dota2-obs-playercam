import pytest

from overpower_cams.abilities import count_abilities, hud_preset


def test_hud_preset_rango():
    assert [hud_preset(n) for n in (4, 5, 6)] == [4, 5, 6]


def test_hud_preset_sin_datos_usa_4():
    assert hud_preset(None) == 4


def test_hud_preset_se_ajusta_al_extremo_mas_cercano():
    assert [hud_preset(n) for n in (0, 1, 3, 7, 8, 20)] == [4, 4, 4, 6, 6, 6]


def _ab(*nombres):
    return {f"ability{i}": {"name": n, "level": 1} for i, n in enumerate(nombres)}


def test_count_abilities_cuenta_las_normales():
    assert count_abilities(_ab("a", "b", "c", "d")) == 4


def test_count_abilities_ignora_talentos_y_ocultas():
    assert count_abilities(_ab("a", "b", "c", "d", "special_bonus_x", "generic_hidden")) == 4


def test_count_abilities_sin_datos_es_none():
    assert count_abilities({}) is None
    assert count_abilities(None) is None
    assert count_abilities("x") is None
    assert count_abilities({"ability0": 3}) is None


# --- datos reales (captura GSI de espectador, minuto 42) ---
import json
from pathlib import Path

from overpower_cams import abilities as mod

MUESTRA = json.loads(
    (Path(__file__).parent / "data" / "gsi_abilities_sample.json").read_text(encoding="utf-8"))
ESPERADO = {
    "doom_bringer": 6, "rubick": 6, "kez": 5, "bounty_hunter": 5, "lion": 4,
    "storm_spirit": 4, "disruptor": 4, "winter_wyvern": 4, "antimage": 4, "axe": 4,
}


def _jugadores():
    for equipo in MUESTRA.values():
        yield from equipo.values()


def test_muestra_real_cuenta_lo_esperado():
    obtenido = {j["hero"].removeprefix("npc_dota_hero_"): count_abilities(j["abilities"])
                for j in _jugadores()}
    assert obtenido == ESPERADO


def test_muestra_real_cubre_4_5_y_6():
    assert {hud_preset(count_abilities(j["abilities"])) for j in _jugadores()} == {4, 5, 6}


def test_innata_pasiva_no_cuenta_pero_la_activa_si():
    assert "lion_to_hell_and_back" in mod.NON_SLOT_INNATES
    assert "invoker_invoke" not in mod.NON_SLOT_INNATES
    assert count_abilities(_ab("a", "b", "c", "d", "lion_to_hell_and_back")) == 4
    assert count_abilities(_ab("a", "b", "c", "d", "invoker_invoke")) == 5


def test_catalogo_de_innatas_cargado():
    assert len(mod.NON_SLOT_INNATES) == 171


def test_treant_cuenta_su_innata_pasiva_en_el_hud():
    base = _ab("treant_natures_grasp", "treant_leech_seed", "treant_living_armor",
               "treant_natures_guise", "treant_overgrowth")
    base["ability3"]["passive"] = True
    assert count_abilities(base) == 5
    base["ability5"] = {"name": "treant_eyes_in_the_forest", "level": 1}
    assert count_abilities(base) == 6


@pytest.mark.parametrize("flags,expected", [
    (mod.PASSIVE, False),
    (mod.PASSIVE | mod.FORCE_NO_INNATE_UI, True),
    (mod.PASSIVE | mod.FORCE_NO_INNATE_UI | mod.HIDDEN, False),
    (mod.PASSIVE | mod.INNATE_UI, False),
    (4, True),                         # innata activa con espacio normal
    (4 | mod.INNATE_UI, False),        # manda la UI, no ser activa/pasiva
])
def test_indicadores_de_ui_sin_excepciones_por_heroe(flags, expected):
    assert mod.innate_uses_hud_slot(flags) is expected


# Catálogo consultado para los 127 héroes de Valve. Los demás usan el icono separado
# o están ocultos. Esta expectativa es independiente de la regla de bits del motor.
CATALOGO = json.loads((Path(__file__).parent.parent / "overpower_cams" / "data" /
                      "innate_abilities.json").read_text(encoding="utf-8"))
INNATAS_CON_ESPACIO = {
    "mirana_celestial_quiver", "lich_death_charge", "phantom_assassin_blur", "chen_zealot",
    "invoker_invoke", "lone_druid_spirit_bear", "treant_natures_guise",
    "visage_silent_as_the_grave", "troll_warlord_switch_stance", "earth_spirit_stone_caller",
    "monkey_king_mischief", "marci_special_delivery", "kez_switch_weapons",
}


@pytest.mark.parametrize("name", sorted(CATALOGO["abilities"]))
def test_clasificacion_de_cada_innata_del_catalogo(name):
    assert (name not in mod.NON_SLOT_INNATES) == (name in INNATAS_CON_ESPACIO)


def test_datos_incompletos_no_inventan_espacios():
    assert count_abilities({"ability0": {}, "ability1": {"name": ""},
                            "ability_extra": {"name": "no_es_una_ranura"}}) is None
