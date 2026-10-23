from overpower_cams.players import PlayerConfig, TeamsConfig, effective_use


def test_valores_por_defecto():
    assert PlayerConfig() == PlayerConfig("", "", "", "camera")
    assert TeamsConfig() == TeamsConfig("", "")


def test_effective_use_los_4_casos():
    assert effective_use(PlayerConfig(camera_url="c", photo_url="f", use="camera")) == "camera"
    assert effective_use(PlayerConfig(camera_url="c", photo_url="f", use="photo")) == "photo"
    # lo elegido no tiene URL: cae a lo otro
    assert effective_use(PlayerConfig(photo_url="f", use="camera")) == "photo"
    assert effective_use(PlayerConfig(camera_url="c", use="photo")) == "camera"
    # ninguna
    assert effective_use(PlayerConfig(use="photo")) is None
