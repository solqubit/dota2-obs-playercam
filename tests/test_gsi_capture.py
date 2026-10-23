"""Tests del script de captura de GSI (tools/gsi_capture.py)."""
import json
import urllib.request

import pytest

from overpower_cams.config import GSI_CFG_NAME, GSI_CFG_TEXT
from overpower_cams.storage import Storage
from tools import gsi_capture as capture_tool
from tools.gsi_capture import (Captura, DIAGNOSTIC_DATA_KEYS, cfg_pide_habilidades, config_con_unidades,
                               config_temporal_unidades, describir_seleccion, revisar_cfg)
from tests.conftest import gsi_payload


def _post(port, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/", data=json.dumps(payload).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read()


def test_guarda_cada_post_en_una_linea(tmp_path):
    salida = tmp_path / "captura.jsonl"
    payloads = [gsi_payload("r3"), {"provider": {"name": "Dota 2"}, "x": [1, 2]}]
    vistos = []
    with Captura(salida, port=0, on_post=lambda n, h: vistos.append((n, h))) as cap:
        for p in payloads:
            assert _post(cap.port, p) == b"OK"
    assert vistos[0][0] == 1 and vistos[0][1].startswith("npc_dota_hero_")
    assert vistos[1] == (2, None)
    lineas = salida.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2
    filas = [json.loads(l) for l in lineas]
    assert [f["data"] for f in filas] == payloads
    assert all(isinstance(f["t"], float) for f in filas)
    assert filas[0]["t"] <= filas[1]["t"]


def test_cfg_pide_habilidades():
    assert cfg_pide_habilidades(GSI_CFG_TEXT)
    assert not cfg_pide_habilidades(GSI_CFG_TEXT.replace('"abilities"     "1"', '"abilities" "0"'))
    assert cfg_pide_habilidades(GSI_CFG_TEXT.replace('"abilities"     "1"', '"abilities"\t"1"'))


def test_revisar_cfg_solo_escribe_si_responde_s(tmp_path):
    ruta = tmp_path / GSI_CFG_NAME
    ruta.write_text(GSI_CFG_TEXT.replace('"abilities"     "1"', '"abilities"     "0"'),
                    encoding="utf-8")
    viejo = ruta.read_text(encoding="utf-8")
    revisar_cfg(ruta, preguntar=lambda _: "n", decir=lambda _: None)
    assert ruta.read_text(encoding="utf-8") == viejo
    revisar_cfg(ruta, preguntar=lambda _: "s", decir=lambda _: None)
    assert ruta.read_text(encoding="utf-8") == GSI_CFG_TEXT


def test_revisar_cfg_no_pregunta_si_ya_pide_habilidades(tmp_path):
    ruta = tmp_path / GSI_CFG_NAME
    ruta.write_text(GSI_CFG_TEXT, encoding="utf-8")
    revisar_cfg(ruta, preguntar=lambda _: 1 / 0, decir=lambda _: None)


def test_demo_muestra_heroe_local_sin_inventar_seleccion():
    # Forma de la captura real de Lone Druid: hero es plano y no hay selected_unit.
    payload = {"hero": {"name": "npc_dota_hero_lone_druid", "level": 1}}
    status = describir_seleccion(payload)
    assert "héroe local: lone_druid" in status
    assert "selección no verificada" in status
    assert "héroe seleccionado" not in status


def test_observador_muestra_seleccion_o_ninguno():
    assert "héroe seleccionado: test2" in describir_seleccion(gsi_payload("r3"))
    assert "héroe seleccionado: ninguno" in describir_seleccion(gsi_payload(None))


def test_captura_guarda_formato_demo_intacto(tmp_path):
    salida = tmp_path / "demo.jsonl"
    payload = {"hero": {"name": "npc_dota_hero_lone_druid", "level": 1}}
    with Captura(salida, port=0) as cap:
        assert _post(cap.port, payload) == b"OK"
        assert "héroe local: lone_druid" in cap.status
    assert json.loads(salida.read_text())["data"] == payload


def test_cfg_ampliado_activa_todas_las_solicitudes_y_conserva_uri_auth_tiempos():
    import re

    nuevo = config_con_unidades(GSI_CFG_TEXT)
    assert cfg_pide_habilidades(nuevo)
    assert config_con_unidades(nuevo) == nuevo
    pattern = r'("data"\s*\{)([^{}]*)(\})'
    block = re.search(pattern, nuevo)
    settings = dict(re.findall(r'"([^"]+)"\s*"([^"]+)"', block[2]))
    assert len(DIAGNOSTIC_DATA_KEYS) == 16
    assert all(settings[key] == "1" for key in DIAGNOSTIC_DATA_KEYS)
    assert re.sub(pattern, '', nuevo) == re.sub(pattern, '', GSI_CFG_TEXT)


def test_cfg_ampliado_se_respalda_y_restaura_aun_con_interrupcion(tmp_path):
    path = tmp_path / GSI_CFG_NAME
    original = b'\xef\xbb\xbf' + GSI_CFG_TEXT.replace('\n', '\r\n').encode()
    path.write_bytes(original)
    with pytest.raises(KeyboardInterrupt):
        with config_temporal_unidades(path, Storage(tmp_path / "datos"), is_running=lambda _: False) as backup:
            assert backup.read_bytes() == original
            assert '"units" "1"' in path.read_text()
            raise KeyboardInterrupt
    assert path.read_bytes() == original


def test_cfg_ampliado_no_modifica_nada_si_dota_esta_abierto(tmp_path):
    path = tmp_path / GSI_CFG_NAME
    path.write_text(GSI_CFG_TEXT)
    with pytest.raises(RuntimeError, match="Cierra Dota"):
        with config_temporal_unidades(path, Storage(tmp_path / "datos"), is_running=lambda _: True):
            pytest.fail("No debe entrar")
    assert path.read_text() == GSI_CFG_TEXT
    assert not (tmp_path / "datos").exists()


def test_cfg_ampliado_no_pisa_cambios_externos(tmp_path):
    path = tmp_path / GSI_CFG_NAME
    path.write_text(GSI_CFG_TEXT)
    with pytest.raises(RuntimeError, match="No lo sobrescribí"):
        with config_temporal_unidades(path, Storage(tmp_path / "datos"), is_running=lambda _: False):
            path.write_text("Cambio externo")
    assert path.read_text() == "Cambio externo"


def test_cfg_ampliado_rechaza_formato_desconocido():
    with pytest.raises(ValueError):
        config_con_unidades('"data" { "anidado" {} }')


def test_captura_anota_solicitudes_y_distingue_las_secciones_recibidas(tmp_path):
    salida = tmp_path / "completa.jsonl"
    payload = {"hero": {}, "items": {}, "units": {}, "auth": {"token": "test"}}
    with Captura(salida, port=0, requested_sections=DIAGNOSTIC_DATA_KEYS) as cap:
        assert _post(cap.port, payload) == b"OK"
        assert cap.sections_seen == {"hero", "items", "units"}
        assert cap.unit_posts == 0   # la sección existe pero no informa unidades
    saved = json.loads(salida.read_text())
    assert saved["requested_data"] == list(DIAGNOSTIC_DATA_KEYS)
    assert saved["data"] == payload


@pytest.mark.parametrize("dota_running,extra_args", [(True, []), (False, ["--live"])])
def test_all_data_captura_en_vivo_sin_reiniciar_ni_modificar_cfg(
        tmp_path, monkeypatch, capsys, dota_running, extra_args):
    path = tmp_path / GSI_CFG_NAME
    path.write_text(GSI_CFG_TEXT)
    observed = {}

    class FakeCapture:
        count = 1
        unit_posts = 0
        sections_seen = {"hero", "abilities"}
        port = 3000

        def __init__(self, salida, **kwargs):
            observed.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def forbidden(*args, **kwargs):
        pytest.fail("La captura en vivo no debe revisar ni modificar el archivo GSI")

    def stop_capture(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(capture_tool.paths, "steam_path", lambda: None)
    monkeypatch.setattr(capture_tool.paths, "find_dota", lambda _: tmp_path)
    monkeypatch.setattr(capture_tool.paths, "is_running", lambda _: dota_running)
    monkeypatch.setattr(capture_tool.paths, "app_data_dir", forbidden)
    monkeypatch.setattr(capture_tool, "revisar_cfg", forbidden)
    monkeypatch.setattr(capture_tool, "config_temporal_unidades", forbidden)
    monkeypatch.setattr(capture_tool, "Captura", FakeCapture)
    monkeypatch.setattr(capture_tool.time, "sleep", stop_capture)
    assert capture_tool.main(["gsi_capture.py", "--all-data", *extra_args,
                              str(tmp_path / "live.jsonl")]) == 0
    assert path.read_text() == GSI_CFG_TEXT
    assert observed["requested_sections"] == ()
    assert observed["capture_mode"] == "live_existing"
    output = capsys.readouterr().out
    assert "CAPTURA EN VIVO" in output
    assert "AHORA abre Dota" not in output


def test_archivo_en_vivo_no_afirma_que_solicito_las_16_secciones(tmp_path):
    salida = tmp_path / "live.jsonl"
    with Captura(salida, port=0, capture_mode="live_existing") as cap:
        assert _post(cap.port, gsi_payload("r3")) == b"OK"
    saved = json.loads(salida.read_text())
    assert saved["capture_mode"] == "live_existing"
    assert "requested_data" not in saved
