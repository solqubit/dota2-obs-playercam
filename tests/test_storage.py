import json
from pathlib import Path

import pytest

from overpower_cams.config import PLAYER_SCENES
from overpower_cams.players import PlayerConfig, TeamsConfig
from overpower_cams.storage import LiveState, Settings, Storage


def test_settings_ida_y_vuelta(tmp_path):
    st = Storage(tmp_path)
    s = Settings(obs_port=4460, obs_password="x", dota_dir="D:/dota")
    st.save_settings(s)
    assert st.load_settings() == s


def test_estado_por_defecto_usa_bando_inicial(tmp_path):
    assert Storage(tmp_path).load_state(2) == LiveState(2, "auto")


def test_estado_recuerda_swap_y_ocultar(tmp_path):
    st = Storage(tmp_path)
    st.save_state(LiveState(2, "hidden"))
    assert st.load_state(1) == LiveState(2, "hidden")


def test_importa_input_map_viejo(tmp_path):
    legacy = tmp_path / "input_map.json"
    legacy.write_text(json.dumps({"portraits": {"r1": [-0.34, 0.017, 4]}}), encoding="utf-8")
    base = tmp_path / "datos"
    st = Storage(base)
    assert st.load_portraits(legacy) == {"r1": [-0.34, 0.017, 4]}
    assert (base / "portraits.json").exists()
    # portraits.json gana sobre el legado
    legacy.write_text(json.dumps({"portraits": {"r2": [0, 0, 1]}}), encoding="utf-8")
    assert st.load_portraits(legacy) == {"r1": [-0.34, 0.017, 4]}


def test_portraits_sin_nada(tmp_path):
    assert Storage(tmp_path).load_portraits(None) == {}
    assert Storage(tmp_path).load_portraits(tmp_path / "no_existe.json") == {}


def test_portraits_ida_y_vuelta(tmp_path):
    st = Storage(tmp_path)
    st.save_portraits({"d3": [0.1, 0.2, 2]})
    assert st.load_portraits(None) == {"d3": [0.1, 0.2, 2]}
    raw = json.loads((tmp_path / "portraits.json").read_text(encoding="utf-8"))
    assert raw == {"portraits": {"d3": [0.1, 0.2, 2]}}


def test_json_roto_no_rompe(tmp_path):
    (tmp_path / "settings.json").write_text("{esto no es json", encoding="utf-8")
    (tmp_path / "state.json").write_text("[[[", encoding="utf-8")
    (tmp_path / "portraits.json").write_text("nope", encoding="utf-8")
    st = Storage(tmp_path)
    assert st.load_settings() == Settings()
    assert st.load_state(2) == LiveState(2, "auto")
    assert st.load_portraits(None) == {}


def test_claves_invalidas_usan_defaults(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({"obs_port": "abc", "otra": 1, "default_radiant_team": 3}), encoding="utf-8")
    (tmp_path / "state.json").write_text(
        json.dumps({"radiant_team": 7, "mode": "raro"}), encoding="utf-8")
    st = Storage(tmp_path)
    assert st.load_settings() == Settings()
    assert st.load_state(2) == LiveState(2, "auto")


def test_unicode_sin_escapar(tmp_path):
    st = Storage(tmp_path)
    st.save_settings(Settings(obs_password="contraseña"))
    assert "contraseña" in (tmp_path / "settings.json").read_text(encoding="utf-8")


def test_backup_con_fecha(tmp_path):
    src = tmp_path / "dota_keys.cfg"
    src.write_text("bind x y", encoding="utf-8")
    st = Storage(tmp_path / "datos")
    dst = st.backup(src)
    assert dst.exists()
    assert dst.parent == tmp_path / "datos" / "backups"
    assert dst.read_text(encoding="utf-8") == "bind x y"
    assert dst.name.startswith("dota_keys_") and dst.suffix == ".cfg"


def test_settings_idioma_ida_y_vuelta(tmp_path):
    st = Storage(tmp_path)
    assert st.load_settings().language is None          # sin archivo: el idioma de Windows
    for code in ("en", "es"):
        st.save_settings(Settings(language=code))
        assert st.load_settings().language == code
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["language"] == "es"


def test_settings_idioma_invalido_queda_en_none(tmp_path):
    for malo in ("fr", "", 1, None, ["es"]):
        (tmp_path / "settings.json").write_text(json.dumps({"language": malo, "obs_port": 4460}),
                                                encoding="utf-8")
        s = Storage(tmp_path).load_settings()
        assert s.language is None and s.obs_port == 4460


def test_settings_v1_sin_main_scene_carga_juego(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({"obs_port": 4455, "obs_password": "", "default_radiant_team": 1}), encoding="utf-8")
    assert Storage(tmp_path).load_settings().main_scene == "Juego"


def test_main_scene_ida_y_vuelta(tmp_path):
    st = Storage(tmp_path)
    st.save_settings(Settings(main_scene="Otra"))
    assert st.load_settings().main_scene == "Otra"
    (tmp_path / "settings.json").write_text(json.dumps({"main_scene": 5}), encoding="utf-8")
    assert st.load_settings().main_scene == "Juego"


def test_jugadores_por_defecto_son_10(tmp_path):
    d = Storage(tmp_path).load_players()
    assert list(d) == PLAYER_SCENES
    assert all(p == PlayerConfig() for p in d.values())
    assert Storage(tmp_path).load_teams() == TeamsConfig()


def test_players_json_ida_y_vuelta(tmp_path):
    st = Storage(tmp_path)
    d = st.load_players()
    d["1 Mid laner"] = PlayerConfig("Ana", "rtmp://x", "C:/f.png", "photo")
    st.save_players(d)
    st.save_teams(TeamsConfig("Alfa", "Beta"))
    st2 = Storage(tmp_path)
    assert st2.load_players() == d
    assert st2.load_teams() == TeamsConfig("Alfa", "Beta")
    raw = json.loads((tmp_path / "players.json").read_text(encoding="utf-8"))
    assert raw["teams"] == {"team1": "Alfa", "team2": "Beta"}
    assert raw["players"]["1 Mid laner"]["use"] == "photo"


def test_players_json_roto_da_defaults(tmp_path):
    (tmp_path / "players.json").write_text("{no json", encoding="utf-8")
    st = Storage(tmp_path)
    assert st.load_players() == {s: PlayerConfig() for s in PLAYER_SCENES}
    assert st.load_teams() == TeamsConfig()


def test_players_json_incompleto_o_invalido(tmp_path):
    (tmp_path / "players.json").write_text(json.dumps({
        "teams": {"team1": 3, "team2": "B"},
        "players": {"1 Hard carry": {"name": "Z", "camera_url": 7, "use": "otra"},
                    "Desconocida": {"name": "Q"}, "2 Offlaner": "x"},
    }), encoding="utf-8")
    st = Storage(tmp_path)
    d = st.load_players()
    assert list(d) == PLAYER_SCENES
    assert d["1 Hard carry"] == PlayerConfig(name="Z")
    assert d["2 Offlaner"] == PlayerConfig()
    assert st.load_teams() == TeamsConfig("", "B")


def test_settings_v1_sin_host_ni_modo_inicial_usan_los_de_siempre(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({"obs_port": 4455, "obs_password": "", "default_radiant_team": 1}), encoding="utf-8")
    s = Storage(tmp_path).load_settings()
    assert s.obs_host == "127.0.0.1" and s.default_mode == "auto"


def test_host_y_modo_inicial_ida_y_vuelta(tmp_path):
    st = Storage(tmp_path)
    st.save_settings(Settings(obs_host="192.168.0.10", default_mode="hidden"))
    s = st.load_settings()
    assert (s.obs_host, s.default_mode) == ("192.168.0.10", "hidden")
    (tmp_path / "settings.json").write_text(json.dumps({"obs_host": " ", "default_mode": "x"}),
                                            encoding="utf-8")
    s = st.load_settings()
    assert (s.obs_host, s.default_mode) == ("127.0.0.1", "auto")


def test_estado_sin_guardar_usa_el_modo_inicial(tmp_path):
    assert Storage(tmp_path).load_state(2, "hidden") == LiveState(2, "hidden")


# ---------- jugadores en memoria (para el hilo de OBS) ----------

def test_snapshot_de_jugadores_sigue_a_lo_guardado_sin_releer_el_archivo(tmp_path, monkeypatch):
    st = Storage(tmp_path)
    d = st.load_players()
    d["1 Mid laner"] = PlayerConfig("SumaiL", "http://cam", "", "camera")
    st.save_players(d)
    d["1 Mid laner"].name = "mutado después"          # el snapshot es una copia

    def no_leer(path):
        raise AssertionError("el snapshot no debe leer el disco")
    monkeypatch.setattr(st, "_read_json", no_leer)
    snap = st.players_snapshot()
    assert snap["1 Mid laner"] == PlayerConfig("SumaiL", "http://cam", "", "camera")
    assert set(snap) == set(PLAYER_SCENES)


def test_snapshot_no_cambia_si_guardar_falla(tmp_path, monkeypatch):
    import pytest
    from overpower_cams import storage as storage_mod
    st = Storage(tmp_path)
    st.save_players({"1 Hard carry": PlayerConfig("A")})

    def falla(src, dst):
        raise OSError("disco lleno")
    monkeypatch.setattr(storage_mod.os, "replace", falla)
    with pytest.raises(OSError):
        st.save_players({"1 Hard carry": PlayerConfig("B")})
    assert st.players_snapshot()["1 Hard carry"].name == "A"


def test_snapshot_no_se_borra_si_players_json_no_se_puede_leer(tmp_path):
    st = Storage(tmp_path)
    st.save_players({"1 Hard carry": PlayerConfig("A")})
    (tmp_path / "players.json").write_text("{a medio escribir", encoding="utf-8")
    assert st.load_players()["1 Hard carry"].name == "A"
    assert st.players_snapshot()["1 Hard carry"].name == "A"


def test_escritura_reintenta_si_windows_tiene_el_archivo_abierto(tmp_path, monkeypatch):
    from overpower_cams import storage as storage_mod
    real, intentos = storage_mod.os.replace, []

    def ocupado(src, dst):
        intentos.append(dst)
        if len(intentos) < 3:
            raise PermissionError(13, "El proceso no tiene acceso al archivo")
        return real(src, dst)
    monkeypatch.setattr(storage_mod.os, "replace", ocupado)
    monkeypatch.setattr(storage_mod.time, "sleep", lambda s: None)
    st = Storage(tmp_path)
    st.save_players({"1 Hard carry": PlayerConfig("A")})
    assert len(intentos) == 3
    assert Storage(tmp_path).load_players()["1 Hard carry"].name == "A"
    assert not list(tmp_path.glob("*.tmp"))


def test_escritura_se_rinde_si_el_archivo_sigue_ocupado(tmp_path, monkeypatch):
    import pytest
    from overpower_cams import storage as storage_mod
    intentos = []

    def ocupado(src, dst):
        intentos.append(dst)
        raise PermissionError(13, "ocupado")
    monkeypatch.setattr(storage_mod.os, "replace", ocupado)
    monkeypatch.setattr(storage_mod.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        Storage(tmp_path).save_teams(TeamsConfig("A", "B"))
    assert len(intentos) == storage_mod.REPLACE_TRIES
    assert not list(tmp_path.glob("*.tmp"))


def test_retratos_ajustes_y_estado_no_reintentan_ni_esperan(tmp_path, monkeypatch):
    """save_portraits corre con el lock del motor: falla al momento, sin dormir."""
    import pytest
    from overpower_cams import storage as storage_mod
    intentos = []

    def ocupado(src, dst):
        intentos.append(dst)
        raise PermissionError(13, "ocupado")

    def no_dormir(s):
        raise AssertionError("no debe esperar")
    monkeypatch.setattr(storage_mod.os, "replace", ocupado)
    monkeypatch.setattr(storage_mod.time, "sleep", no_dormir)
    st = Storage(tmp_path)
    for guardar in (lambda: st.save_portraits({"r1": [0.0, 0.0, 1]}),
                    lambda: st.save_settings(Settings()),
                    lambda: st.save_state(LiveState(1, "auto"))):
        with pytest.raises(PermissionError):
            guardar()
    assert len(intentos) == 3


@pytest.mark.parametrize("section", ["players", "teams"])
@pytest.mark.parametrize("unreadable", [True, False])
def test_guardar_no_borra_la_otra_seccion_si_no_puede_leer(tmp_path, monkeypatch, section, unreadable):
    st = Storage(tmp_path)
    st.save_teams(TeamsConfig("A", "B"))
    st.save_players({"1 Hard carry": PlayerConfig("Player A", "https://example.com/cam")})
    path = tmp_path / "players.json"
    if unreadable:
        monkeypatch.setattr(st, "_read_json", lambda path: None)
    else:
        path.write_text("{incompleto", encoding="utf-8")
    before = path.read_bytes()
    snapshot = st.players_snapshot()
    with pytest.raises(OSError, match="se conserva el archivo"):
        if section == "players":
            st.save_players({"1 Hard carry": PlayerConfig("Otro")})
        else:
            st.save_teams(TeamsConfig("Otro", ""))
    assert path.read_bytes() == before
    assert st.players_snapshot() == snapshot
    assert not list(tmp_path.glob("*.tmp"))
