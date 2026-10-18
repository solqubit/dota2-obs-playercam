"""Archivo de configuración GSI de Dota."""
from overpower_cams.config import GSI_CFG_NAME, GSI_CFG_TEXT
from overpower_cams.gsi_cfg import cfg_status, write_cfg


def test_cfg_status(tmp_path):
    ruta = tmp_path / GSI_CFG_NAME
    assert cfg_status(ruta) == "missing"
    write_cfg(ruta)
    assert cfg_status(ruta) == "ok"
    ruta.write_text(GSI_CFG_TEXT.replace('"throttle"      "0.01"', '"throttle" "0.5"'),
                    encoding="utf-8")
    assert cfg_status(ruta) == "different"


def test_cfg_status_ignora_espacios_y_saltos_de_linea(tmp_path):
    ruta = tmp_path / GSI_CFG_NAME
    ruta.write_bytes(GSI_CFG_TEXT.replace("\n", "\r\n").replace("    ", "\t").encode("utf-8"))
    assert cfg_status(ruta) == "ok"


def test_write_cfg_crea_carpeta(tmp_path):
    carpeta = tmp_path / "game" / "dota" / "cfg" / "gamestate_integration"
    assert not carpeta.exists()
    write_cfg(carpeta / GSI_CFG_NAME)
    assert (carpeta / GSI_CFG_NAME).is_file()
    assert cfg_status(carpeta / GSI_CFG_NAME) == "ok"
