"""Pruebas de overpower_cams.paths (con tmp_path, sin tocar Steam/Dota reales)."""
import os
from pathlib import Path

from overpower_cams import paths
from overpower_cams.config import APP_DIR_NAME, GSI_CFG_NAME


def _vdf(*libs):
    entries = "\n".join(
        f'\t"{i}"\n\t{{\n\t\t"path"\t\t"{p}"\n\t\t"label"\t\t""\n\t}}'
        for i, p in enumerate(libs)
    )
    return f'"libraryfolders"\n{{\n{entries}\n}}\n'


def _steam_con_vdf(tmp_path, *libs):
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    (steam / "steamapps" / "libraryfolders.vdf").write_text(_vdf(*libs), encoding="utf-8")
    return steam


def test_libraries_lee_rutas_escapadas(tmp_path):
    steam = _steam_con_vdf(
        tmp_path,
        r"C:\Program Files (x86)\Steam",
        r"D:\SteamLibrary",
    )
    libs = paths.steam_libraries(steam)
    assert Path("C:/Program Files (x86)/Steam") in libs
    assert Path("D:/SteamLibrary") in libs
    assert steam in libs


def test_libraries_sin_vdf_incluye_steam(tmp_path):
    assert paths.steam_libraries(tmp_path) == [tmp_path]


def test_find_dota_en_segunda_biblioteca(tmp_path):
    lib2 = tmp_path / "Biblioteca_Título"
    (lib2 / "steamapps").mkdir(parents=True)
    (lib2 / "steamapps" / "appmanifest_570.acf").write_text("x", encoding="utf-8")
    steam = _steam_con_vdf(tmp_path, str(tmp_path / "Steam").replace("\\", "\\\\"),
                           str(lib2).replace("\\", "\\\\"))
    assert paths.find_dota(steam) == lib2 / "steamapps" / "common" / "dota 2 beta"


def test_find_dota_no_instalado(tmp_path):
    steam = _steam_con_vdf(tmp_path, str(tmp_path / "Steam").replace("\\", "\\\\"))
    assert paths.find_dota(steam) is None
    assert paths.find_dota(None) is None


def test_keys_file_cuenta_mas_reciente(tmp_path):
    steam = tmp_path / "Steam"
    archivos = []
    for cuenta in ("111", "222"):
        cfg = steam / "userdata" / cuenta / "570" / "remote" / "cfg"
        cfg.mkdir(parents=True)
        f = cfg / "dotakeys_personal.lst"
        f.write_text("x", encoding="utf-8")
        archivos.append(f)
    os.utime(archivos[0].parent, (1_000_000, 1_000_000))
    os.utime(archivos[1].parent, (2_000_000, 2_000_000))
    assert paths.dota_keys_file(steam) == archivos[1]


def test_keys_file_sin_steam_o_sin_archivos(tmp_path):
    assert paths.dota_keys_file(None) is None
    assert paths.dota_keys_file(tmp_path) is None


def test_gsi_cfg_path(tmp_path):
    p = paths.gsi_cfg_path(tmp_path / "dota 2 beta")
    assert p.name == GSI_CFG_NAME
    assert p.as_posix().endswith(
        "game/dota/cfg/gamestate_integration/gamestate_integration_obs.cfg"
    )


def test_app_data_dir_usa_appdata_y_se_crea(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = paths.app_data_dir()
    assert d == tmp_path / APP_DIR_NAME
    assert d.is_dir()


def test_is_running_detecta_y_no_falla(monkeypatch):
    class R:
        stdout = "Nombre de imagen   PID\ndota2.exe   123\n"

    llamadas = {}

    def fake_run(cmd, **kw):
        llamadas["cmd"] = cmd
        llamadas["kw"] = kw
        return R()

    monkeypatch.setattr(paths.subprocess, "run", fake_run)
    assert paths.is_running("dota2.exe") is True
    assert paths.is_running("obs64.exe") is False
    assert llamadas["kw"]["creationflags"] == paths.subprocess.CREATE_NO_WINDOW


def test_is_running_false_si_tasklist_falla(monkeypatch):
    def boom(*a, **k):
        raise OSError("sin tasklist")

    monkeypatch.setattr(paths.subprocess, "run", boom)
    assert paths.is_running("dota2.exe") is False


def test_resource_path_sin_empaquetar_es_la_raiz_del_repo():
    raiz = Path(__file__).resolve().parent.parent
    assert paths.resource_path("assets/Borde.png") == raiz / "assets" / "Borde.png"
    assert paths.resource_path("assets/Borde.png").is_file()


def test_resource_path_empaquetado_usa_meipass(tmp_path, monkeypatch):
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("assets/Borde.png") == tmp_path / "assets" / "Borde.png"


# ---------- cuenta de Steam activa (valores sintéticos, nunca el registro real) ----------

ID64_BASE = 76561197960265728


def _cuentas(tmp_path, *cuentas, con_570=True):
    """Steam falso con userdata/<cuenta>; devuelve (steam, {cuenta: archivo de teclas})."""
    steam = tmp_path / "Steam"
    out = {}
    for cuenta in cuentas:
        base = steam / "userdata" / cuenta
        base.mkdir(parents=True)
        if con_570:
            cfg = base / "570" / "remote" / "cfg"
            cfg.mkdir(parents=True)
            f = cfg / "dotakeys_personal.lst"
            f.write_text("x", encoding="utf-8")
            out[cuenta] = f
    return steam, out


def _loginusers(steam, usuarios):
    """`usuarios`: lista de (accountid, campos extra) para config/loginusers.vdf."""
    bloques = []
    for cuenta, extra in usuarios:
        campos = "".join(f'\t\t"{k}"\t\t"{v}"\n' for k, v in extra.items())
        bloques.append(f'\t"{ID64_BASE + int(cuenta)}"\n\t{{\n\t\t"AccountName"\t\t"prueba"\n'
                       f'{campos}\t}}\n')
    (steam / "config").mkdir(parents=True, exist_ok=True)
    (steam / "config" / "loginusers.vdf").write_text('"users"\n{\n' + "".join(bloques) + "}\n",
                                                     encoding="utf-8")


def test_cuenta_activa_del_registro_gana_a_la_mas_reciente(tmp_path, monkeypatch):
    steam, files = _cuentas(tmp_path, "111", "222")
    os.utime(files["111"].parent, (1_000_000, 1_000_000))
    os.utime(files["222"].parent, (2_000_000, 2_000_000))
    monkeypatch.setattr(paths, "_read_active_user", lambda: 111)
    assert paths.steam_account_id(steam) == "111"
    assert paths.dota_keys_file(steam) == files["111"]


def test_registro_en_cero_usa_loginusers_most_recent(tmp_path, monkeypatch):
    steam, files = _cuentas(tmp_path, "111", "222")
    os.utime(files["111"].parent, (2_000_000, 2_000_000))   # la de mtime sería 111
    monkeypatch.setattr(paths, "_read_active_user", lambda: 0)
    _loginusers(steam, [("111", {"MostRecent": "0", "timestamp": "9"}),
                        ("222", {"MostRecent": "1", "timestamp": "1"})])
    assert paths.steam_account_id(steam) == "222"
    assert paths.dota_keys_file(steam) == files["222"]


def test_loginusers_sin_most_recent_usa_el_timestamp_mas_alto(tmp_path):
    steam, files = _cuentas(tmp_path, "111", "222")
    os.utime(files["222"].parent, (2_000_000, 2_000_000))
    _loginusers(steam, [("111", {"timestamp": "1700000500"}),
                        ("222", {"timestamp": "1700000100"})])
    assert paths.steam_account_id(steam) == "111"
    assert paths.dota_keys_file(steam) == files["111"]


def test_cuenta_del_registro_sin_carpeta_cae_a_loginusers_y_luego_a_mtime(tmp_path, monkeypatch):
    steam, files = _cuentas(tmp_path, "111", "222")
    os.utime(files["111"].parent, (1_000_000, 1_000_000))
    os.utime(files["222"].parent, (2_000_000, 2_000_000))
    monkeypatch.setattr(paths, "_read_active_user", lambda: 999)     # no tiene userdata
    assert paths.dota_keys_file(steam) == files["222"]              # mtime
    _loginusers(steam, [("111", {"MostRecent": "1"})])
    assert paths.dota_keys_file(steam) == files["111"]


def test_cuenta_activa_sin_carpeta_570_no_usa_otra_cuenta(tmp_path, monkeypatch):
    steam, files = _cuentas(tmp_path, "111")
    (steam / "userdata" / "333").mkdir()                            # nunca abrió Dota
    monkeypatch.setattr(paths, "_read_active_user", lambda: 333)
    assert paths.steam_account_id(steam) == "333"
    assert paths.dota_keys_file(steam) is None


def test_loginusers_roto_o_raro_no_falla(tmp_path):
    steam, files = _cuentas(tmp_path, "111")
    (steam / "config").mkdir()
    (steam / "config" / "loginusers.vdf").write_bytes(b'\xff\xfe"users" { "abc" { } "12" { }')
    assert paths.steam_account_id(steam) == "111"     # solo queda el respaldo por mtime
    assert paths.dota_keys_file(steam) == files["111"]


def test_steam_account_id_sin_steam_o_sin_userdata(tmp_path):
    assert paths.steam_account_id(None) is None
    assert paths.steam_account_id(tmp_path) is None


def test_read_active_user_nunca_lanza(monkeypatch):
    def boom(*a, **k):
        raise OSError("sin clave")
    monkeypatch.setattr(paths.winreg, "OpenKey", boom)
    assert paths._read_active_user_registry() is None


def test_rutas_de_autoexec_y_teclas_por_defecto(tmp_path):
    dota = tmp_path / "dota 2 beta"
    assert paths.autoexec_path(dota) == dota / "game" / "dota" / "cfg" / "autoexec.cfg"
    assert paths.user_keys_default_path(dota) == dota / "game" / "dota" / "cfg" / "user_keys_default.vcfg"
