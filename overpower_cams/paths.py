"""Ubicación de Steam, Dota 2 y sus archivos de configuración (solo Windows)."""
import glob
import os
import re
import subprocess
import sys
import winreg
from pathlib import Path

from .config import APP_DIR_NAME, GSI_CFG_NAME

DOTA_APP_ID = "570"


def steam_path() -> Path | None:
    """Carpeta de Steam según el registro (clave Software/Valve/Steam de HKCU, valor SteamPath)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            valor = winreg.QueryValueEx(k, "SteamPath")[0]
    except OSError:
        return None
    return Path(valor) if valor else None


def steam_libraries(steam: Path) -> list[Path]:
    """Bibliotecas de Steam (libraryfolders.vdf). Siempre incluye la carpeta de Steam."""
    libs: list[Path] = []
    vdf = Path(steam) / "steamapps" / "libraryfolders.vdf"
    try:
        texto = vdf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        texto = ""
    for ruta in re.findall(r'"path"\s+"([^"]+)"', texto):
        libs.append(Path(ruta.replace("\\\\", "\\")))
    if not any(os.path.normcase(p) == os.path.normcase(steam) for p in libs):
        libs.append(Path(steam))
    return libs


def find_dota(steam: Path | None) -> Path | None:
    """Carpeta de instalación de Dota 2 (la biblioteca que tiene su appmanifest)."""
    if steam is None:
        return None
    for lib in steam_libraries(steam):
        if (lib / "steamapps" / f"appmanifest_{DOTA_APP_ID}.acf").is_file():
            return lib / "steamapps" / "common" / "dota 2 beta"
    return None


def is_dota_dir(dota: Path | str | None) -> bool:
    """True si la carpeta parece una instalación de Dota 2 (tiene game\\dota)."""
    return dota is not None and (Path(dota) / "game" / "dota").is_dir()


def gsi_cfg_path(dota: Path) -> Path:
    """Dónde va el .cfg de Game State Integration de esta app."""
    return Path(dota) / "game" / "dota" / "cfg" / "gamestate_integration" / GSI_CFG_NAME


def dota_keys_file(steam: Path | None) -> Path | None:
    """dotakeys_personal.lst de la cuenta de Steam usada más recientemente."""
    if steam is None:
        return None
    archivos = glob.glob(os.path.join(
        str(steam), "userdata", "*", DOTA_APP_ID, "remote", "cfg", "dotakeys_personal.lst"))
    mejor = max(archivos, key=lambda f: os.path.getmtime(os.path.dirname(f)), default=None)
    return Path(mejor) if mejor else None


def app_data_dir() -> Path:
    """Carpeta de datos de la app en %APPDATA% (se crea si no existe)."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    d = Path(base) / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_running(exe: str) -> bool:
    """True si hay un proceso con ese nombre de imagen. Nunca lanza: ante error, False."""
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe}"],
            capture_output=True, text=True, errors="ignore",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return exe.lower() in (r.stdout or "").lower()


def resource_path(rel: str) -> Path:
    """Archivo que viaja con la app (p. ej. "assets/Borde.png"). Empaquetada con PyInstaller
    está en sys._MEIPASS; sin empaquetar, en la raíz del repositorio."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).resolve().parent.parent / rel


def relaunch_command() -> list[str]:
    """Cómo volver a abrir la app: el .exe tal cual, o `python -m overpower_cams.app`."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "overpower_cams.app"]


def relaunch() -> None:
    """Abre otra copia de la app (p. ej. tras cambiar el idioma). Quien llama debe cerrar
    la actual ANTES, para liberar el puerto GSI."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"   # que el .exe nuevo arranque como uno nuevo
    cwd = None if getattr(sys, "frozen", False) else str(Path(__file__).resolve().parent.parent)
    subprocess.Popen(relaunch_command(), cwd=cwd, env=env, close_fds=True)
