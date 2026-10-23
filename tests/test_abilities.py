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
    assert "lion_to_hell_and_back" in mod.INNATE_PASSIVES
    assert "invoker_invoke" not in mod.INNATE_PASSIVES
    assert count_abilities(_ab("a", "b", "c", "d", "lion_to_hell_and_back")) == 4
    assert count_abilities(_ab("a", "b", "c", "d", "invoker_invoke")) == 5


def test_lista_de_innatas_pasivas_cargada():
    assert len(mod.INNATE_PASSIVES) == 172
