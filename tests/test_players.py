from overpower_cams.players import PlayerConfig, TeamsConfig, effective_use


def test_valores_por_defecto():
    assert PlayerConfig() == PlayerConfig("", "", "", "camera")
    assert TeamsConfig() == TeamsConfig("", "")


def test_effective_use_los_4_casos():
    assert effective_use(PlayerConfig(camera_url="c", photo_url="f", use="camera")) == "camera"
    assert effective_use(PlayerConfig(camera_url="c", photo_url="f", use="photo")) == "photo"
    # Una selección vacía no muestra la fuente alternativa.
    assert effective_use(PlayerConfig(photo_url="f", use="camera")) is None
    assert effective_use(PlayerConfig(camera_url="c", use="photo")) is None
    assert effective_use(PlayerConfig(camera_url="c", photo_url="  ", use="photo")) is None
    # ninguna
    assert effective_use(PlayerConfig(use="photo")) is None
