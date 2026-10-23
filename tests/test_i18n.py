"""Idioma de la interfaz: catálogo completo, marcadores coherentes, `tr` y detección."""
import ast
import ctypes
import string
from pathlib import Path

import pytest

from overpower_cams import i18n
from overpower_cams.i18n import EN, LANGUAGES, detect_default, get_language, set_language, tr, tr_for

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted((ROOT / "overpower_cams").rglob("*.py")) + [ROOT / "console.py"]
# Función -> posición del texto (la clave) entre sus argumentos.
TR_FUNCS = {"tr": 0, "tr_for": 1}


def _func_name(call: ast.Call) -> str | None:
    f = call.func
    return f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)


def _tr_calls():
    """(archivo, línea, nodo del texto) de cada tr(...)/tr_for(...) del código (menos i18n.py).
    `ast` ya une los literales pegados ("a" "b"), así que eso se admite."""
    for path in SOURCES:
        if path.name == "i18n.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and _func_name(node) in TR_FUNCS:
                idx = TR_FUNCS[_func_name(node)]
                arg = node.args[idx] if len(node.args) > idx else None
                yield path.relative_to(ROOT), node.lineno, arg


def _keys() -> set[str]:
    return {arg.value for _, _, arg in _tr_calls()}


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def test_cada_tr_usa_un_texto_literal():
    """Si la clave no es un literal, este test no podría revisar que esté traducida."""
    malos = [f"{p}:{line}" for p, line, arg in _tr_calls()
             if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str))]
    assert not malos, f"tr() con un texto que no es literal: {malos}"


def test_hay_textos_para_traducir():
    assert len(_keys()) > 150


def test_cada_texto_tiene_traduccion_al_ingles():
    faltan = sorted(_keys() - EN.keys())
    assert not faltan, "Faltan en i18n.EN:\n" + "\n".join(map(repr, faltan))


def test_no_sobran_traducciones():
    sobran = sorted(EN.keys() - _keys())
    assert not sobran, "Entradas de i18n.EN que nadie usa:\n" + "\n".join(map(repr, sobran))


def test_el_catalogo_no_repite_claves():
    tree = ast.parse((ROOT / "overpower_cams" / "i18n.py").read_text(encoding="utf-8"))
    dicts = [n.value for n in ast.walk(tree)
             if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", None) == "EN"]
    assert len(dicts) == 1
    claves = [k.value for k in dicts[0].keys]
    repetidas = sorted({k for k in claves if claves.count(k) > 1})
    assert not repetidas, repetidas


def test_las_traducciones_no_estan_vacias():
    assert all(v.strip() for v in EN.values())


@pytest.mark.parametrize("es", sorted(EN))
def test_los_marcadores_coinciden(es):
    assert _fields(EN[es]) == _fields(es), (es, EN[es])
    # y el formato funciona con esos marcadores
    kw = {name: "X" for name in _fields(es)}
    if kw:
        EN[es].format(**kw)
        es.format(**kw)


def test_tr_en_espanol_devuelve_la_clave():
    set_language("es")
    assert get_language() == "es"
    assert tr("Ajustes") == "Ajustes"
    assert tr("Conectado a OBS en {host}:{port}", host="127.0.0.1", port=4455) == \
        "Conectado a OBS en 127.0.0.1:4455"


def test_tr_en_ingles_traduce_y_formatea():
    set_language("en")
    assert tr("Ajustes") == "Settings"
    assert tr("Revisión") == "Checks"
    assert tr("En vivo") == "Live"
    assert tr("Conectado a OBS en {host}:{port}", host="127.0.0.1", port=4455) == \
        "Connected to OBS at 127.0.0.1:4455"
    assert tr("Los 10 ubicados ({n} afinados con tus clicks)", n=3) == \
        "All 10 located (3 refined by your clicks)"


def test_tr_sin_traduccion_devuelve_el_espanol():
    set_language("en")
    assert tr("Texto que no está en el catálogo") == "Texto que no está en el catálogo"
    assert tr("Hola {nombre}", nombre="Ana") == "Hola Ana"


def test_tr_sin_kw_no_toca_las_llaves():
    set_language("es")
    assert tr("a {b} c") == "a {b} c"


def test_tr_for_usa_el_idioma_pedido_sin_cambiar_el_actual():
    set_language("es")
    assert tr_for("en", "Reiniciar ahora") == "Restart now"
    assert tr_for("es", "Reiniciar ahora") == "Reiniciar ahora"
    assert get_language() == "es"


def test_idioma_desconocido_queda_en_espanol():
    set_language("fr")
    assert get_language() == "es"


def test_languages():
    assert LANGUAGES == {"es": "Español", "en": "English"}


def test_detect_default_si_ctypes_falla_es_ingles(monkeypatch):
    def falla():
        raise OSError("sin Windows")
    monkeypatch.setattr(ctypes.windll.kernel32, "GetUserDefaultUILanguage", falla)
    assert detect_default() == "en"


@pytest.mark.parametrize("lang_id, esperado", [
    (0x0C0A, "es"),   # español (España, moderno)
    (0x080A, "es"),   # español (México)
    (0x2C0A, "es"),   # español (Argentina)
    (0x0409, "en"),   # inglés (EE. UU.)
    (0x0416, "en"),   # portugués (Brasil): no es español -> inglés
])
def test_detect_default_segun_windows(monkeypatch, lang_id, esperado):
    monkeypatch.setattr(ctypes.windll.kernel32, "GetUserDefaultUILanguage", lambda: lang_id)
    assert detect_default() == esperado


def test_el_fixture_deja_espanol():
    assert i18n.get_language() == "es"


def test_app_name_en_los_dos_idiomas():
    from overpower_cams import config
    assert config.app_name() == "OverPower · Cámaras Dota" == config.APP_NAME
    set_language("en")
    assert config.app_name() == "OverPower · Dota Player Cams"


def test_instrucciones_de_escena_nombran_la_coleccion_camaraman():
    from overpower_cams import checks
    for code in ("es", "en"):
        set_language(code)
        assert "Camaraman" in checks._instr_escena()


def test_la_consola_reconoce_los_eventos_en_ingles():
    import console as consola
    set_language("en")
    learn = tr("retrato {slot} mal aprendido: se vuelve a aprender", slot="r1")
    bar = tr("click en la barra superior (x={x}): esperando a GSI para aprenderlo", x="+0.100")
    key = tr("la tecla {key} no seleccionó a {slot} en Dota", key="F1", slot="r1")
    assert consola.engine_event(learn).startswith("[LEARN] ")
    assert consola.engine_event(bar).startswith("[LEARN] ")
    assert consola.engine_event(key).startswith("[KEYS] ")
    for auto in (tr("click retrato {slot} → {cam}", slot="r1", cam="CAM_EQ1_1"),
                 tr("tecla {key} → {cam}", key="F1", cam="CAM_EQ1_1"),
                 tr("sin héroe → oculto")):
        assert consola.engine_event(auto).startswith("[AUTO] "), auto


def test_la_consola_reconoce_los_eventos_en_espanol():
    import console as consola
    assert consola.engine_event("retrato r1 mal aprendido: se vuelve a aprender").startswith("[LEARN]")
    assert consola.engine_event("click en la barra superior (x=+0.100): esperando a GSI para "
                                "aprenderlo").startswith("[LEARN]")
    assert consola.engine_event("la tecla F1 no seleccionó a r1 en Dota").startswith("[KEYS]")
    assert consola.engine_event("click retrato r1 → CAM_EQ1_1").startswith("[AUTO]")
    assert consola.engine_event("[OBS] x") == "[OBS] x"


def test_la_consola_arranca_en_ingles():
    import console as consola
    from overpower_cams.storage import LiveState
    set_language("en")
    lines = consola.startup_lines(LiveState(2, "hidden"))
    assert lines[0] == "[SIDE] Radiant = Team 2   |   Dire = Team 1"
    assert lines[1] == "[AUTO] Mode: Hide all — type 'auto' to resume"
