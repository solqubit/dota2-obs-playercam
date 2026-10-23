"""Revisiones (verde / amarillo / rojo) y arreglos de Dota, Steam y OBS.

`run_checks` solo LEE: no escribe archivos ni cambia nada en OBS. Los cambios los hace
únicamente `apply_fix`, siempre con cuidado (copia de seguridad, negarse si Dota está abierto).
Ninguna revisión lanza excepciones: si algo falla por dentro, esa revisión queda en "error"
con el texto de la excepción y las demás se siguen ejecutando.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from obsws_python.error import OBSSDKRequestError

from . import config, gsi_cfg, paths
from .dota_keys import fix_keys_text, link_enabled, missing_slots, parse_player_keys
from .i18n import tr
from .obs_link import ObsLink
from .portraits import PortraitModel
from .storage import Settings, Storage

DOTA_EXE = "dota2.exe"
ALL_CAMERAS = config.CAMERAS_TEAM1 + config.CAMERAS_TEAM2   # v1: la Task 8 reescribe estas revisiones
_RESOURCE_NOT_FOUND = 600   # código de obs-websocket: la escena no existe

# Textos largos ("Ver instrucciones"): funciones, para que salgan en el idioma elegido.
def _instr_obs() -> str:
    return tr(
        "1. Abre OBS Studio.\n"
        "2. Ve a Herramientas → Ajustes del servidor WebSocket.\n"
        "3. Marca «Habilitar servidor WebSocket».\n"
        "4. Revisa que el puerto sea el mismo que está en Ajustes de esta app (por defecto 4455).\n"
        "5. Pulsa «Mostrar información de conexión», copia la contraseña y pégala en Ajustes de esta app.")


def _instr_obs_auth() -> str:
    return tr(
        "OBS está abierto, pero rechazó la contraseña.\n"
        "1. En OBS ve a Herramientas → Ajustes del servidor WebSocket.\n"
        "2. Pulsa «Mostrar información de conexión» y copia la contraseña.\n"
        "3. Pégala en Ajustes de esta app.")


def _instr_gsi_data() -> str:
    return tr(
        "Dota está abierto pero no está mandando datos a la app.\n"
        "1. Entra a una partida o a ver una repetición: en el menú principal Dota no manda nada.\n"
        "2. Revisa que la revisión «Archivo GSI» esté en verde y reinicia Dota si la acabas de arreglar.\n"
        "3. Si sigue sin llegar nada: en Steam, clic derecho en Dota 2 → Propiedades → Opciones de "
        "lanzamiento y agrega  -gamestateintegration  (Valve lo documenta como necesario; en algunos "
        "equipos funciona sin esa opción).\n"
        "4. Cierra Dota por completo y ábrelo de nuevo.")


def _instr_escena() -> str:
    return tr(
        "Para importar la escena de OBS (la que te pasó el organizador, o la de ejemplo\n"
        "«example-scene.json» que viene junto a la app):\n"
        "1. En OBS ve a Colección de escenas → Importar.\n"
        "2. Agrega el archivo .json de la escena y confirma.\n"
        "3. Luego Colección de escenas → elige la colección importada.\n"
        "Si ya la tenías, revisa que los nombres de las cámaras sean exactamente CAM_EQ1_1 … CAM_EQ2_5.")


def check_title(cid: str) -> str:
    """Título de cada revisión, en el idioma de la interfaz."""
    titles = {
        "dota": tr("Dota instalado"),
        "gsi_cfg": tr("Archivo GSI"),
        "gsi_data": tr("Datos de Dota llegando"),
        "keys": tr("Teclas de espectador"),
        "obs": tr("OBS y WebSocket"),
        "scene": tr("Escena de OBS"),
        "companion_images": tr("Imágenes de Borde y Marco"),
        "portraits": tr("Retratos"),
    }
    return titles[cid]


def _join_and(names: list[str]) -> str:
    """"Borde", "Borde y Marco", "A, B y C"."""
    if len(names) <= 1:
        return "".join(names)
    return tr("{first} y {last}", first=", ".join(names[:-1]), last=names[-1])


class FixRefused(Exception):
    """No se puede arreglar ahora; el texto es el mensaje para el usuario."""


@dataclass
class CheckResult:
    id: str
    status: str            # "ok" | "warn" | "error"
    title: str
    detail: str
    fix_label: str | None = None
    instructions: str | None = None


@dataclass
class Context:
    storage: Storage
    settings: Settings
    steam: Path | None
    dota: Path | None
    keys_file: Path | None
    obs: ObsLink
    last_post_t: float | None
    now: float
    assets_dir: Path        # imágenes de la app (Borde.png, Marco.png…), en _internal\assets del .exe
    portraits: PortraitModel


def _res(cid, status, detail, fix_label=None, instructions=None) -> CheckResult:
    return CheckResult(cid, status, check_title(cid), detail, fix_label, instructions)


# ---------- OBS: lectura de la escena (solo lectura) ----------

@dataclass
class _Scan:
    state: str                              # "ok" | "disconnected" | "no_scene" | "lost"
    found: dict | None = None               # nombre -> (contenedor, id)
    error: str = ""

    @property
    def missing_cameras(self) -> list[str]:
        return [n for n in ALL_CAMERAS if n not in (self.found or {})]

    @property
    def missing_companions(self) -> list[str]:
        return [n for n in config.COMPANIONS_V1 if n not in (self.found or {})]


def _scan_scene(obs: ObsLink) -> _Scan:
    """Lee qué hay en la escena SIN tocar nada (load_items() apagaría las cámaras al aire)."""
    if not obs.connected:
        return _Scan("disconnected")
    try:
        return _Scan("ok", obs.find_scene_items(config.SCENE_NAME))
    except OBSSDKRequestError as e:
        if e.code == _RESOURCE_NOT_FOUND:
            return _Scan("no_scene")
        return _Scan("lost", error=f"{type(e).__name__}: {e}")
    except Exception as e:  # noqa: BLE001 - conexión caída, se informa como pérdida
        return _Scan("lost", error=f"{type(e).__name__}: {e}")


# ---------- revisiones ----------

def _check_dota(ctx: Context, **_) -> CheckResult:
    if paths.is_dota_dir(ctx.dota):
        return _res("dota", "ok", str(ctx.dota))
    detail = tr("No encontré Dota")
    if ctx.dota is not None:
        if Path(ctx.dota).is_dir():
            detail = tr("Esa carpeta no parece ser Dota 2 (falta game\\dota): {path}", path=ctx.dota)
        else:
            detail = tr("No encontré Dota: la carpeta {path} no existe", path=ctx.dota)
    return _res("dota", "error", detail, tr("Buscar…"),
                tr("Elige la carpeta donde está instalado Dota 2 (la que se llama «dota 2 beta» "
                   "y contiene la carpeta «game»). Suele estar en <tu biblioteca de Steam>\\steamapps\\common."))


def _check_gsi_cfg(ctx: Context, **_) -> CheckResult:
    if ctx.dota is None:
        return _res("gsi_cfg", "error", tr("No se puede revisar sin la carpeta de Dota"))
    estado = gsi_cfg.cfg_status(paths.gsi_cfg_path(ctx.dota))
    if estado == "ok":
        return _res("gsi_cfg", "ok", tr("El archivo que le dice a Dota dónde mandar los datos está bien"))
    if estado == "missing":
        detail = tr("Falta el archivo que le dice a Dota que mande los datos a esta app")
    else:
        detail = tr("El archivo de Dota para esta app tiene un contenido distinto al esperado")
    return _res("gsi_cfg", "error", detail, tr("Arreglar"),
                tr("«Arreglar» crea la carpeta gamestate_integration si no existe y escribe el archivo "
                   "{file}. Dota lo lee al arrancar: si está abierto, hay que reiniciarlo.",
                   file=config.GSI_CFG_NAME))


def _check_gsi_data(ctx: Context, *, is_running, **_) -> CheckResult:
    if ctx.last_post_t is not None and ctx.now - ctx.last_post_t <= config.GSI_STALE_S:
        return _res("gsi_data", "ok", tr("Llegan datos de Dota"))
    if not is_running(DOTA_EXE):
        return _res("gsi_data", "warn", tr("Sin datos: Abre Dota y entra a una partida"))
    return _res("gsi_data", "error", tr("Dota está abierto pero no llegan datos"), None,
                _instr_gsi_data())


def _slot_label(slot: str) -> str:
    return f"{'Radiant' if slot[0] == 'r' else 'Dire'} {slot[1:]}"


def _read_keys_text(path: Path) -> str:
    """Texto del archivo de teclas. `surrogateescape` permite devolver los mismos bytes al
    escribir, aunque el archivo tenga algo que no sea UTF-8; `newline=""` no toca los saltos."""
    return Path(path).read_bytes().decode("utf-8", errors="surrogateescape")


def _check_keys(ctx: Context, **_) -> CheckResult:
    if ctx.keys_file is None or not Path(ctx.keys_file).is_file():
        return _res("keys", "warn",
                    tr("No encontré el archivo de teclas de Dota (dotakeys_personal.lst). "
                       "Las teclas rápidas no se van a poder usar; los clicks en retratos y GSI sí."),
                    None,
                    tr("Abre Dota con la misma cuenta de Steam, entra a Ajustes → Teclas rápidas y "
                       "cierra la ventana para que Dota cree el archivo. Luego pulsa «Revisar todo de nuevo»."))
    texto = _read_keys_text(ctx.keys_file)
    faltan = missing_slots(parse_player_keys(texto))
    if faltan:
        return _res("keys", "error",
                    tr("Faltan teclas de espectador para: {slots}",
                       slots=", ".join(_slot_label(s) for s in faltan)),
                    tr("Arreglar"),
                    tr("«Arreglar» (con Dota cerrado) hace una copia de seguridad del archivo y asigna "
                       "las teclas 1 a 9 y 0 a los jugadores 1 a 10. Si otra acción de espectador usa "
                       "esa tecla, la pasa a una libre (F9)."))
    if link_enabled(texto):
        return _res("keys", "warn",
                    tr("Está activada la opción «Copiar las teclas rápidas del espectador desde la "
                       "sección Teclas rápidas»; puede pisar las teclas de espectador"),
                    tr("Arreglar"),
                    tr("«Arreglar» (con Dota cerrado) desactiva esa opción, con copia de seguridad."))
    return _res("keys", "ok", tr("Los 10 jugadores tienen su tecla de espectador"))


def _check_obs(ctx: Context, scan: _Scan, **_) -> CheckResult:
    obs = ctx.obs
    if scan.state == "lost":
        return _res("obs", "error",
                    tr("Se perdió la conexión con OBS — reintentando ({error})", error=scan.error),
                    None, _instr_obs())
    if obs.connected:
        return _res("obs", "ok", tr("Conectado a OBS en {host}:{port}", host=obs.host, port=obs.port))
    err = obs.error
    if err == "auth" and not obs.password:
        return _res("obs", "error", tr("Falta la contraseña de OBS: escríbela en Ajustes"),
                    None, _instr_obs())
    if err == "auth":
        return _res("obs", "error", tr("Contraseña incorrecta: cámbiala en Ajustes"), None,
                    _instr_obs_auth())
    if err == "lost":
        return _res("obs", "error", tr("Se perdió la conexión con OBS — reintentando"), None,
                    _instr_obs())
    if err == "refused" or err is None:
        return _res("obs", "error",
                    tr("No pude conectar con OBS en {host}:{port}. ¿Está abierto y con el "
                       "servidor WebSocket activado?", host=obs.host, port=obs.port),
                    None, _instr_obs())
    return _res("obs", "error", tr("No pude conectar con OBS: {error}", error=err), None,
                _instr_obs())


def _check_scene(ctx: Context, scan: _Scan, **_) -> CheckResult:
    if scan.state in ("disconnected", "lost"):
        return _res("scene", "error", tr("No se puede revisar la escena: OBS no está conectado"))
    if scan.state == "no_scene":
        return _res("scene", "error",
                    tr("No existe la escena «{scene}» en OBS", scene=config.SCENE_NAME),
                    None, _instr_escena())
    if scan.missing_cameras:
        return _res("scene", "error",
                    tr("Faltan cámaras en la escena: {names}", names=", ".join(scan.missing_cameras)),
                    None, _instr_escena())
    if scan.missing_companions:
        return _res("scene", "warn",
                    tr("Faltan en la escena: {names} (las cámaras funcionan igual)",
                       names=", ".join(scan.missing_companions)),
                    tr("Arreglar"),
                    tr("«Arreglar» crea esos elementos vacíos y ocultos en la escena "
                       "«{scene}». No cambia nada más de la escena.", scene=config.SCENE_NAME))
    return _res("scene", "ok",
                tr("«{scene}» tiene las 10 cámaras, Borde y Marco", scene=config.SCENE_NAME))


def _image_problem(ctx: Context, name: str) -> str | None:
    """None si la imagen del acompañante existe en esta PC; si no, qué le pasa."""
    ruta = ctx.obs.get_image_path(name)
    if not ruta:
        return tr("{name} sin imagen asignada", name=name)
    if not Path(ruta).is_file():
        return tr("{name}: la imagen no existe en esta PC ({path})", name=name, path=ruta)
    return None


def _bundled_image(ctx: Context, name: str) -> Path | None:
    """`<carpeta de la app>/assets/<nombre>.png`, si existe."""
    p = Path(ctx.assets_dir) / f"{name}.png"
    return p if p.is_file() else None


def _check_companion_images(ctx: Context, scan: _Scan, **_) -> CheckResult:
    if scan.state != "ok":
        return _res("companion_images", "warn", tr("Sin revisar: OBS no está conectado"))
    problemas: dict[str, str] = {}
    for name in config.COMPANIONS_V1:
        if name in scan.found:
            p = _image_problem(ctx, name)
            if p:
                problemas[name] = p
    if not ctx.obs.connected:   # se cayó justo al leer las rutas
        return _res("companion_images", "warn", tr("Sin revisar: se perdió la conexión con OBS"))
    if not problemas:
        return _res("companion_images", "ok", tr("Las imágenes de los acompañantes existen"))
    arreglables = [n for n in problemas if _bundled_image(ctx, n)]
    instr = ""
    if arreglables:
        instr = tr("«Arreglar» le pone a {names} la imagen de la carpeta de la app "
                   "({folder}); el cambio se hace en vivo, con OBS abierto.",
                   names=_join_and(arreglables), folder=ctx.assets_dir) + " "
    for n in problemas:
        if n not in arreglables:
            instr += tr("{name} no tiene imagen en la carpeta de la app: copia {name}.png en "
                        "{folder} y pulsa «Arreglar», elígela con «Buscar… {name}», o ponla en "
                        "OBS (clic derecho en «{name}» → Propiedades).",
                        name=n, folder=ctx.assets_dir) + " "
    return _res("companion_images", "warn", "; ".join(problemas.values()),
                tr("Arreglar") if arreglables else None, instr.strip())


def _check_portraits(ctx: Context, **_) -> CheckResult:
    n = len(ctx.portraits.as_dict())
    return _res("portraits", "ok", tr("Los 10 ubicados ({n} afinados con tus clicks)", n=n))


def run_checks(ctx: Context, *, is_running=paths.is_running) -> list[CheckResult]:
    """Todas las revisiones, en orden. No modifica nada y no lanza excepciones."""
    try:
        scan = _scan_scene(ctx.obs)
    except Exception as e:  # noqa: BLE001
        scan = _Scan("lost", error=f"{type(e).__name__}: {e}")
    plan = [
        ("dota", _check_dota), ("gsi_cfg", _check_gsi_cfg), ("gsi_data", _check_gsi_data),
        ("keys", _check_keys), ("obs", _check_obs), ("scene", _check_scene),
        ("companion_images", _check_companion_images), ("portraits", _check_portraits),
    ]
    results = []
    for cid, fn in plan:
        try:
            results.append(fn(ctx, scan=scan, is_running=is_running))
        except Exception as e:  # noqa: BLE001 - una revisión nunca tumba a las demás
            results.append(_res(cid, "error", f"{type(e).__name__}: {e}"))
    return results


# ---------- arreglos ----------

def _fix_gsi_cfg(ctx: Context, is_running) -> str:
    if ctx.dota is None:
        raise FixRefused(tr("Primero hay que elegir la carpeta de Dota"))
    if not paths.is_dota_dir(ctx.dota):
        raise FixRefused(tr("Esa carpeta no parece ser Dota 2 (falta game\\dota): "
                            "elige la carpeta correcta con «Buscar…»"))
    destino = paths.gsi_cfg_path(ctx.dota)
    try:
        if destino.is_file():   # solo nuestro archivo: se guarda copia por si tenía algo propio
            ctx.storage.backup(destino)
        gsi_cfg.write_cfg(destino)
    except OSError as e:
        raise FixRefused(tr("No pude escribir el archivo GSI: {error}", error=e)) from e
    msg = tr("Listo: escribí {path}.", path=destino)
    if is_running(DOTA_EXE):
        msg += " " + tr("Reinicia Dota para que lo lea.")
    return msg


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _fix_keys(ctx: Context, is_running) -> str:
    if ctx.keys_file is None or not Path(ctx.keys_file).is_file():
        raise FixRefused(tr("No encontré el archivo de teclas de Dota (dotakeys_personal.lst)"))
    if is_running(DOTA_EXE):   # Dota reescribe este archivo al cerrar: editarlo abierto no sirve
        raise FixRefused(tr("Cierra Dota por completo y vuelve a intentar"))
    keys_file = Path(ctx.keys_file)
    try:
        original = _read_keys_text(keys_file)
        nuevo = fix_keys_text(original)
    except (OSError, ValueError) as e:
        raise FixRefused(tr("No pude arreglar el archivo de teclas: {error}", error=e)) from e
    if nuevo == original:
        raise FixRefused(tr("Las teclas de espectador ya estaban bien; no cambié nada"))
    if missing_slots(parse_player_keys(nuevo)):   # comprobar ANTES de escribir
        raise FixRefused(tr("No pude asignar todas las teclas de espectador; no cambié nada"))
    try:
        copia = ctx.storage.backup(keys_file)
        _atomic_write(keys_file, nuevo.encode("utf-8", errors="surrogateescape"))
    except OSError as e:
        raise FixRefused(tr("No pude guardar el archivo de teclas: {error}", error=e)) from e
    return tr("Listo: arreglé las teclas de espectador. Copia de seguridad: {backup}. "
              "Si al abrir Steam aparece un conflicto de sincronización (Steam Cloud), "
              "elige la versión local.", backup=copia)


def _fix_scene(ctx: Context) -> str:
    scan = _scan_scene(ctx.obs)
    if scan.state != "ok":
        raise FixRefused(tr("No puedo arreglar la escena: OBS no está conectado o falta la escena "
                            "«{scene}»", scene=config.SCENE_NAME))
    faltan = scan.missing_companions
    if not faltan:
        raise FixRefused(tr("No falta ningún acompañante en la escena"))
    creados = []
    for name in faltan:
        if not ctx.obs.create_companion(name, config.SCENE_NAME):
            if creados:
                raise FixRefused(tr("OBS no me dejó crear «{name}» (ya creé: {done})",
                                    name=name, done=", ".join(creados)))
            raise FixRefused(tr("OBS no me dejó crear «{name}»", name=name))
        creados.append(name)
    return tr("Listo: creé {names} en la escena «{scene}», vacío y oculto. "
              "Ponle su imagen en OBS si hace falta.",
              names=", ".join(creados), scene=config.SCENE_NAME)


def _fix_companion_images(ctx: Context) -> str:
    scan = _scan_scene(ctx.obs)
    if scan.state != "ok":
        raise FixRefused(tr("No puedo arreglar las imágenes: OBS no está conectado"))
    con_problema = [n for n in config.COMPANIONS_V1
                    if n in scan.found and _image_problem(ctx, n) is not None]
    if not con_problema:
        raise FixRefused(tr("Los acompañantes ya tienen imagen"))
    hechos = []
    for name in con_problema:
        img = _bundled_image(ctx, name)
        if img is None:
            continue
        if not ctx.obs.set_image_path(name, str(img)):
            if hechos:
                raise FixRefused(tr("OBS no me dejó cambiar la imagen de {name} (ya cambié: {done})",
                                    name=name, done=", ".join(hechos)))
            raise FixRefused(tr("OBS no me dejó cambiar la imagen de {name}", name=name))
        hechos.append(name)
    if not hechos:
        faltan = ", ".join(f"{n}.png" for n in con_problema)
        raise FixRefused(tr("No encuentro {files} en la carpeta de la app ({folder}). "
                            "Cópialo ahí y vuelve a pulsar «Arreglar», o elige la imagen con «Buscar…».",
                            files=faltan, folder=ctx.assets_dir))
    cambios = "; ".join(tr("{name} ahora usa {path}", name=n, path=Path(ctx.assets_dir) / (n + ".png"))
                        for n in hechos)
    return tr("Listo: {changes}.", changes=cambios)


def apply_fix(check_id: str, ctx: Context, *, is_running=paths.is_running) -> str:
    """Aplica el arreglo de una revisión y devuelve el mensaje para el usuario.
    Lanza FixRefused (con el motivo) cuando no se puede arreglar."""
    if check_id == "gsi_cfg":
        return _fix_gsi_cfg(ctx, is_running)
    if check_id == "keys":
        return _fix_keys(ctx, is_running)
    if check_id == "scene":
        return _fix_scene(ctx)
    if check_id == "companion_images":
        return _fix_companion_images(ctx)
    raise FixRefused(tr("La revisión «{id}» no tiene un arreglo automático", id=check_id))
