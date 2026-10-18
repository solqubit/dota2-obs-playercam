import json
from pathlib import Path

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
