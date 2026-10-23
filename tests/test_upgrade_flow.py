"""GSI simulado -> motor -> peticiones OBS: Shard/Cetro, reemplazos y desaparición.

Nombres de habilidades contrastados con herodata de Valve; estas son simulaciones,
no capturas de partidas reales. No se cambia Dota ni se conecta a OBS real.
"""
import pytest

from conftest import FakeClock, fake_camaraman, gsi_payload
from overpower_cams.config import HUD_FILTERS, PLAYER_SCENES
from overpower_cams.engine import Engine
from overpower_cams.obs_link import ObsLink
from overpower_cams.players import PlayerConfig
from overpower_cams.portraits import PortraitModel


@pytest.mark.parametrize("base,innate,upgrade,expected", [
    (("treant_natures_grasp", "treant_leech_seed", "treant_living_armor",
      "treant_natures_guise", "treant_overgrowth"), None, "treant_eyes_in_the_forest", 6),
    (("nyx_assassin_impale", "nyx_assassin_jolt", "nyx_assassin_spiked_carapace",
      "nyx_assassin_vendetta"), "nyx_assassin_neuro_sting", "nyx_assassin_burrow", 5),
    (("crystal_maiden_crystal_nova", "crystal_maiden_frostbite", "crystal_maiden_brilliance_aura",
      "crystal_maiden_freezing_field"), "crystal_maiden_glacial_guard", "crystal_maiden_crystal_clone", 5),
    (("ogre_magi_fireblast", "ogre_magi_ignite", "ogre_magi_bloodlust", "ogre_magi_multicast"),
     "ogre_magi_dumb_luck", "ogre_magi_unrefined_fireblast", 5),
])
def test_habilidad_nueva_y_retirada_ajustan_el_filtro_en_obs(base, innate, upgrade, expected):
    fake = fake_camaraman()
    players = {s: PlayerConfig(camera_url="https://example.com/camera") for s in PLAYER_SCENES}
    obs = ObsLink("127.0.0.1", 4455, "test", client_factory=fake.factory,
                  players_provider=lambda: players)
    assert obs.connect()
    obs.load_items()
    engine = Engine(obs, PortraitModel(), {}, clock=FakeClock(100))
    scene = "1 Hard carry"

    def post(names):
        data = gsi_payload("r1")
        # Una habilidad puede seguir visible sin nivel, sin maná o en cooldown.
        abilities = {f"ability{i}": {"name": name, "level": 0, "can_cast": False,
                                    "ability_active": False, "cooldown": 30}
                     for i, name in enumerate(names)}
        if innate:
            abilities["ability20"] = {"name": innate, "passive": True}
        data["abilities"] = {"team2": {"player0": abilities}}
        engine.process(data)

    try:
        post(base)
        assert engine.status().abilities[scene] == expected - 1
        fake.ops.clear()
        post((*base, upgrade))
        assert engine.status().abilities[scene] == expected
        assert fake.ops == [("filter_enabled", HUD_FILTERS[expected], True)]
        fake.ops.clear()
        post((*base, upgrade))             # los mismos datos no repiten la animación
        assert fake.ops == []
        if upgrade == "nyx_assassin_burrow":
            post((*base, "nyx_assassin_unburrow"))  # reemplaza el botón; no agrega otro
            assert engine.status().abilities[scene] == expected
            assert fake.ops == []
        post(base)
        assert engine.status().abilities[scene] == expected - 1
        assert fake.ops == [("filter_enabled", HUD_FILTERS[expected - 1], True)]
        assert fake.is_enabled(scene, "Juego") is True
    finally:
        obs.close()
