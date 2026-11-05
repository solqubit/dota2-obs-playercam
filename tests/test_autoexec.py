"""autoexec.cfg de Dota: leer, poner y quitar la tecla de la cámara asistida (todo en tmp_path)."""
import os

import pytest

from overpower_cams import paths
from overpower_cams.autoexec import (
    ASSISTED_COMMAND, assisted_line, find_assisted_key, foreign_binds, has_chained_bind,
    other_binds, read_assisted_key, remove_assisted_key, remove_assisted_text, set_assisted_text,
    write_assisted_key,
)
from overpower_cams.storage import Storage

MIA = f'bind "F4" "{ASSISTED_COMMAND}" // OverPower: cámara asistida'


def _dota(tmp_path, autoexec_bytes=None):
    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    if autoexec_bytes is not None:
        cfg = dota / "game" / "dota" / "cfg"
        cfg.mkdir()
        (cfg / "autoexec.cfg").write_bytes(autoexec_bytes)
    return dota


# ---------- leer ----------

@pytest.mark.parametrize("linea, tecla", [
    ('bind "F4" "dota_toggle_assisted_camera_operator"', "F4"),
    ("bind F7 dota_toggle_assisted_camera_operator", "F7"),
    ('  BIND "kp_end" "DOTA_TOGGLE_ASSISTED_CAMERA_OPERATOR"  // mía', "kp_end"),
    ("\tbind \"F12\" dota_toggle_assisted_camera_operator;", "F12"),
    (MIA, "F4"),
])
def test_find_assisted_key_formatos(linea, tecla):
    assert find_assisted_key('echo "hola"\r\n' + linea + "\r\n") == tecla


def test_find_assisted_key_ignora_comentarios_y_otros_comandos():
    texto = ('// bind "F4" "dota_toggle_assisted_camera_operator"\n'
             'bind "F5" "dota_toggle_assisted_camera_operator_algo"\n'
             'bind "F6" "say hola"\n')
    assert find_assisted_key(texto) is None


def test_find_assisted_key_la_ultima_gana():
    texto = ("bind F4 dota_toggle_assisted_camera_operator\n"
             "bind F7 dota_toggle_assisted_camera_operator\n")
    assert find_assisted_key(texto) == "F7"


def test_other_binds_de_una_tecla():
    texto = ('bind "F4" "dota_toggle_assisted_camera_operator"\nbind f4 "say hola"\n'
             'bind F5 "+voicerecord"\n')
    assert other_binds(texto, "F4") == ["say hola"]
    assert other_binds(texto, "F9") == []


def test_read_assisted_key_sin_archivo_sin_cfg_o_sin_dota(tmp_path):
    assert read_assisted_key(None) is None
    dota = _dota(tmp_path)
    assert read_assisted_key(dota) is None
    (dota / "game" / "dota" / "cfg").mkdir()
    (paths.autoexec_path(dota)).write_bytes(b'echo "\xff"\r\nbind F4 dota_toggle_assisted_camera_operator\r\n')
    assert read_assisted_key(dota) == "F4"


# ---------- texto ----------

def test_set_conserva_todo_lo_demas_y_reemplaza_el_bind_anterior():
    original = ('echo "=== autoexec cargado ==="\r\n'
                'bind "F4" "dota_toggle_assisted_camera_operator"\r\n'
                'dota_camera_distance 1400\r\n')
    nuevo = set_assisted_text(original, "F7")
    assert nuevo == ('echo "=== autoexec cargado ==="\r\n'
                     + MIA.replace("F4", "F7") + "\r\n"
                     'dota_camera_distance 1400\r\n')
    assert find_assisted_key(nuevo) == "F7"
    assert set_assisted_text(nuevo, "F7") == nuevo


def test_set_quita_binds_repetidos_y_agrega_al_final_si_no_habia():
    texto = ("bind F4 dota_toggle_assisted_camera_operator\nsensitivity 2\n"
             "bind F5 dota_toggle_assisted_camera_operator\n")
    nuevo = set_assisted_text(texto, "F9")
    assert nuevo.count(ASSISTED_COMMAND) == 1 and find_assisted_key(nuevo) == "F9"
    assert nuevo.startswith(assisted_line("F9") + "\n" + "sensitivity 2\n")
    sin = set_assisted_text("sensitivity 2", "F9")              # sin salto al final
    assert sin == "sensitivity 2\r\n" + assisted_line("F9") + "\r\n"   # Windows por defecto
    assert set_assisted_text("", "F9") == assisted_line("F9") + "\r\n"


def test_remove_quita_solo_nuestro_comando():
    texto = 'echo hola\r\nbind "F4" "dota_toggle_assisted_camera_operator"\r\nbind F5 "say x"\r\n'
    assert remove_assisted_text(texto) == 'echo hola\r\nbind F5 "say x"\r\n'
    assert remove_assisted_text("echo hola\n") == "echo hola\n"


def test_assisted_line_usa_comillas_y_comentario():
    assert assisted_line("F4") == MIA


# ---------- archivo ----------

def test_write_crea_la_carpeta_cfg_y_el_archivo(tmp_path):
    dota = _dota(tmp_path)
    storage = Storage(tmp_path / "data")
    ruta = write_assisted_key(dota, "F4", storage)
    assert ruta == paths.autoexec_path(dota)
    assert ruta.read_bytes() == (MIA + "\r\n").encode("utf-8")
    assert not (storage.base / "backups").exists()               # no había nada que respaldar


def test_write_hace_backup_y_conserva_bytes_y_saltos(tmp_path):
    original = 'echo "\xe1"\r\nbind "F4" "dota_toggle_assisted_camera_operator"\r\n'.encode("latin-1")
    dota = _dota(tmp_path, original)
    storage = Storage(tmp_path / "data")
    write_assisted_key(dota, "F7", storage)
    data = paths.autoexec_path(dota).read_bytes()
    assert data.startswith(b'echo "\xe1"\r\n')                   # byte no UTF-8 intacto
    assert data.count(b"\n") == data.count(b"\r\n")
    assert read_assisted_key(dota) == "F7"
    copias = list((storage.base / "backups").iterdir())
    assert len(copias) == 1 and copias[0].read_bytes() == original
    assert not [p for p in paths.autoexec_path(dota).parent.iterdir() if p.suffix == ".tmp"]


def test_remove_archivo(tmp_path):
    dota = _dota(tmp_path, b"echo hola\r\nbind F4 dota_toggle_assisted_camera_operator\r\n")
    storage = Storage(tmp_path / "data")
    assert remove_assisted_key(dota, storage) is True
    assert paths.autoexec_path(dota).read_bytes() == b"echo hola\r\n"
    assert remove_assisted_key(dota, storage) is False            # ya no estaba: no escribe
    assert len(list((storage.base / "backups").iterdir())) == 1
    assert remove_assisted_key(_dota(tmp_path / "otra"), storage) is False


def test_write_falla_sin_dejar_temporales(tmp_path, monkeypatch):
    dota = _dota(tmp_path, b"echo hola\r\n")
    storage = Storage(tmp_path / "data")

    def boom(src, dst):
        raise PermissionError("en uso")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(PermissionError):
        write_assisted_key(dota, "F4", storage)
    assert paths.autoexec_path(dota).read_bytes() == b"echo hola\r\n"
    assert [p.name for p in paths.autoexec_path(dota).parent.iterdir()] == ["autoexec.cfg"]


# ---------- bind encadenado escrito a mano ----------

ENCADENADO = 'bind F4 "dota_toggle_assisted_camera_operator; echo x"\r\n'


def test_bind_encadenado_cuenta_como_configurado():
    assert find_assisted_key("echo hola\r\n" + ENCADENADO) == "F4"
    assert find_assisted_key('bind F6 "echo a;dota_toggle_assisted_camera_operator"') == "F6"
    assert find_assisted_key('bind F6 "echo dota_toggle_assisted_camera_operator"') is None
    assert has_chained_bind(ENCADENADO) and not has_chained_bind(MIA)
    assert foreign_binds(ENCADENADO) == []                       # no choca consigo mismo


def test_con_bind_encadenado_no_se_agrega_otro_ni_se_toca():
    texto = "echo hola\r\n" + ENCADENADO
    assert set_assisted_text(texto, "F7") == texto
    assert remove_assisted_text(texto) == texto


def test_archivo_con_bind_encadenado_no_se_escribe(tmp_path):
    dota = _dota(tmp_path, ENCADENADO.encode())
    storage = Storage(tmp_path / "data")
    write_assisted_key(dota, "F7", storage)
    assert remove_assisted_key(dota, storage) is False
    assert paths.autoexec_path(dota).read_bytes() == ENCADENADO.encode()
    assert not (storage.base / "backups").exists()
