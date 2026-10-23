from overpower_cams.config import (
    CAMERAS_TEAM1, CAMERAS_TEAM2, COMPANIONS, COMPANIONS_V1, DEFAULT_MAIN_SCENE, GSI_CFG_TEXT,
    HUD_FILTERS, MOVE_FILTER_KIND, PLAYER_SCENES, PLAYER_SCENES_TEAM1, PLAYER_SCENES_TEAM2,
    PORTRAIT_PITCH, ROLES, source_name,
)


def test_constantes_del_spec():
    assert len(CAMERAS_TEAM1 + CAMERAS_TEAM2) == 10
    assert COMPANIONS == ["Borde"]
    assert COMPANIONS_V1 == ["Borde", "Marco"]
    assert '"uri"           "http://127.0.0.1:3000/"' in GSI_CFG_TEXT
    assert '"throttle"      "0.01"' in GSI_CFG_TEXT
    assert round(PORTRAIT_PITCH * 1080) == 62


def test_gsi_pide_habilidades():
    assert '"abilities"     "1"' in GSI_CFG_TEXT


def test_escenas_de_jugador():
    assert len(ROLES) == 5
    assert PLAYER_SCENES_TEAM1[0] == "1 Hard carry" and PLAYER_SCENES_TEAM2[4] == "2 Hard support"
    assert PLAYER_SCENES == PLAYER_SCENES_TEAM1 + PLAYER_SCENES_TEAM2
    assert len(PLAYER_SCENES) == 10
    assert DEFAULT_MAIN_SCENE == "Juego"


def test_filtros_y_nombres_de_fuente():
    assert HUD_FILTERS == {4: "H 4 habilidades", 5: "H 5 habilidades", 6: "H 6 habilidades"}
    assert MOVE_FILTER_KIND == "move_source_filter"
    assert source_name("Camara", "1 Hard carry") == "Camara · 1 Hard carry"
    assert source_name("Nombre", "2 Offlaner") == "Nombre · 2 Offlaner"
