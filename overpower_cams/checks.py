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

from . import config, gsi_cfg, paths
from .dota_keys import fix_keys_text, link_enabled, missing_slots, parse_player_keys
from .i18n import tr
from .obs_link import BORDE, ObsLink, SceneReport
from .portraits import PortraitModel
from .scene_builder import SceneBuildError
from .storage import Settings, Storage

DOTA_EXE = "dota2.exe"
MASK_ASSET = "Mascara camara.png"        # máscara de Camara/Foto, en assets/
FONDO_ASSET = "Marco sin camara.png"     # imagen de Fondo, en assets/
TEMPLATE_SCENE = "1 Hard carry"          # plantilla para crear escenas de jugador

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
        "Para usar la colección Camaraman en OBS:\n"
        "1. En OBS ve a Colección de escenas → Importar.\n"
        "2. Agrega el archivo .json de la colección Camaraman y confirma.\n"
        "3. Luego Colección de escenas → elige la colección importada.\n"
        "Si ya la tenías, revisa que la escena principal se llame como está en Ajustes (por defecto «Juego»).")


def _instr_move_filters(scene: str) -> str:
    return tr(
        "Los filtros mueven la caja de habilidades según cuántas tenga el jugador.\n"
        "1. Instala el plugin Move Transition (move-transition 3.x) y reinicia OBS.\n"
        "2. En la escena «{scene}», clic derecho → Filtros, y agrega tres filtros «Mover fuente» "
        "(Move Source) llamados exactamente H 4 habilidades, H 5 habilidades y H 6 habilidades.\n"
        "3. En cada uno pon la posición y la escala que quieres para esa cantidad de habilidades.\n"
        "4. Pulsa «Revisar todo de nuevo».", scene=scene)


def check_title(cid: str) -> str:
    """Título de cada revisión, en el idioma de la interfaz."""
    titles = {
        "dota": tr("Dota instalado"),
        "gsi_cfg": tr("Archivo GSI"),
        "gsi_data": tr("Datos de Dota llegando"),
        "keys": tr("Teclas de espectador"),
        "obs": tr("OBS y WebSocket"),
        "scene": tr("Escena de OBS"),
        "player_scenes": tr("Escenas de jugador"),
        "move_filters": tr("Filtros de habilidades"),
        "scene_images": tr("Imágenes de las escenas"),
        "portraits": tr("Retratos"),
    }
    return titles[cid]


def _short_list(names: list[str], limit: int = 5) -> str:
    """"A, B, C" o, si hay muchos, "A, B, C, D, E y 7 más"."""
    if len(names) <= limit:
        return ", ".join(names)
    return tr("{names} y {n} más", names=", ".join(names[:limit]), n=len(names) - limit)


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
    assets_dir: Path        # imágenes de la app (Borde.png, Mascara camara.png…), en _internal\assets del .exe
    portraits: PortraitModel


def _res(cid, status, detail, fix_label=None, instructions=None) -> CheckResult:
    return CheckResult(cid, status, check_title(cid), detail, fix_label, instructions)


# ---------- OBS: lectura de la colección (solo lectura) ----------

@dataclass
class _Scan:
    state: str                              # "ok" | "disconnected" | "lost"
    report: SceneReport | None = None
    error: str = ""

    @property
    def main_found(self) -> bool:
        return self.report is not None and self.report.main_found


def _scan_scene(obs: ObsLink) -> _Scan:
    """Lee la colección SIN apagar nada (`refresh_items`; `load_items()` apagaría lo que está al aire)."""
    if not obs.connected:
        return _Scan("disconnected")
    try:
        return _Scan("ok", obs.refresh_items())
    except Exception as e:  # noqa: BLE001 - conexión caída, se informa como pérdida
        return _Scan("lost", error=f"{type(e).__name__}: {e}")


def _unchecked(cid: str, ctx: Context, scan: _Scan) -> CheckResult | None:
    """Resultado "sin revisar" si no hay colección que mirar; None si sí se puede revisar."""
    if scan.state != "ok":
        return _res(cid, "warn", tr("Sin revisar: OBS no está conectado"))
    if not scan.main_found:
        return _res(cid, "warn", tr("Sin revisar: no existe la escena «{scene}»", scene=ctx.obs.main_scene))
    return None


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
    main = ctx.obs.main_scene
    if scan.state != "ok":
        return _res("scene", "error", tr("No se puede revisar la escena: OBS no está conectado"))
    if not scan.main_found:
        return _res("scene", "error", tr("No existe la escena «{scene}» en OBS", scene=main),
                    None, _instr_escena())
    if not scan.report.borde:
        return _res("scene", "warn",
                    tr("Falta {name} en la escena «{scene}» (las escenas de jugador funcionan igual)",
                       name=BORDE, scene=main),
                    tr("Arreglar"),
                    tr("«Arreglar» crea {name} vacío y oculto en la escena «{scene}». "
                       "No cambia nada más de la escena.", name=BORDE, scene=main))
    return _res("scene", "ok", tr("«{scene}» existe y tiene el {name}", scene=main, name=BORDE))


def _check_player_scenes(ctx: Context, scan: _Scan, **_) -> CheckResult:
    if (r := _unchecked("player_scenes", ctx, scan)) is not None:
        return r
    rep = scan.report
    partes = []
    if rep.missing_scenes:
        partes.append(tr("Faltan escenas: {names}", names=", ".join(rep.missing_scenes)))
    faltan = [src for scene in config.PLAYER_SCENES for src in rep.missing_sources.get(scene, [])]
    if faltan:
        partes.append(tr("Faltan fuentes: {names}", names=", ".join(faltan)))
    if not partes:
        return _res("player_scenes", "ok", tr("Las 10 escenas de jugador tienen sus 4 fuentes"))
    if rep.missing_scenes:
        return _res("player_scenes", "warn", "; ".join(partes), tr("Crear escenas"),
                    tr("«Crear escenas» copia la escena «{template}» (con sus 4 fuentes, filtros y "
                       "posición) para cada escena que falta y la agrega apagada a «{scene}». No toca "
                       "las escenas que ya existen. Las fuentes que faltan en escenas existentes se "
                       "agregan a mano en OBS.", template=TEMPLATE_SCENE, scene=ctx.obs.main_scene))
    return _res("player_scenes", "warn", "; ".join(partes), None,
                tr("Agrega en OBS las fuentes que faltan (se llaman «Camara · escena», «Foto · escena», "
                   "«Fondo · escena» y «Nombre · escena»), o copia otra escena de jugador."))


def _check_move_filters(ctx: Context, scan: _Scan, **_) -> CheckResult:
    if (r := _unchecked("move_filters", ctx, scan)) is not None:
        return r
    main = ctx.obs.main_scene
    faltan = [name for n, name in config.HUD_FILTERS.items() if scan.report.filters.get(n) is None]
    if not faltan:
        return _res("move_filters", "ok", tr("Los filtros H 4/5/6 habilidades están en «{scene}»", scene=main))
    return _res("move_filters", "warn",
                tr("Falta el plugin Move Transition o los filtros H 4/5/6 habilidades en «{scene}»: "
                   "{names}", scene=main, names=", ".join(faltan)),
                None, _instr_move_filters(main))


@dataclass
class _ImageProblem:
    kind: str                # "borde" | "mask" | "fondo"
    source: str              # fuente (Borde, Camara · X, Fondo · X)
    filter: str | None       # solo máscaras: nombre del filtro
    asset: str               # imagen empaquetada que lo arregla


def _is_broken(path) -> bool:
    return not path or not Path(path).is_file()


def _image_problems(ctx: Context, report: SceneReport) -> list[_ImageProblem]:
    """Rutas vacías o que no existen en esta PC: Borde, máscaras de Camara/Foto y archivo de Fondo.
    Solo lee de OBS."""
    obs = ctx.obs
    out: list[_ImageProblem] = []
    if report.borde and _is_broken(obs.get_image_path(BORDE)):
        out.append(_ImageProblem("borde", BORDE, None, "Borde.png"))
    for scene in config.PLAYER_SCENES:
        if scene in report.missing_scenes:
            continue
        faltan = report.missing_sources.get(scene, [])
        for kind in ("Camara", "Foto"):
            src = config.source_name(kind, scene)
            if src in faltan:
                continue
            for fname, path in obs.get_mask_paths(src) or []:
                if _is_broken(path):
                    out.append(_ImageProblem("mask", src, fname, MASK_ASSET))
        src = config.source_name("Fondo", scene)
        if src not in faltan:
            if _is_broken(obs.get_image_path(src)):
                out.append(_ImageProblem("fondo", src, None, FONDO_ASSET))
    return out


def _bundled(ctx: Context, asset: str) -> Path | None:
    p = Path(ctx.assets_dir) / asset
    return p if p.is_file() else None


def _check_scene_images(ctx: Context, scan: _Scan, **_) -> CheckResult:
    if (r := _unchecked("scene_images", ctx, scan)) is not None:
        return r
    problemas = _image_problems(ctx, scan.report)
    if not ctx.obs.connected:   # se cayó justo al leer las rutas
        return _res("scene_images", "warn", tr("Sin revisar: se perdió la conexión con OBS"))
    if not problemas:
        return _res("scene_images", "ok", tr("Las imágenes del Borde, las máscaras y los fondos existen"))
    nombres = list(dict.fromkeys(p.source for p in problemas))
    arreglables = [p for p in problemas if _bundled(ctx, p.asset)]
    instr = ""
    if arreglables:
        instr = tr("«Arreglar» apunta esas imágenes a las de la carpeta de la app ({folder}); el cambio "
                   "se hace en vivo, con OBS abierto. Las rutas que sí existen no se tocan.",
                   folder=ctx.assets_dir) + " "
    for asset in dict.fromkeys(p.asset for p in problemas):
        if _bundled(ctx, asset) is None:
            instr += tr("Falta {file} en la carpeta de la app ({folder}): cópiala ahí y pulsa "
                        "«Arreglar», o ponla a mano en OBS.", file=asset, folder=ctx.assets_dir) + " "
    return _res("scene_images", "warn",
                tr("Imágenes que están vacías o no existen en esta PC: {names}", names=_short_list(nombres)),
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
        ("player_scenes", _check_player_scenes), ("move_filters", _check_move_filters),
        ("scene_images", _check_scene_images), ("portraits", _check_portraits),
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
    if scan.state != "ok" or not scan.main_found:
        raise FixRefused(tr("No puedo arreglar la escena: OBS no está conectado o falta la escena "
                            "«{scene}»", scene=ctx.obs.main_scene))
    if scan.report.borde:
        raise FixRefused(tr("No falta nada en la escena"))
    if not ctx.obs.create_companion(BORDE, ctx.obs.main_scene):
        raise FixRefused(tr("OBS no me dejó crear «{name}»", name=BORDE))
    return tr("Listo: creé {name} en la escena «{scene}», vacío y oculto. "
              "Ponle su imagen en OBS si hace falta.", name=BORDE, scene=ctx.obs.main_scene)


def _fix_player_scenes(ctx: Context) -> str:
    scan = _scan_scene(ctx.obs)
    if scan.state != "ok" or not scan.main_found:
        raise FixRefused(tr("No puedo crear las escenas: OBS no está conectado o falta la escena "
                            "«{scene}»", scene=ctx.obs.main_scene))
    rep = scan.report
    faltan = list(rep.missing_scenes)
    if not faltan:
        raise FixRefused(tr("No falta ninguna escena de jugador"))
    if TEMPLATE_SCENE in rep.missing_scenes or rep.missing_sources.get(TEMPLATE_SCENE):
        raise FixRefused(tr("No puedo crear las escenas porque falta la plantilla «{template}» o está "
                            "incompleta. Arréglala en OBS y vuelve a intentar.", template=TEMPLATE_SCENE))
    try:
        creadas = ctx.obs.create_player_scenes(faltan)
    except SceneBuildError as e:
        hechas = ", ".join(e.created) if e.created else "—"
        raise FixRefused(tr("OBS no me dejó crear la escena «{scene}» ({error}). Ya creé: {done}. "
                            "«{scene}» pudo quedar a medias en OBS: revísala o bórrala.",
                            scene=e.target, error=e.cause, done=hechas)) from e
    except OSError as e:   # incluye ConnectionError
        raise FixRefused(tr("Se perdió la conexión con OBS: {error}", error=e)) from e
    if not creadas:
        raise FixRefused(tr("Esas escenas ya existen en OBS pero no están dentro de «{scene}»: "
                            "agrégalas ahí a mano ({names})", scene=ctx.obs.main_scene,
                            names=", ".join(faltan)))
    return tr("Listo: creé {names}, apagadas y copiadas de «{template}».",
              names=", ".join(creadas), template=TEMPLATE_SCENE)


def _fix_scene_images(ctx: Context) -> str:
    scan = _scan_scene(ctx.obs)
    if scan.state != "ok" or not scan.main_found:
        raise FixRefused(tr("No puedo arreglar las imágenes: OBS no está conectado o falta la escena "
                            "«{scene}»", scene=ctx.obs.main_scene))
    problemas = _image_problems(ctx, scan.report)
    if not problemas:
        raise FixRefused(tr("Todas las imágenes ya existen; no cambié nada"))
    arreglables = [p for p in problemas if _bundled(ctx, p.asset)]
    if not arreglables:
        faltan = ", ".join(dict.fromkeys(p.asset for p in problemas))
        raise FixRefused(tr("No encuentro {files} en la carpeta de la app ({folder}). "
                            "Cópialo ahí y vuelve a pulsar «Arreglar», o ponlo a mano en OBS.",
                            files=faltan, folder=ctx.assets_dir))
    hechos: list[str] = []
    for p in arreglables:
        img = str(_bundled(ctx, p.asset))
        if p.kind == "mask":
            ok = ctx.obs.set_mask_path(p.source, p.filter, img)
        else:
            ok = ctx.obs.set_image_path(p.source, img)
        if not ok:
            if hechos:
                raise FixRefused(tr("OBS no me dejó cambiar la imagen de {name} (ya cambié: {done})",
                                    name=p.source, done=_short_list(hechos)))
            raise FixRefused(tr("OBS no me dejó cambiar la imagen de {name}", name=p.source))
        hechos.append(p.source)
    return tr("Listo: cambié la imagen de {names}.", names=_short_list(list(dict.fromkeys(hechos))))


def apply_fix(check_id: str, ctx: Context, *, is_running=paths.is_running) -> str:
    """Aplica el arreglo de una revisión y devuelve el mensaje para el usuario.
    Lanza FixRefused (con el motivo) cuando no se puede arreglar."""
    if check_id == "gsi_cfg":
        return _fix_gsi_cfg(ctx, is_running)
    if check_id == "keys":
        return _fix_keys(ctx, is_running)
    if check_id == "scene":
        return _fix_scene(ctx)
    if check_id == "player_scenes":
        return _fix_player_scenes(ctx)
    if check_id == "scene_images":
        return _fix_scene_images(ctx)
    raise FixRefused(tr("La revisión «{id}» no tiene un arreglo automático", id=check_id))
