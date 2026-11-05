"""autoexec.cfg de Dota (game\\dota\\cfg\\autoexec.cfg): la tecla de la cámara asistida.

Dota ejecuta ese archivo solo, al arrancar (no hace falta ninguna opción de lanzamiento), así
que un `bind "F4" "dota_toggle_assisted_camera_operator"` ahí deja la tecla puesta para
siempre. Ojo: los atajos propios de Dota (dotakeys_personal.lst) le ganan a un `bind`.

Las funciones de texto son puras. Las de archivo conservan byte a byte todo lo demás
(codificación y saltos de línea, como `checks._read_keys_text`), hacen copia de seguridad
antes de cambiar un archivo que ya existía y escriben de forma atómica.
"""
from __future__ import annotations

import re
from pathlib import Path

from .paths import autoexec_path
from .storage import atomic_write_bytes

ASSISTED_COMMAND = "dota_toggle_assisted_camera_operator"
COMMENT = "// OverPower: cámara asistida"

# Una línea `bind TECLA comando`, con o sin comillas y con un comentario o `;` al final.
_BIND_RE = re.compile(r'^[ \t]*bind[ \t]+(?:"([^"]+)"|(\S+))[ \t]+(?:"([^"]*)"|([^\s;/]+))'
                      r'[ \t]*;?[ \t]*(?://.*)?$', re.IGNORECASE)


def _binds(text: str):
    """(índice de línea, tecla, comando) de cada `bind` del texto."""
    for i, line in enumerate(text.splitlines()):
        m = _BIND_RE.match(line)
        if m:
            yield i, (m.group(1) or m.group(2)), (m.group(3) if m.group(3) is not None else m.group(4))


def _es_nuestro(command: str) -> bool:
    """El bind es exactamente el de la cámara asistida (el que la app escribe y reemplaza)."""
    return command.strip().lower() == ASSISTED_COMMAND


def _lo_incluye(command: str) -> bool:
    """El comando ejecuta la cámara asistida, solo o encadenado («cmd1; cmd2»)."""
    return any(part.strip().lower() == ASSISTED_COMMAND for part in command.split(";"))


def find_assisted_key(text: str) -> str | None:
    """Tecla de la cámara asistida en el texto (la última, como la deja Dota), o None.
    Cuenta también un bind encadenado escrito a mano (`bind F4 "...operator; echo x"`)."""
    key = None
    for _i, k, cmd in _binds(text):
        if _lo_incluye(cmd):
            key = k
    return key


def has_chained_bind(text: str) -> bool:
    """Hay un bind encadenado (escrito a mano) que ejecuta la cámara asistida: la app no lo toca
    ni agrega otro."""
    return any(_lo_incluye(cmd) and not _es_nuestro(cmd) for _i, _k, cmd in _binds(text))


def foreign_binds(text: str) -> list[tuple[str, str]]:
    """(tecla, comando) de cada `bind` del texto que no ejecuta la cámara asistida."""
    return [(k, cmd) for _i, k, cmd in _binds(text) if not _lo_incluye(cmd)]


def other_binds(text: str, key: str) -> list[str]:
    """Comandos de otros `bind` del texto en esa tecla (mayúsculas dan igual)."""
    from .dota_keys import normalize_key
    k = normalize_key(key)
    return [cmd for kk, cmd in foreign_binds(text) if normalize_key(kk) == k]


def assisted_line(key: str) -> str:
    """La línea que escribe la app (y la que se puede pegar en la consola, sin el comentario)."""
    return f'bind "{key}" "{ASSISTED_COMMAND}" {COMMENT}'


def console_line(key: str) -> str:
    return f'bind "{key}" "{ASSISTED_COMMAND}"'


def _eol(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n" if "\n" in text else "\r\n"      # archivo nuevo: estilo Windows


def _sin_nuestras_lineas(text: str) -> tuple[list[str], int | None]:
    """Líneas (con su salto) sin nuestros `bind`, y dónde estaba el primero."""
    lines = text.splitlines(keepends=True)
    ours = {i for i, _k, cmd in _binds(text) if _es_nuestro(cmd)}
    first = min(ours) if ours else None
    return [ln for i, ln in enumerate(lines) if i not in ours], first


def set_assisted_text(text: str, key: str) -> str:
    """El texto con un solo bind de la cámara asistida en `key`: en el lugar del primero que
    había (los demás se quitan) o al final. Todo lo demás queda igual. Si hay un bind
    encadenado escrito a mano, el texto no cambia (no se agrega otro)."""
    if has_chained_bind(text):
        return text
    eol = _eol(text)
    lines, first = _sin_nuestras_lineas(text)
    if first is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += eol
        lines.append(assisted_line(key) + eol)
    else:
        original = text.splitlines(keepends=True)[first]
        fin = original[len(original.rstrip("\r\n")):] or eol
        lines.insert(first, assisted_line(key) + fin)
    return "".join(lines)


def remove_assisted_text(text: str) -> str:
    """El texto sin ningún bind de la cámara asistida. Un bind encadenado escrito a mano no se
    toca (el texto no cambia)."""
    if has_chained_bind(text):
        return text
    return "".join(_sin_nuestras_lineas(text)[0])


def _read(path: Path) -> str:
    return Path(path).read_bytes().decode("utf-8", errors="surrogateescape")


def _encode(text: str) -> bytes:
    return text.encode("utf-8", errors="surrogateescape")


def read_assisted_key(dota) -> str | None:
    """Tecla configurada en el autoexec.cfg de esa carpeta de Dota (None si no hay)."""
    if dota is None:
        return None
    path = autoexec_path(dota)
    if not path.is_file():
        return None
    return find_assisted_key(_read(path))


def read_text(dota) -> str:
    """Texto del autoexec.cfg ("" si no existe)."""
    path = autoexec_path(dota)
    return _read(path) if path.is_file() else ""


def write_assisted_key(dota, key: str, storage) -> Path:
    """Pone la tecla en autoexec.cfg (crea la carpeta cfg y el archivo si faltan). Hace copia
    de seguridad con `storage.backup` si el archivo ya existía. Lanza OSError si no puede."""
    path = autoexec_path(dota)
    path.parent.mkdir(parents=True, exist_ok=True)
    existe = path.is_file()
    original = _read(path) if existe else ""
    nuevo = set_assisted_text(original, key)
    if existe and nuevo == original:
        return path
    if existe:
        storage.backup(path)
    atomic_write_bytes(path, _encode(nuevo))
    return path


def remove_assisted_key(dota, storage) -> bool:
    """Quita la tecla del autoexec.cfg. False si no estaba (no escribe nada)."""
    path = autoexec_path(dota)
    if not path.is_file():
        return False
    original = _read(path)
    nuevo = remove_assisted_text(original)
    if nuevo == original:
        return False
    storage.backup(path)
    atomic_write_bytes(path, _encode(nuevo))
    return True
