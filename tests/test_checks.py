"""Revisiones y arreglos (checks.py). Todo con tmp_path y fakes: nada toca Steam/Dota/OBS reales."""
from pathlib import Path

import pytest

from overpower_cams import checks, config, gsi_cfg, paths
from overpower_cams.checks import CheckResult, Context, FixRefused, apply_fix, run_checks
from overpower_cams.dota_keys import fix_keys_text, missing_slots, parse_player_keys
from overpower_cams.obs_link import ObsLink
from overpower_cams.portraits import PortraitModel
from overpower_cams.storage import Settings, Storage
from conftest import FakeObsClient, filtros_camaraman, layout_camaraman, layout_nuevo

DATA = Path(__file__).parent / "data" / "dotakeys_ejemplo.lst"
IDS = ["dota", "gsi_cfg", "gsi_data", "keys", "obs", "scene", "companion_images", "portraits"]
NOW = 1000.0


def CERRADO(exe):
    return False


def ABIERTO(exe):
    return True


def make_ctx(tmp_path, fake=None, *, connect=True, last_post_t=NOW - 1, with_keys=True,
             with_cfg=True, portraits=None):
    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True, exist_ok=True)
    if with_cfg:
        gsi_cfg.write_cfg(paths.gsi_cfg_path(dota))
    keys_file = None
    if with_keys:
        keys_file = tmp_path / "steam" / "userdata" / "1" / "570" / "remote" / "cfg" / "dotakeys_personal.lst"
        keys_file.parent.mkdir(parents=True, exist_ok=True)
        keys_file.write_bytes(DATA.read_bytes())
    fake = fake or FakeObsClient(layout_nuevo(), inputs={"Borde": {"file": str(tmp_path / "x.png")}})
    obs = ObsLink("127.0.0.1", 4455, "pw", client_factory=fake.factory)
    if connect:
        obs.connect()
    assets = tmp_path / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "Borde.png").write_bytes(b"png")
    ctx = Context(storage=Storage(tmp_path / "data"), settings=Settings(), steam=tmp_path / "steam",
                  dota=dota, keys_file=keys_file, obs=obs, last_post_t=last_post_t, now=NOW,
                  assets_dir=assets, portraits=PortraitModel(portraits))
    return ctx, fake


def by_id(results):
    return {r.id: r for r in results}


def check(ctx, cid, **kw):
    kw.setdefault("is_running", CERRADO)
    return by_id(run_checks(ctx, **kw))[cid]


def make_images_ok(fake, tmp_path):
    for n in ("Borde", "Marco"):
        p = tmp_path / f"{n}.png"
        p.write_bytes(b"png")
        fake.inputs[n] = {"file": str(p)}


# ---------- general ----------

def test_orden_e_ids_y_todo_ok(tmp_path):
    ctx, fake = make_ctx(tmp_path)
    make_images_ok(fake, tmp_path)
    ctx.keys_file.write_bytes(fix_keys_text(DATA.read_text(newline="")).encode())
    res = run_checks(ctx, is_running=CERRADO)
    assert [r.id for r in res] == IDS
    assert all(isinstance(r, CheckResult) for r in res)
    assert [r.status for r in res] == ["ok"] * 8, [(r.id, r.status, r.detail) for r in res]


def test_run_checks_no_modifica_nada(tmp_path):
    ctx, fake = make_ctx(tmp_path, with_cfg=False)
    before_keys = ctx.keys_file.read_bytes()
    fake.calls.clear()
    run_checks(ctx, is_running=CERRADO)
    assert ctx.keys_file.read_bytes() == before_keys
    assert not paths.gsi_cfg_path(ctx.dota).exists()
    assert not (ctx.storage.base / "backups").exists()
    assert fake.calls == [] and fake.created == []
    assert fake.inputs["Borde"] == {"file": str(tmp_path / "x.png")}


def test_run_checks_no_apaga_la_escena_al_aire_en_obs(tmp_path):
    """Revisar no puede cambiar lo que sale al aire (load_items apagaría todo)."""
    fake = FakeObsClient(layout_nuevo(), scenes=layout_camaraman(), filters=filtros_camaraman())
    ctx, _ = make_ctx(tmp_path, fake)
    ctx.obs.load_items()
    ctx.obs.apply("1 Hard carry", "test")
    fake.ops.clear()
    run_checks(ctx, is_running=CERRADO)
    assert fake.ops == []
    assert fake.is_enabled("1 Hard carry", "Juego") is True


def test_una_revision_que_falla_no_tumba_a_las_demas(tmp_path, monkeypatch):
    ctx, _ = make_ctx(tmp_path)

    def boom(path):
        raise RuntimeError("se rompió")
    monkeypatch.setattr(checks.gsi_cfg, "cfg_status", boom)
    res = by_id(run_checks(ctx, is_running=CERRADO))
    assert list(res) == IDS
    assert res["gsi_cfg"].status == "error" and "se rompió" in res["gsi_cfg"].detail
    assert res["dota"].status == "ok"


# ---------- dota ----------

def test_dota_ok_y_no_encontrado(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    r = check(ctx, "dota")
    assert r.status == "ok" and str(ctx.dota) in r.detail
    ctx.dota = None
    r = check(ctx, "dota")
    assert r.status == "error" and "No encontré Dota" in r.detail and r.fix_label == "Buscar…"


def test_carpeta_sin_game_dota_no_es_dota_y_no_se_arregla_el_gsi(tmp_path):
    ctx, _ = make_ctx(tmp_path, with_cfg=False)
    cualquiera = tmp_path / "Documentos"
    cualquiera.mkdir()
    ctx.dota = cualquiera
    r = check(ctx, "dota")
    assert r.status == "error" and r.fix_label == "Buscar…"
    assert "Esa carpeta no parece ser Dota 2 (falta game" in r.detail
    with pytest.raises(FixRefused):
        apply_fix("gsi_cfg", ctx, is_running=CERRADO)
    assert list(cualquiera.iterdir()) == []          # no creó carpetas en cualquier lado


# ---------- gsi_cfg ----------

def test_gsi_cfg_falta_carpeta(tmp_path):
    ctx, _ = make_ctx(tmp_path, with_cfg=False)
    assert not paths.gsi_cfg_path(ctx.dota).parent.exists()
    r = check(ctx, "gsi_cfg")
    assert r.status == "error" and r.fix_label == "Arreglar"
    msg = apply_fix("gsi_cfg", ctx, is_running=CERRADO)
    assert "Reinicia Dota" not in msg
    assert check(ctx, "gsi_cfg").status == "ok"


def test_gsi_cfg_distinto_se_respalda_y_avisa_si_dota_abierto(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cfg = paths.gsi_cfg_path(ctx.dota)
    cfg.write_text('"otra cosa" { }', encoding="utf-8")
    r = check(ctx, "gsi_cfg")
    assert r.status == "error" and r.fix_label == "Arreglar"
    msg = apply_fix("gsi_cfg", ctx, is_running=ABIERTO)
    assert "Reinicia Dota para que lo lea" in msg
    assert check(ctx, "gsi_cfg").status == "ok"
    copias = list((ctx.storage.base / "backups").iterdir())
    assert len(copias) == 1 and copias[0].read_text(encoding="utf-8") == '"otra cosa" { }'


def test_gsi_cfg_sin_dota_se_niega(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    ctx.dota = None
    assert check(ctx, "gsi_cfg").status == "error"
    with pytest.raises(FixRefused):
        apply_fix("gsi_cfg", ctx, is_running=CERRADO)


# ---------- gsi_data ----------

def test_gsi_data_estados(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    ctx.last_post_t = ctx.now - 1
    assert check(ctx, "gsi_data").status == "ok"
    ctx.last_post_t = ctx.now - config.GSI_STALE_S
    assert check(ctx, "gsi_data").status == "ok"
    ctx.last_post_t = None
    r = check(ctx, "gsi_data", is_running=CERRADO)
    assert r.status == "warn" and "Abre Dota y entra a una partida" in r.detail
    r = check(ctx, "gsi_data", is_running=ABIERTO)
    assert r.status == "error" and "-gamestateintegration" in (r.instructions or "")
    ctx.last_post_t = ctx.now - 60
    assert check(ctx, "gsi_data", is_running=ABIERTO).status == "error"


# ---------- keys ----------

def test_keys_faltan_y_enlace(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    r = check(ctx, "keys")
    assert r.status == "error" and r.fix_label == "Arreglar"
    assert "Radiant 1" in r.detail
    # teclas completas pero con el enlace activado -> amarillo
    arreglado = fix_keys_text(DATA.read_text(newline=""))
    assert '"LinkPlayerToSpectator"\t\t"0"' in arreglado
    ctx.keys_file.write_bytes(arreglado.replace(
        '"LinkPlayerToSpectator"\t\t"0"', '"LinkPlayerToSpectator"\t\t"1"').encode())
    assert missing_slots(parse_player_keys(ctx.keys_file.read_text())) == []
    r = check(ctx, "keys")
    assert r.status == "warn" and r.fix_label == "Arreglar"


def test_keys_sin_archivo(tmp_path):
    ctx, _ = make_ctx(tmp_path, with_keys=False)
    r = check(ctx, "keys")
    assert r.status == "warn" and r.fix_label is None
    with pytest.raises(FixRefused):
        apply_fix("keys", ctx, is_running=CERRADO)


def test_keys_con_dota_abierto_se_niega(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    antes = ctx.keys_file.read_bytes()
    with pytest.raises(FixRefused, match="Cierra Dota por completo y vuelve a intentar"):
        apply_fix("keys", ctx, is_running=lambda exe: exe == "dota2.exe")
    assert ctx.keys_file.read_bytes() == antes
    assert not (ctx.storage.base / "backups").exists()


def test_keys_arreglo_hace_backup(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    antes = ctx.keys_file.read_bytes()
    msg = apply_fix("keys", ctx, is_running=CERRADO)
    copias = list((ctx.storage.base / "backups").iterdir())
    assert len(copias) == 1 and copias[0].read_bytes() == antes
    assert missing_slots(parse_player_keys(ctx.keys_file.read_text())) == []
    assert "local" in msg and "Steam" in msg
    assert check(ctx, "keys").status == "ok"


def test_keys_arreglo_conserva_crlf(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    ctx.keys_file.write_bytes(DATA.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    apply_fix("keys", ctx, is_running=CERRADO)
    data = ctx.keys_file.read_bytes()
    assert b"\r\n" in data and data.count(b"\n") == data.count(b"\r\n")


# ---------- obs ----------

def test_obs_estados(tmp_path):
    fake = FakeObsClient(layout_nuevo())
    ctx, _ = make_ctx(tmp_path, fake, connect=False)
    fake.connect_error = ConnectionRefusedError()
    ctx.obs.connect()
    r = check(ctx, "obs")
    assert r.status == "error" and "Ajustes del servidor WebSocket" in (r.instructions or "")
    ctx.obs.error = "auth"
    r = check(ctx, "obs")
    assert r.status == "error" and "Contraseña incorrecta: cámbiala en Ajustes" in r.detail
    ctx.obs.password = ""
    r = check(ctx, "obs")
    assert r.status == "error" and "Falta la contraseña de OBS: escríbela en Ajustes" in r.detail
    assert "Contraseña incorrecta" not in r.detail
    ctx.obs.password = "pw"
    ctx.obs.error = "lost"
    r = check(ctx, "obs")
    assert r.status == "error" and "Se perdió la conexión con OBS — reintentando" in r.detail
    assert "Ajustes del servidor WebSocket" in (r.instructions or "")
    ctx.obs.error = "OSError: algo raro"
    assert "algo raro" in check(ctx, "obs").detail
    # sin OBS, la escena es error y las imágenes quedan sin revisar
    assert check(ctx, "scene").status == "error"
    assert check(ctx, "companion_images").status == "warn"
    fake.connect_error = None
    ctx.obs.connect()
    assert check(ctx, "obs").status == "ok"


def test_conexion_que_se_cae_durante_la_revision(tmp_path):
    ctx, fake = make_ctx(tmp_path)
    fake.fail_next = True
    res = by_id(run_checks(ctx, is_running=CERRADO))
    assert res["obs"].status == "error" and "Se perdió la conexión" in res["obs"].detail
    assert res["scene"].status == "error"


# ---------- scene ----------

def test_falta_camara_es_rojo_con_la_lista(tmp_path):
    layout = layout_nuevo()
    del layout["CAM_EQ1_3"], layout["CAM_EQ2_5"]
    ctx, _ = make_ctx(tmp_path, FakeObsClient(layout))
    r = check(ctx, "scene")
    assert r.status == "error" and r.fix_label is None
    assert "CAM_EQ1_3" in r.detail and "CAM_EQ2_5" in r.detail
    assert "Importar" in (r.instructions or "")


def test_escena_inexistente(tmp_path):
    ctx, _ = make_ctx(tmp_path, FakeObsClient(layout_nuevo(), scene_exists=False))
    r = check(ctx, "scene")
    assert r.status == "error" and config.SCENE_NAME in r.detail
    assert "Colección de escenas" in (r.instructions or "")
    with pytest.raises(FixRefused):
        apply_fix("scene", ctx)


def test_falta_marco_se_crea(tmp_path):
    ctx, fake = make_ctx(tmp_path, FakeObsClient(layout_nuevo(companions=("Borde",))))
    r = check(ctx, "scene")
    assert r.status == "warn" and r.fix_label == "Arreglar" and "Marco" in r.detail
    msg = apply_fix("scene", ctx)
    assert "Marco" in msg
    assert fake.created == [("Escena Dota", "Marco", "image_source", {}, False)]
    assert check(ctx, "scene").status == "ok"


def test_arreglar_escena_sin_conexion_se_niega(tmp_path):
    ctx, _ = make_ctx(tmp_path, FakeObsClient(layout_nuevo(companions=())), connect=False)
    with pytest.raises(FixRefused):
        apply_fix("scene", ctx)


# ---------- companion_images ----------

def test_borde_sin_imagen_se_arregla(tmp_path):
    ctx, fake = make_ctx(tmp_path)
    fake.inputs["Marco"] = {"file": str(tmp_path / "marco.png")}
    (tmp_path / "marco.png").write_bytes(b"png")
    r = check(ctx, "companion_images")
    assert r.status == "warn" and r.fix_label == "Arreglar" and "Borde" in r.detail
    apply_fix("companion_images", ctx)
    assert ctx.obs.get_image_path("Borde") == str(ctx.assets_dir / "Borde.png")
    assert check(ctx, "companion_images").status == "ok"


def test_marco_sin_imagen_ni_asset_no_tiene_arreglo(tmp_path):
    ctx, fake = make_ctx(tmp_path)
    p = tmp_path / "b.png"
    p.write_bytes(b"png")
    fake.inputs["Borde"] = {"file": str(p)}
    fake.inputs["Marco"] = {}
    r = check(ctx, "companion_images")
    assert r.status == "warn" and "Marco sin imagen asignada" in r.detail and r.fix_label is None
    assert "Marco.png" in r.instructions and str(ctx.assets_dir) in r.instructions
    with pytest.raises(FixRefused):
        apply_fix("companion_images", ctx)


def test_marco_con_asset_en_la_carpeta_de_la_app_se_arregla(tmp_path):
    ctx, fake = make_ctx(tmp_path)
    p = tmp_path / "b.png"
    p.write_bytes(b"png")
    fake.inputs["Borde"] = {"file": str(p)}
    fake.inputs["Marco"] = {}
    (ctx.assets_dir / "Marco.png").write_bytes(b"png")
    r = check(ctx, "companion_images")
    assert r.status == "warn" and r.fix_label == "Arreglar"
    apply_fix("companion_images", ctx)
    assert ctx.obs.get_image_path("Marco") == str(ctx.assets_dir / "Marco.png")
    assert ctx.obs.get_image_path("Borde") == str(p)      # el que ya estaba bien no se toca
    assert check(ctx, "companion_images").status == "ok"


def test_acompanante_ausente_no_se_revisa(tmp_path):
    ctx, _ = make_ctx(tmp_path, FakeObsClient(layout_nuevo(companions=())))
    assert check(ctx, "companion_images").status == "ok"


def test_borde_sin_copia_empaquetada_se_niega(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    (ctx.assets_dir / "Borde.png").unlink()
    with pytest.raises(FixRefused):
        apply_fix("companion_images", ctx)


# ---------- portraits ----------

def test_portraits(tmp_path):
    ctx, _ = make_ctx(tmp_path, portraits={"r1": [0.1, 0.03, 2], "d3": [0.2, 0.03, 1]})
    r = check(ctx, "portraits")
    assert r.status == "ok"
    assert r.detail == "Los 10 ubicados (2 afinados con tus clicks)"


def test_apply_fix_id_desconocido(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    for cid in ("dota", "nada"):
        with pytest.raises(FixRefused):
            apply_fix(cid, ctx)


# ---------- la escena cambia después de conectar ----------

def test_run_checks_ve_la_escena_importada_despues_de_conectar(tmp_path):
    fake = FakeObsClient(layout_nuevo(), scene_exists=False,
                         inputs={"Borde": {"file": str(tmp_path / "x.png")}})
    ctx, _ = make_ctx(tmp_path, fake)
    ctx.obs.load_items()                           # se conectó sin la escena
    fake.scene_exists = True                       # y luego la importaron
    assert check(ctx, "scene").status == "ok"
