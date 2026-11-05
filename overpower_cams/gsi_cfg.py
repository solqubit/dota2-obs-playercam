"""Archivo de configuración GSI de Dota (gamestate_integration_obs.cfg)."""
from pathlib import Path

from .config import GSI_CFG_TEXT
from .storage import atomic_write_bytes


def _compacto(texto: str) -> str:
    """Texto sin espacios ni saltos de línea, para comparar sin importar el formato."""
    return "".join(texto.split())


def cfg_status(path: Path) -> str:
    """"missing" si no existe, "ok" si coincide con GSI_CFG_TEXT (ignorando espacios
    y saltos de línea), "different" si existe pero tiene otro contenido."""
    path = Path(path)
    if not path.is_file():
        return "missing"
    try:
        texto = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "different"
    return "ok" if _compacto(texto) == _compacto(GSI_CFG_TEXT) else "different"


def write_cfg(path: Path) -> None:
    """Escribe GSI_CFG_TEXT en `path` (de forma atómica), creando las carpetas que falten.
    Solo toca ese archivo: los .cfg de GSI de otros programas quedan igual."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, GSI_CFG_TEXT.encode("utf-8"))
