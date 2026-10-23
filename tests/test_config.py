from overpower_cams.config import (
    CAMERAS_TEAM1, CAMERAS_TEAM2, COMPANIONS, GSI_CFG_TEXT, PORTRAIT_PITCH,
)


def test_constantes_del_spec():
    assert len(CAMERAS_TEAM1 + CAMERAS_TEAM2) == 10
    assert COMPANIONS == ["Borde", "Marco"]
    assert '"uri"           "http://127.0.0.1:3000/"' in GSI_CFG_TEXT
    assert '"throttle"      "0.01"' in GSI_CFG_TEXT
    assert round(PORTRAIT_PITCH * 1080) == 62


def test_gsi_pide_habilidades():
    assert '"abilities"     "1"' in GSI_CFG_TEXT
