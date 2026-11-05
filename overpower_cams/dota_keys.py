"""Teclas de Dota 2 (dotakeys_personal.lst, texto KeyValues de Valve).

Casi todo son funciones puras: reciben y devuelven texto, no leen archivos ni imprimen.
Las que leen un archivo (`read_player_keys`, `read_key_uses`, `read_default_binds`) nunca
lanzan (sin Qt: las usan la app y la consola). La lógica de parseo viene de
`load_player_keys()` del script de consola probado.
"""
import re
from pathlib import Path

from .config import SLOTS
from .paths import user_keys_default_path
from .i18n import tr

# Nombres de tecla del teclado numérico en la config de Dota (estilo Source)
_KP_NAMES = {"KP_INS": 0, "KP_END": 1, "KP_DOWNARROW": 2, "KP_PGDN": 3, "KP_LEFTARROW": 4,
             "KP_5": 5, "KP_RIGHTARROW": 6, "KP_HOME": 7, "KP_UPARROW": 8, "KP_PGUP": 9}

# Tecla por defecto de cada jugador 1..10 en el modo espectador.
DEFAULT_PLAYER_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
# Teclas a las que se mueve una acción que choca con las de los jugadores.
FALLBACK_KEYS = ["F9", "F11"]

_PLAYER_PREFIX = "SpectatorCameraFocusPlayer"
# Entrada `"Spectator..." { ... }` (los bloques de teclas no anidan llaves).
_ENTRY_RE = re.compile(r'"(Spectator\w*)"\s*\{([^{}]*)\}')
_KEY_RE = re.compile(r'"Key"(\s*)"([^"]*)"')
_MOD_RE = re.compile(r'"Modifier"\s*"([^"]*)"')
# Cualquier entrada `"Accion" { ... }` de cualquier sección (Keys, Items…).
_ANY_ENTRY_RE = re.compile(r'"(\w+)"\s*\{([^{}]*)\}')
# Campos con tecla: "Key" y, si el formato las tiene, las secundarias ("Key2", "SecondaryKey"…).
_ANY_KEY_RE = re.compile(r'"((?:Secondary|Alt)?Key\d*)"\s*"([^"]*)"', re.IGNORECASE)
# Bloque "bindings" de user_keys_default.vcfg: `"TECLA" "comando"` por línea.
_BINDINGS_RE = re.compile(r'"bindings"\s*\{([^{}]*)\}', re.IGNORECASE)
_PAIR_RE = re.compile(r'"([^"]*)"[ \t]+"([^"]*)"')
_LINK_RE = re.compile(r'("LinkPlayerToSpectator"\s*)"([^"]*)"')


def dota_key_to_vk(name):
    """Nombre de tecla de Dota -> código de tecla virtual de Windows (None si no se conoce)."""
    n = name.upper()
    if not n:
        return None
    if len(n) == 1 and n.isascii() and n.isalnum():
        return ord(n)
    if n[0] == "F" and n[1:].isdigit() and 1 <= int(n[1:]) <= 12:
        return 0x6F + int(n[1:])
    if n.startswith("KP_") and n[3:].isdigit():
        return 0x60 + int(n[3:])
    if n in _KP_NAMES:
        return 0x60 + _KP_NAMES[n]
    return None


# Mismo botón del teclado numérico con dos nombres (Bloq Num activado o no).
_KEY_ALIASES = {f"KP_{n}": name for name, n in _KP_NAMES.items() if not name[3:].isdigit()}
_KEY_ALIASES.update({"INSERT": "INS", "DELETE": "DEL", "PAGEUP": "PGUP", "PAGEDOWN": "PGDN",
                     "KP_DELETE": "KP_DEL", "RETURN": "ENTER"})


def normalize_key(name: str) -> str:
    """Nombre de tecla para comparar: sin espacios, en mayúsculas y con un solo nombre para
    las del teclado numérico ("KP_1" y "KP_END" son la misma)."""
    n = (name or "").strip().upper()
    return _KEY_ALIASES.get(n, n)


def key_name(vk):
    """Código de tecla virtual -> nombre corto para mostrar."""
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num{vk - 0x60}"
    if 0x70 <= vk <= 0x7B:
        return f"F{vk - 0x6F}"
    return f"vk{vk}"


def _sin_modificador(body: str) -> bool:
    mod = _MOD_RE.search(body)
    return not mod or mod.group(1).lower() == "none"


def _numero_jugador(name: str) -> int | None:
    """N de "SpectatorCameraFocusPlayerN" (None si no es una entrada de jugador)."""
    sufijo = name[len(_PLAYER_PREFIX):]
    return int(sufijo) if name.startswith(_PLAYER_PREFIX) and sufijo.isdigit() else None


def parse_player_keys(text: str) -> dict[int, str]:
    """vk -> slot ("r1".."d5") según SpectatorCameraFocusPlayer1..10.
    Ignora las entradas con un modificador distinto de None."""
    keys: dict[int, str] = {}
    for name, body in _ENTRY_RE.findall(text):
        n = _numero_jugador(name)
        key = _KEY_RE.search(body)
        if n is None or not key or not 1 <= n <= 10 or not _sin_modificador(body):
            continue
        vk = dota_key_to_vk(key.group(2))
        if vk:
            keys[vk] = SLOTS[n - 1]   # jugadores 1-5 = Radiant, 6-10 = Dire
    return keys


def read_player_keys(keys_file) -> dict[int, str]:
    """Teclas de espectador del archivo de Dota (vacío si no existe o no se puede leer)."""
    if keys_file is None:
        return {}
    try:
        text = Path(keys_file).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    return parse_player_keys(text)


def missing_slots(keys: dict[int, str]) -> list[str]:
    """Slots (en orden r1..r5, d1..d5) que no tienen tecla."""
    usados = set(keys.values())
    return [s for s in SLOTS if s not in usados]


def link_enabled(text: str) -> bool:
    """True si "LinkPlayerToSpectator" vale "1" (la tecla del héroe también lo selecciona)."""
    m = _LINK_RE.search(text)
    return bool(m) and m.group(2).strip() == "1"


# ---------- arreglo del archivo ----------

def _player_entries(text: str) -> dict[int, "re.Match"]:
    """Entradas SpectatorCameraFocusPlayerN existentes, por N."""
    out = {}
    for m in _ENTRY_RE.finditer(text):
        n = _numero_jugador(m.group(1))
        if n is not None:
            out.setdefault(n, m)
    return out


def _inicio_de_linea(text: str, pos: int) -> int:
    return text.rfind("\n", 0, pos) + 1


def _indent_de(text: str, pos: int) -> str:
    """Sangría (espacios/tabs) de la línea que contiene `pos`."""
    return re.match(r"[ \t]*", text[_inicio_de_linea(text, pos):]).group(0)


def _fin_de_keys(text: str) -> int:
    """Posición de la llave de cierre del bloque "Keys" (o -1 si no hay)."""
    m = re.search(r'"Keys"\s*\{', text)
    if not m:
        return -1
    nivel = 1
    for i in range(m.end(), len(text)):
        if text[i] == "{":
            nivel += 1
        elif text[i] == "}":
            nivel -= 1
            if nivel == 0:
                return i
    return -1


def _agregar_jugador(text: str, n: int, tecla: str, eol: str) -> str:
    """Inserta el bloque del jugador n (con su tecla) antes del siguiente
    SpectatorCameraFocusPlayer existente, o al final de "Keys"."""
    siguientes = [m for k, m in sorted(_player_entries(text).items()) if k > n]
    if siguientes:
        pos = _inicio_de_linea(text, siguientes[0].start())
        indent = _indent_de(text, siguientes[0].start())
    else:
        fin = _fin_de_keys(text)
        if fin < 0:
            raise ValueError(tr('el archivo no tiene la sección "Keys"'))
        pos = _inicio_de_linea(text, fin)
        indent = _indent_de(text, fin) + "\t"
    bloque = (f'{indent}"{_PLAYER_PREFIX}{n}"{eol}{indent}{{{eol}'
              f'{indent}\t"Key"\t\t"{tecla}"{eol}{indent}}}{eol}')
    return text[:pos] + bloque + text[pos:]


def _asignar_tecla_vacia(text: str, m: "re.Match", tecla: str, eol: str) -> str:
    """Entrada existente sin "Key": agrega la línea Key tras su llave de apertura."""
    llave = text.index("{", m.end(1))
    pos = text.find("\n", llave)
    pos = len(text) if pos == -1 else pos
    if pos > 0 and text[pos - 1] == "\r":
        pos -= 1
    indent = _indent_de(text, m.start(1)) + "\t"
    return text[:pos] + f'{eol}{indent}"Key"\t\t"{tecla}"' + text[pos:]


def _teclas_usadas(text: str) -> set[str]:
    """Teclas (normalizadas) de TODAS las entradas sin modificador, de jugador y de
    espectador: al ver partidas Dota también dispara los atajos de jugador (y le ganan a un
    `bind`), así que ninguna de esas teclas está libre."""
    return {normalize_key(k) for _a, k in parse_key_uses(text)}


def _mover_conflictos(text: str, tecla: str, reserved: set[str]) -> str:
    """Las entradas Spectator* (no de jugador) sin modificador que usan `tecla`
    pasan a la primera libre de FALLBACK_KEYS (libre en todo el archivo y fuera de
    `reserved`), o se quedan sin "Key"."""
    while True:
        for m in _ENTRY_RE.finditer(text):
            key = _KEY_RE.search(m.group(2))
            if (_numero_jugador(m.group(1)) is not None or not key
                    or key.group(2).upper() != tecla.upper() or not _sin_modificador(m.group(2))):
                continue
            ini, fin = m.start(2) + key.start(), m.start(2) + key.end()
            ocupadas = _teclas_usadas(text) | reserved
            libre = next((k for k in FALLBACK_KEYS if normalize_key(k) not in ocupadas), None)
            if libre:
                # conserva el espaciado original entre "Key" y el valor
                text = text[:ini] + f'"Key"{key.group(1)}"{libre}"' + text[fin:]
            else:
                # sin tecla libre: se quita la línea completa de "Key"
                ini_l = _inicio_de_linea(text, ini)
                fin_l = text.find("\n", fin)
                fin_l = len(text) if fin_l == -1 else fin_l + 1
                text = text[:ini_l] + text[fin_l:]
            break
        else:
            return text


def fix_keys_text(text: str, reserved=()) -> str:
    """Arregla el archivo de teclas para el modo espectador:
    (a) cada SpectatorCameraFocusPlayerN sin tecla recibe su tecla por defecto;
    (b) otras acciones Spectator* sin modificador que usen esas teclas pasan a F9/F11 si
        esa tecla no la usa nada más del archivo (de jugador o de espectador) ni está en
        `reserved` (la de la cámara asistida, las propias de Dota); si no hay libre, se
        quedan sin tecla;
    (c) "LinkPlayerToSpectator" pasa a "0".
    Respeta los saltos de línea y el formato del archivo y no toca nada más."""
    eol = "\r\n" if "\r\n" in text else "\n"
    reservadas = {normalize_key(k) for k in reserved}

    asignadas: list[str] = []
    for n in range(1, 11):
        tecla = DEFAULT_PLAYER_KEYS[n - 1]
        existente = _player_entries(text).get(n)
        if existente is None:
            text = _agregar_jugador(text, n, tecla, eol)
            asignadas.append(tecla)
        elif not _KEY_RE.search(existente.group(2)):
            text = _asignar_tecla_vacia(text, existente, tecla, eol)
            asignadas.append(tecla)

    for tecla in asignadas:
        text = _mover_conflictos(text, tecla, reservadas)

    return _LINK_RE.sub(lambda m: f'{m.group(1)}"0"', text, count=1)


# ---------- todas las teclas en uso (para la cámara asistida) ----------

def parse_key_uses(text: str) -> list[tuple[str, str]]:
    """(acción, tecla) de cada entrada de cualquier sección que tenga tecla y no lleve
    modificador (ALT+Q no choca con un `bind` en Q). Incluye las teclas secundarias."""
    out = []
    for name, body in _ANY_ENTRY_RE.findall(text):
        if not _sin_modificador(body):
            continue
        for _campo, key in _ANY_KEY_RE.findall(body):
            if key.strip():
                out.append((name, key.strip()))
    return out


def read_key_uses(keys_file) -> list[tuple[str, str]]:
    """`parse_key_uses` del archivo de teclas (vacío si no hay archivo o no se puede leer)."""
    if keys_file is None:
        return []
    try:
        text = Path(keys_file).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return parse_key_uses(text)


def parse_default_binds(text: str) -> list[tuple[str, str]]:
    """(comando, tecla) del bloque "bindings" de user_keys_default.vcfg (p. ej. F10)."""
    m = _BINDINGS_RE.search(text or "")
    if not m:
        return []
    return [(cmd, key) for key, cmd in _PAIR_RE.findall(m.group(1)) if key.strip()]


def read_default_binds(dota) -> list[tuple[str, str]]:
    """Teclas que Dota trae asignadas por defecto (vacío si no hay Dota o archivo)."""
    if dota is None:
        return []
    try:
        text = user_keys_default_path(dota).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return parse_default_binds(text)


def _action_labels() -> dict[str, str]:
    """Nombres legibles de las acciones más comunes (en el idioma de la interfaz)."""
    return {
        "CourierSelect": tr("Seleccionar mensajero"),
        "CourierDeliver": tr("Mensajero: entregar objetos"),
        "HeroSelect": tr("Seleccionar héroe"),
        "SelectAll": tr("Seleccionar todas las unidades"),
        "ScoreboardToggle": tr("Marcador"),
        "SpectatorScoreboard": tr("Marcador"),
        "Pause": tr("Pausa"),
        "SpectatorPause": tr("Pausa"),
        "Console": tr("Consola"),
        "ShopToggle": tr("Abrir la tienda"),
        "PurchaseQuickbuy": tr("Compra rápida"),
        "PurchaseSticky": tr("Compra fija"),
        "ScreenshotSettings": tr("Captura de pantalla"),
        "ChatTeam": tr("Chat de equipo"),
        "ChatGlobal": tr("Chat general"),
        "SpectatorChat": tr("Chat de espectadores"),
        "ActivateGlyph": tr("Glifo"),
        "CameraGrip": tr("Arrastrar la cámara"),
        "SpectatorCameraGrip": tr("Arrastrar la cámara"),
        "CameraUp": tr("Cámara arriba"), "SpectatorCameraUp": tr("Cámara arriba"),
        "CameraDown": tr("Cámara abajo"), "SpectatorCameraDown": tr("Cámara abajo"),
        "CameraLeft": tr("Cámara a la izquierda"), "SpectatorCameraLeft": tr("Cámara a la izquierda"),
        "CameraRight": tr("Cámara a la derecha"), "SpectatorCameraRight": tr("Cámara a la derecha"),
        "SpectatorHeroSelect": tr("Seleccionar héroe (espectador)"),
        "SpectatorFOWBoth": tr("Niebla: ver ambos equipos"),
        "SpectatorFOWRadient": tr("Niebla: ver Radiant"),
        "SpectatorFOWDire": tr("Niebla: ver Dire"),
        "SpectatorStatsItem": tr("Gráfico de objetos"),
        "SpectatorStatsGold": tr("Gráfico de oro"),
        "SpectatorStatsXP": tr("Gráfico de experiencia"),
        "SpectatorStatsWinChance": tr("Gráfico de probabilidad de victoria"),
        "SpectatorBroadcasterMenu": tr("Menú de comentarista"),
        "SpectatorIncreaseReplaySpeed": tr("Repetición: más rápido"),
        "SpectatorDecreaseReplaySpeed": tr("Repetición: más lento"),
        "SpectatorCoach_ViewToggle": tr("Vista de entrenador"),
    }


def action_label(action: str) -> str:
    """Nombre legible de una acción de dotakeys_personal.lst; si no se conoce, el crudo."""
    n = _numero_jugador(action)
    if n is not None:
        return tr("Cámara: jugador {n}", n=n)
    return _action_labels().get(action, action)


def key_conflicts(key: str, uses, label=action_label) -> list[str]:
    """Nombres (legibles con `label`, sin repetir, en orden) de lo que usa `key` en `uses`,
    una lista de (acción, tecla). Mayúsculas y alias del teclado numérico dan igual."""
    k = normalize_key(key)
    out: list[str] = []
    for action, used in uses:
        if normalize_key(used) == k:
            name = label(action)
            if name not in out:
                out.append(name)
    return out
