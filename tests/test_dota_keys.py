"""Teclas de espectador de Dota (dotakeys_personal.lst): leer y arreglar."""
from pathlib import Path

from overpower_cams.dota_keys import (
    dota_key_to_vk, fix_keys_text, key_name, link_enabled, missing_slots,
    parse_player_keys,
)

DATA = Path(__file__).parent / "data" / "dotakeys_ejemplo.lst"


def _data() -> str:
    # independiente de autocrlf: el archivo de datos se normaliza a LF
    return DATA.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _bloque(text: str, nombre: str) -> str:
    """Texto del bloque `"nombre" { ... }` (desde el nombre hasta la llave de cierre)."""
    ini = text.index(f'"{nombre}"')
    fin = text.index("}", ini)
    return text[ini:fin + 1]


def test_dota_key_to_vk_y_key_name():
    assert dota_key_to_vk("1") == 0x31
    assert dota_key_to_vk("a") == 0x41
    assert dota_key_to_vk("F9") == 0x78
    assert dota_key_to_vk("KP_5") == 0x65
    assert dota_key_to_vk("KP_INS") == 0x60
    assert dota_key_to_vk("MOUSE3") is None
    assert key_name(0x31) == "1"
    assert key_name(0x65) == "Num5"
    assert key_name(0x78) == "F9"
    assert key_name(0x1B) == "vk27"


def test_parse_archivo_de_ejemplo():
    data = _data()
    keys = parse_player_keys(data)
    assert len(keys) == 9
    assert missing_slots(keys) == ["r1"]
    assert link_enabled(data) is True


def test_parse_ignora_modificador():
    texto = (
        '"Keys"\n\t{\n'
        '\t\t"SpectatorCameraFocusPlayer1"\n\t\t{\n\t\t\t"Key"\t\t"1"\n'
        '\t\t\t"Modifier"\t\t"CTRL"\n\t\t}\n'
        '\t\t"SpectatorCameraFocusPlayer2"\n\t\t{\n\t\t\t"Key"\t\t"KP_5"\n'
        '\t\t\t"Modifier"\t\t"None"\n\t\t}\n'
        '\t}\n'
    )
    assert parse_player_keys(texto) == {0x65: "r2"}


def test_fix_asigna_1_y_mueve_hero_select():
    data = _data()
    arreglado = fix_keys_text(data)
    keys = parse_player_keys(arreglado)
    assert len(keys) == 10
    assert keys[0x31] == "r1"
    assert missing_slots(keys) == []
    assert '"Key"\t\t"F9"' in _bloque(arreglado, "SpectatorHeroSelect")
    assert link_enabled(arreglado) is False
    assert fix_keys_text(arreglado) == arreglado


def test_fix_inserta_con_el_formato_del_archivo():
    arreglado = fix_keys_text(_data())
    assert (
        '\t\t"SpectatorCameraFocusPlayer1"\n\t\t{\n\t\t\t"Key"\t\t"1"\n\t\t}\n'
        '\t\t"SpectatorCameraFocusPlayer2"'
    ) in arreglado


def test_fix_no_toca_lo_demas():
    original = _data().split("\n")
    arreglado = fix_keys_text(_data()).split("\n")

    def sin_las_tres(lineas: list[str]) -> list[str]:
        out, i = [], 0
        while i < len(lineas):
            ln = lineas[i]
            if '"LinkPlayerToSpectator"' in ln or '"SpectatorCameraFocusPlayer1"' in ln \
                    or '"SpectatorHeroSelect"' in ln:
                if "LinkPlayerToSpectator" in ln:
                    i += 1
                else:   # bloque: nombre, {, ..., }
                    while lineas[i].strip() != "}":
                        i += 1
                    i += 1
                continue
            out.append(ln)
            i += 1
        return out

    assert sin_las_tres(arreglado) == sin_las_tres(original)


def test_fix_conserva_crlf():
    crlf = _data().replace("\n", "\r\n")
    arreglado = fix_keys_text(crlf)
    assert "\n" not in arreglado.replace("\r\n", "")
    assert parse_player_keys(arreglado)[0x31] == "r1"
    assert fix_keys_text(arreglado) == arreglado


def test_fix_sin_tecla_libre_quita_la_tecla_en_conflicto():
    data = _data()
    # F9 y F11 ya usadas por otras entradas Spectator sin modificador
    extra = (
        '\t\t"SpectatorNueva1"\n\t\t{\n\t\t\t"Key"\t\t"F9"\n\t\t}\n'
        '\t\t"SpectatorNueva2"\n\t\t{\n\t\t\t"Key"\t\t"F11"\n\t\t}\n'
    )
    data = data.replace('\t\t"SpectatorPause"', extra + '\t\t"SpectatorPause"')
    arreglado = fix_keys_text(data)
    assert '"Key"' not in _bloque(arreglado, "SpectatorHeroSelect").split("Modifier")[0]
    assert fix_keys_text(arreglado) == arreglado


def test_fix_sin_keys_que_arreglar_no_cambia_nada():
    arreglado = fix_keys_text(_data())
    assert fix_keys_text(arreglado) == arreglado


def test_fix_sin_ninguna_entrada_de_jugador_las_agrega_al_final_de_keys():
    texto = (
        '"KeyBindings"\n{\n\t"LinkPlayerToSpectator"\t\t"1"\n\t"Keys"\n\t{\n'
        '\t\t"CameraUp"\n\t\t{\n\t\t\t"Key"\t\t"UPARROW"\n\t\t}\n'
        '\t}\n}\n'
    )
    keys = parse_player_keys(fix_keys_text(texto))
    assert len(keys) == 10
    assert keys[0x30] == "d5"
