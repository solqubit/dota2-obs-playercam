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


STEAMID64_BASE = 76561197960265728   # SteamID64 = esto + el número de cuenta (accountid)
_USER_RE = re.compile(r'"(\d{17})"\s*\{([^{}]*)\}')
_FIELD_RE = r'"{name}"\s*"([^"]*)"'


def _read_active_user_registry() -> int | None:
    """Cuenta con la que está abierto Steam ahora (ActiveProcess/ActiveUser de HKCU; 0 o
    nada si Steam está cerrado). Nunca lanza."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as k:
            valor = winreg.QueryValueEx(k, "ActiveUser")[0]
    except OSError:
        return None
    return valor if isinstance(valor, int) and valor > 0 else None


# Los tests la reemplazan (conftest) para no leer el registro real.
_read_active_user = _read_active_user_registry


def _login_users_most_recent(steam: Path) -> str | None:
    """accountid de la última cuenta que entró a Steam según config/loginusers.vdf:
    la de "MostRecent" "1" o, si ninguna lo tiene (Steam nuevo), la de "timestamp" más alto."""
    try:
        texto = (Path(steam) / "config" / "loginusers.vdf").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    mejor, mejor_orden = None, None
    for id64, cuerpo in _USER_RE.findall(texto):
        cuenta = int(id64) - STEAMID64_BASE
        if cuenta <= 0:
            continue
        reciente = re.search(_FIELD_RE.format(name="MostRecent"), cuerpo, re.IGNORECASE)
        stamp = re.search(_FIELD_RE.format(name="timestamp"), cuerpo, re.IGNORECASE)
        orden = (bool(reciente) and reciente.group(1).strip() == "1",
                 int(stamp.group(1)) if stamp and stamp.group(1).strip().isdigit() else 0)
        if mejor_orden is None or orden > mejor_orden:
            mejor, mejor_orden = str(cuenta), orden
    return mejor


def _keys_path(steam: Path, account: str) -> Path:
    return Path(steam) / "userdata" / account / DOTA_APP_ID / "remote" / "cfg" / "dotakeys_personal.lst"


def _known_account(steam: Path) -> str | None:
    """La cuenta que dicen Steam (abierto) o loginusers.vdf, si tiene carpeta en userdata."""
    activa = _read_active_user()
    for cuenta in (str(activa) if activa else None, _login_users_most_recent(steam)):
        if cuenta and (Path(steam) / "userdata" / cuenta).is_dir():
            return cuenta
    return None


def _mtime_keys_file(steam: Path) -> Path | None:
    archivos = glob.glob(os.path.join(
        str(steam), "userdata", "*", DOTA_APP_ID, "remote", "cfg", "dotakeys_personal.lst"))
    mejor = max(archivos, key=lambda f: os.path.getmtime(os.path.dirname(f)), default=None)
    return Path(mejor) if mejor else None


def steam_account_id(steam: Path | None) -> str | None:
    """accountid (carpeta de userdata) de la cuenta de Steam en uso: la abierta ahora según el
    registro; si no, la última de loginusers.vdf; si no, la que tiene el archivo de teclas de
    Dota tocado más recientemente."""
    if steam is None:
        return None
    cuenta = _known_account(steam)
    if cuenta is not None:
        return cuenta
    f = _mtime_keys_file(steam)
    return f.parents[3].name if f else None


def dota_keys_file(steam: Path | None) -> Path | None:
    """dotakeys_personal.lst de la cuenta de Steam en uso (`steam_account_id`). Si esa cuenta
    se conoce pero nunca abrió Dota, None: no se usan las teclas de OTRA cuenta."""
    cuenta = steam_account_id(steam)
    if cuenta is None:
        return None
    f = _keys_path(steam, cuenta)
    return f if f.is_file() else None


def autoexec_path(dota: Path) -> Path:
    """autoexec.cfg de Dota: lo ejecuta solo al arrancar (no hace falta opción de lanzamiento)."""
    return Path(dota) / "game" / "dota" / "cfg" / "autoexec.cfg"


def user_keys_default_path(dota: Path) -> Path:
    """Teclas que Dota trae asignadas por defecto a comandos de consola (p. ej. F10)."""
    return Path(dota) / "game" / "dota" / "cfg" / "user_keys_default.vcfg"


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
