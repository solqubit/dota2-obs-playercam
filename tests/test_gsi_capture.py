"""Tests del script de captura de GSI (tools/gsi_capture.py)."""
import json
import urllib.request

from overpower_cams.config import GSI_CFG_NAME, GSI_CFG_TEXT
from tools.gsi_capture import Captura, cfg_pide_habilidades, revisar_cfg
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
