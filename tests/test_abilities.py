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
