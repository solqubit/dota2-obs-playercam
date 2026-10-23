"""Arranque de la app de escritorio: arma el motor, OBS, el servidor GSI, la entrada local
y la ventana. Uso: `python -m overpower_cams.app`."""
from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

import obsws_python
from PySide6.QtWidgets import QApplication, QMessageBox

from . import checks, config, local_input as local_input_mod, paths
from .dota_keys import read_player_keys
from .engine import Engine
from .gsi_server import GsiServer, PortInUse
from .i18n import detect_default, set_language, tr
from .gui.events import EventBus
from .gui.main_window import MainWindow
from .local_input import LocalInput
from .obs_link import ObsLink
from .portraits import PortraitModel
from .storage import LiveState, Settings, Storage

ERROR_LOG_NAME = "error.log"
_AUTO = object()
_crash_shown = False   # el aviso de error inesperado se muestra una sola vez por sesión


def _scene_to_v1_camera(scene):
    """Puente temporal hasta la Task 5: el ObsLink de v1 solo conoce las cámaras CAM_EQx_y."""
    if scene in config.PLAYER_SCENES:
        return (config.CAMERAS_TEAM1 + config.CAMERAS_TEAM2)[config.PLAYER_SCENES.index(scene)]
    return scene


class ObsSink:
    """Destino de cámaras del motor: reenvía al ObsLink actual, que cambia si en Ajustes se
    cambia el puerto o la contraseña. Cambiar `obs` es una asignación atómica."""

    def __init__(self, obs: ObsLink | None = None):
        self.obs = obs

    def apply(self, scene, reason, abilities=4) -> None:
        obs = self.obs
        if obs is not None:
            obs.apply(_scene_to_v1_camera(scene), reason, abilities)

    def retrigger(self, scene, abilities) -> None:
        obs = self.obs
        if obs is not None:
            obs.retrigger(scene, abilities)


def legacy_input_map() -> Path:
    """`input_map.json` de la versión anterior (solo consola): junto al .exe
    empaquetado, o en la raíz del repositorio sin empaquetar."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "input_map.json"
    return Path(__file__).resolve().parent.parent / "input_map.json"


def resolve_dota(settings: Settings, steam: Path | None) -> Path | None:
    """La carpeta elegida en Ajustes si existe en disco; si no, la que se encuentra en Steam."""
    if settings.dota_dir and Path(settings.dota_dir).is_dir():
        return Path(settings.dota_dir)
    return paths.find_dota(steam)


@dataclass
class AppParts:
    storage: Storage
    settings: Settings
    state: LiveState
    portraits: PortraitModel
    steam: Path | None
    events: EventBus
    sink: ObsSink
    engine: Engine
    gsi: GsiServer
    local_input: LocalInput
    obs_client_factory: object
    assets_dir: Path
    obs: ObsLink | None = field(default=None)

    def make_ctx(self, obs: ObsLink) -> checks.Context:
        return checks.Context(
            storage=self.storage, settings=self.settings, steam=self.steam,
            dota=resolve_dota(self.settings, self.steam),
            keys_file=paths.dota_keys_file(self.steam), obs=obs,
            last_post_t=self.gsi.last_post_t, now=time.monotonic(),
            assets_dir=self.assets_dir, portraits=self.portraits)

    def make_obs(self, settings: Settings) -> ObsLink:
        """ObsLink nuevo con los ajustes dados; desde ya el motor manda las cámaras a él."""
        obs = ObsLink(config.OBS_HOST, settings.obs_port, settings.obs_password,
                      client_factory=self.obs_client_factory, on_event=self.events.post)
        self.obs = obs
        self.sink.obs = obs
        return obs


def build_app(storage: Storage, *, steam=_AUTO, obs_client_factory=obsws_python.ReqClient,
              gsi_port: int = config.GSI_PORT, keyboard_listener=None, mouse_listener=None,
              get_rect=local_input_mod.dota_client_rect, legacy_portraits=_AUTO) -> AppParts:
    """Arma todas las piezas sin arrancar nada (ni GSI, ni teclado/mouse, ni OBS).
    Requiere un QApplication ya creado (por el EventBus)."""
    if steam is _AUTO:
        steam = paths.steam_path()
    if legacy_portraits is _AUTO:
        legacy_portraits = legacy_input_map()
    events = EventBus()
    settings = storage.load_settings()
    state = storage.load_state(settings.default_radiant_team)
    portraits = PortraitModel(storage.load_portraits(legacy_portraits))

    def save_portraits():   # corre con el lock del motor: solo escribe el archivo
        try:
            storage.save_portraits(portraits.as_dict())
        except OSError as e:
            events.post("[ERROR] " + tr("no pude guardar los retratos: {error}", error=e))

    sink = ObsSink()
    engine = Engine(sink, portraits, read_player_keys(paths.dota_keys_file(steam)),
                    radiant_team=state.radiant_team, mode=state.mode,
                    on_event=events.post, on_learned=save_portraits)
    gsi = GsiServer(engine, port=gsi_port, on_event=events.post)
    local = LocalInput(engine, get_rect=get_rect, on_event=events.post,
                       keyboard_listener=keyboard_listener, mouse_listener=mouse_listener)
    parts = AppParts(storage=storage, settings=settings, state=state, portraits=portraits,
                     steam=steam, events=events, sink=sink, engine=engine, gsi=gsi,
                     local_input=local, obs_client_factory=obs_client_factory,
                     assets_dir=paths.resource_path("assets"))
    parts.make_obs(settings)
    return parts


def create_window(parts: AppParts, *, is_running=paths.is_running) -> MainWindow:
    return MainWindow(parts.make_ctx, parts.engine, parts.obs, parts.gsi, parts.local_input,
                      parts.storage, events=parts.events, obs_factory=parts.make_obs,
                      is_running=is_running)


def start_gsi_or_warn(gsi: GsiServer, parent=None) -> bool:
    """Abre el puerto GSI. Si está ocupado, avisa (con el texto del sistema) y devuelve False."""
    try:
        gsi.start()
    except PortInUse as e:
        QMessageBox.critical(parent, config.app_name(),
                             f"{e}.\n\n" + tr("Cierra lo que lo esté usando y vuelve a abrir la app."))
        return False
    return True


def write_error_log(exc_type, exc, tb, *, base: Path | None = None) -> Path | None:
    """Agrega al error.log de la carpeta de datos la fecha y el traceback. Devuelve la ruta
    del archivo, o None si ni eso se pudo escribir (nunca lanza)."""
    try:
        path = (base if base is not None else paths.app_data_dir()) / ERROR_LOG_NAME
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
            f.write("".join(traceback.format_exception(exc_type, exc, tb)))
            f.write("\n")
        return path
    except Exception:  # noqa: BLE001 - registrar el error nunca debe causar otro
        return None


def _show_crash(path: Path | None) -> None:
    if QApplication.instance() is None:
        return
    donde = (tr("Los detalles están en:\n{path}", path=path) if path
             else tr("No pude guardar los detalles."))
    QMessageBox.critical(None, config.app_name(),
                         tr("Ocurrió un error inesperado y la app puede no funcionar bien.") + "\n\n" + donde)


def handle_crash(exc_type, exc, tb, *, base: Path | None = None, show=_show_crash) -> Path | None:
    """Anota el error en error.log y avisa con un cuadro, solo la primera vez."""
    global _crash_shown
    path = write_error_log(exc_type, exc, tb, base=base)
    if not _crash_shown:
        _crash_shown = True
        try:
            show(path)
        except Exception:  # noqa: BLE001
            pass
    return path


def install_excepthook() -> None:
    """Las excepciones dentro de slots de Qt (que si no se pierden en el .exe sin consola)
    también se anotan en error.log."""
    sys.excepthook = lambda t, e, tb: handle_crash(t, e, tb)


def main() -> int:
    install_excepthook()
    try:
        return _run()
    except Exception:  # noqa: BLE001 - error al arrancar: dejar rastro y avisar
        handle_crash(*sys.exc_info())
        return 1


def apply_language(settings: Settings) -> str:
    """Fija el idioma de la interfaz: el de Ajustes o, si no hay, el de Windows. Va ANTES de
    crear cualquier texto. El detectado no se guarda hasta que se guarden los Ajustes."""
    code = settings.language or detect_default()
    set_language(code)
    return code


def _run() -> int:
    storage = Storage(paths.app_data_dir())
    apply_language(storage.load_settings())
    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setApplicationName(config.app_name())
    # Qt ya deja el proceso "DPI aware"; esto lo asegura antes de usar dota_client_rect.
    local_input_mod.set_dpi_awareness()
    parts = build_app(storage)
    if not start_gsi_or_warn(parts.gsi):
        return 1
    win = create_window(parts)
    if parts.state.mode == "auto":
        try:
            parts.local_input.start()
        except Exception as e:  # noqa: BLE001 - sin teclado/mouse la app sigue con GSI
            parts.events.post("[ERROR] " + tr("no pude escuchar teclado y mouse: {error}", error=e))
    win.show()   # si OBS rechaza la contraseña vacía, la ventana abre Ajustes una vez
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
