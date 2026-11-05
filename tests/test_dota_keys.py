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


# ---------- todas las teclas en uso (todas las secciones) ----------

from overpower_cams.dota_keys import (  # noqa: E402
    action_label, key_conflicts, normalize_key, parse_default_binds, parse_key_uses,
    read_default_binds, read_key_uses,
)

MINI = (
    '"KeyBindings"\n{\n\t"Keys"\n\t{\n'
    '\t\t"CourierSelect"\n\t\t{\n\t\t\t"Key"\t\t"F4"\n\t\t\t"Mode"\t\t"0"\n\t\t}\n'
    '\t\t"HeroSelect"\n\t\t{\n\t\t\t"Key"\t\t"f1"\n\t\t}\n'
    '\t\t"ChatVoiceTeam"\n\t\t{\n\t\t\t"Mode"\t\t"0"\n\t\t}\n'
    '\t\t"ScoreboardToggle"\n\t\t{\n\t\t\t"Key"\t\t"Q"\n\t\t\t"Modifier"\t\t"ALT"\n\t\t}\n'
    '\t\t"SpectatorFOWBoth"\n\t\t{\n\t\t\t"Key"\t\t"F1"\n\t\t\t"Modifier"\t\t"None"\n\t\t}\n'
    '\t\t"Console"\n\t\t{\n\t\t\t"Key"\t\t"\\"\n\t\t}\n'
    '\t\t"AlgoNuevo"\n\t\t{\n\t\t\t"Key"\t\t"G"\n\t\t\t"Key2"\t\t"F12"\n\t\t}\n'
    '\t}\n\t"Items"\n\t{\n'
    '\t\t"item_blink"\n\t\t{\n\t\t\t"Key"\t\t"KP_END"\n\t\t}\n'
    '\t}\n}\n'
)


def test_parse_key_uses_lee_todas_las_secciones_sin_modificador():
    uses = parse_key_uses(MINI)
    assert ("CourierSelect", "F4") in uses
    assert ("HeroSelect", "f1") in uses and ("SpectatorFOWBoth", "F1") in uses
    assert ("Console", "\\") in uses
    assert ("AlgoNuevo", "G") in uses and ("AlgoNuevo", "F12") in uses   # tecla secundaria
    assert ("item_blink", "KP_END") in uses                              # sección Items
    assert not any(a == "ScoreboardToggle" for a, _ in uses)             # ALT+Q no choca con Q
    assert not any(a == "ChatVoiceTeam" for a, _ in uses)                # sin tecla


def test_parse_key_uses_del_archivo_real_de_ejemplo():
    uses = parse_key_uses(_data())
    assert ("CourierSelect", "F4") in uses
    assert ("SpectatorBroadcasterMenu", "F10") in uses


def test_normalize_key_ignora_mayusculas_y_alias_del_teclado_numerico():
    assert normalize_key("f4") == normalize_key("F4") == "F4"
    assert normalize_key("KP_1") == normalize_key("kp_end")
    assert normalize_key("KP_0") == normalize_key("KP_INS")
    assert normalize_key(" space ") == "SPACE"


def test_key_conflicts_nombres_legibles_y_sin_repetir():
    uses = parse_key_uses(MINI)
    assert key_conflicts("f4", uses) == ["Seleccionar mensajero"]
    assert key_conflicts("F1", uses) == ["Seleccionar héroe", "Niebla: ver ambos equipos"]
    assert key_conflicts("KP_1", uses) == ["item_blink"]                 # sin nombre: el crudo
    assert key_conflicts("F11", uses) == []
    assert key_conflicts("F4", uses + [("CourierSelect", "F4")]) == ["Seleccionar mensajero"]


def test_action_label_espectador_e_ingles():
    from overpower_cams import i18n
    assert action_label("SpectatorCameraFocusPlayer3") == "Cámara: jugador 3"
    assert action_label("SpectatorBroadcasterMenu") == "Menú de comentarista"
    assert action_label("SpectatorStatsGold") == "Gráfico de oro"
    assert action_label("Pause") == "Pausa"
    assert action_label("CosaRara") == "CosaRara"
    i18n.set_language("en")
    assert action_label("CourierSelect") == "Select courier"
    assert action_label("SpectatorCameraFocusPlayer10") == "Camera: player 10"


def test_read_key_uses_sin_archivo_o_ilegible(tmp_path):
    assert read_key_uses(None) == []
    assert read_key_uses(tmp_path / "no.lst") == []
    f = tmp_path / "k.lst"
    f.write_bytes(MINI.encode("utf-8") + b"\xff")
    assert ("CourierSelect", "F4") in read_key_uses(f)


VCFG = ('"config"\r\n{\r\n\t"bindings"\r\n\t{\r\n\t\t"\\" "toggleconsole"\r\n'
        '\t\t"F10" "return_to_tools_from_engine"\r\n\t}\r\n\t\r\n\t"analogbindings"\r\n\t{\r\n\r\n\t}\r\n}\r\n')


def test_parse_default_binds_del_vcfg():
    assert parse_default_binds(VCFG) == [("toggleconsole", "\\"), ("return_to_tools_from_engine", "F10")]
    assert parse_default_binds("") == []
    assert parse_default_binds('"config" { "analogbindings" { "A" "x" } }') == []


def test_read_default_binds(tmp_path):
    dota = tmp_path / "dota 2 beta"
    assert read_default_binds(dota) == []
    cfg = dota / "game" / "dota" / "cfg"
    cfg.mkdir(parents=True)
    (cfg / "user_keys_default.vcfg").write_text(VCFG, encoding="utf-8", newline="")
    assert ("return_to_tools_from_engine", "F10") in read_default_binds(dota)
    assert read_default_binds(None) == []


# ---------- el arreglo mira todas las secciones y respeta las teclas reservadas ----------

def test_fix_no_mueve_a_una_tecla_que_usa_un_atajo_de_jugador():
    # F9 la usa un atajo de JUGADOR (no Spectator*): Dota también lo dispara al ver partidas
    data = _data().replace('\t\t"CourierSelect"\n\t\t{\n\t\t\t"Key"\t\t"F4"',
                           '\t\t"CourierSelect"\n\t\t{\n\t\t\t"Key"\t\t"F9"')
    arreglado = fix_keys_text(data)
    assert '"Key"\t\t"F11"' in _bloque(arreglado, "SpectatorHeroSelect")


def test_fix_no_mueve_a_la_tecla_reservada_de_la_camara_asistida():
    arreglado = fix_keys_text(_data(), reserved={"f9"})
    assert '"Key"\t\t"F11"' in _bloque(arreglado, "SpectatorHeroSelect")
    assert fix_keys_text(arreglado, reserved={"F9"}) == arreglado
