"""Conexión con OBS (obs-websocket vía obsws-python).

Busca cámaras y acompañantes en cualquier lugar de la escena (también dentro de grupos), cambiar de cámara sin flash negro,
mostrar los acompañantes solo con una cámara al aire y recuperarse si OBS se reinicia.
"""
import threading
import time
from dataclasses import dataclass, field

import obsws_python
import websocket
from obsws_python.error import OBSSDKError, OBSSDKRequestError, OBSSDKTimeoutError

from . import config
from .i18n import tr

ITEMS_REFRESH_S = 2.0        # tope de frecuencia al releer la escena cuando falta una cámara
OBS_TIMEOUT_S = 5.0          # tope de espera por conexión/respuesta (nunca bloquear al motor)
_RESOURCE_NOT_FOUND = 600    # código de obs-websocket: la escena/entrada no existe

ALL_CAMERAS = config.CAMERAS_TEAM1 + config.CAMERAS_TEAM2


@dataclass
class ItemReport:
    """Resultado de `load_items()`: qué falta en la escena de OBS."""
    missing_cameras: list[str] = field(default_factory=list)
    missing_companions: list[str] = field(default_factory=list)
    scene_found: bool = True


def classify_error(exc: BaseException) -> str:
    """Convierte la excepción de conexión de ReqClient en "auth", "refused" u otro texto."""
    if isinstance(exc, ConnectionRefusedError):
        return "refused"
    # Contraseña mala: OBS cierra el socket al identificar (WebSocketConnectionClosed) o
    # obsws-python lanza OBSSDKError ("failed to identify client...", "no password provided").
    if isinstance(exc, websocket.WebSocketConnectionClosedException):
        return "auth"
    if isinstance(exc, OBSSDKError) and not isinstance(exc, (OBSSDKRequestError, OBSSDKTimeoutError)):
        return "auth"
    return f"{type(exc).__name__}: {exc}"


class ObsLink:
    """Enlace con OBS. Todas las llamadas al cliente van bajo un lock (no es thread-safe)."""

    def __init__(self, host: str, port: int, password: str, *,
                 client_factory=obsws_python.ReqClient, on_event=lambda text: None,
                 clock=time.monotonic):
        self.host = host
        self.port = port
        self.password = password
        self._factory = client_factory
        self._emit = on_event
        self._clock = clock
        self._last_refresh: float | None = None  # cuándo se releyó la escena por última vez
        self._lock = threading.RLock()
        self._client = None
        self._items: dict[str, tuple[str, int]] = {}
        self._last_camera: str | None = None   # cámara encendida hoy en OBS
        self.connected = False
        self.error: str | None = None
        self.pending_camera: str | None = None  # última cámara pedida y NO entregada a OBS
        self._has_pending = False               # distingue "ocultar" (None) de "sin pedido"
        self._reconnect_lock = threading.Lock()  # una sola reconexión a la vez
        self.report: ItemReport | None = None   # resultado del último `load_items()`

    # --- conexión ----------------------------------------------------------
    def _build_client(self):
        """Abre el cliente SIN tomar el lock (puede tardar segundos). -> (cliente, error)."""
        try:
            return self._factory(host=self.host, port=self.port,
                                 password=self.password, timeout=OBS_TIMEOUT_S), None
        except Exception as e:  # noqa: BLE001 - se clasifica y se informa
            return None, classify_error(e)

    def connect(self) -> bool:
        client, err = self._build_client()
        with self._lock:
            self._close()
            self._client = client
            self.connected = client is not None
            self.error = err
        if client is not None:
            self._emit(tr("Conectado a OBS en {host}:{port}", host=self.host, port=self.port))
        return client is not None

    def close(self) -> None:
        """Cierra la conexión (p. ej. al cambiar puerto o contraseña en Ajustes)."""
        with self._lock:
            self._close()
            self.connected = False

    def ping(self) -> bool:
        """Pregunta algo trivial a OBS para notar una conexión caída aunque no haya cambios de
        cámara. Devuelve si sigue conectado; si se cayó, queda `connected = False` ("lost")."""
        with self._lock:
            if not self.connected or self._client is None:
                return False
            try:
                self._client.get_version()
            except OBSSDKRequestError:
                return True            # OBS respondió (aunque sea con un error)
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                return False
            return True

    def _close(self):
        client, self._client = self._client, None
        if client is not None:
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    def _fail(self, exc: BaseException):
        """Una llamada al cliente falló: se da por perdida la conexión (y los IDs)."""
        # Nunca "auth": esa clasificación es solo del momento de conectar.
        self.connected = False
        self.error = "lost"
        self._emit(tr("Se perdió la conexión con OBS ({error})", error=f"{type(exc).__name__}: {exc}"))

    # --- escena ------------------------------------------------------------
    def find_scene_items(self) -> dict[str, tuple[str, int]]:
        """nombre -> (contenedor, item_id) de todo lo que hay en la escena, también dentro de grupos.
        Para un ítem dentro de un grupo, OBS pide el nombre del GRUPO como contenedor."""
        with self._lock:
            found: dict[str, tuple[str, int]] = {}
            for it in self._client.get_scene_item_list(config.SCENE_NAME).scene_items:
                found.setdefault(it["sourceName"], (config.SCENE_NAME, it["sceneItemId"]))
                if it.get("isGroup"):
                    subs = self._client.get_group_scene_item_list(it["sourceName"]).scene_items
                    for sub in subs:
                        found.setdefault(sub["sourceName"], (it["sourceName"], sub["sceneItemId"]))
            return found

    def load_items(self) -> ItemReport:
        """Carga los IDs de cámaras y acompañantes y apaga todo. Si falla la conexión,
        marca `connected = False` y relanza la excepción."""
        with self._lock:
            self._items = {}
            self._last_camera = None
            try:
                try:
                    found = self.find_scene_items()
                except OBSSDKRequestError as e:
                    if e.code != _RESOURCE_NOT_FOUND:
                        raise
                    self.report = ItemReport(list(ALL_CAMERAS), list(config.COMPANIONS), False)
                    self._emit(tr("La escena '{scene}' no existe en OBS", scene=config.SCENE_NAME))
                    return self.report

                report = ItemReport(
                    missing_cameras=[n for n in ALL_CAMERAS if n not in found],
                    missing_companions=[n for n in config.COMPANIONS if n not in found],
                    scene_found=True,
                )
                for name in ALL_CAMERAS + config.COMPANIONS:
                    if name in found:
                        self._items[name] = found[name]
                self._hide_all()
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                raise
            self.report = report
            self._emit(tr("Fuentes de OBS cargadas"))
            return report

    def items_stale(self, found: dict[str, tuple[str, int]]) -> bool:
        """True si lo que hay hoy en la escena (`found`) no coincide con los IDs cargados."""
        wanted = {n: found[n] for n in ALL_CAMERAS + config.COMPANIONS if n in found}
        return wanted != self._items

    def refresh_items(self) -> ItemReport:
        """Vuelve a leer la escena y actualiza los IDs SIN apagar nada: `_last_camera` se
        conserva (load_items lo apaga todo). Si falla la conexión, marca `connected = False`
        y relanza la excepción."""
        with self._lock:
            self._last_refresh = self._clock()
            if not self.connected or self._client is None:
                return ItemReport(
                    [n for n in ALL_CAMERAS if n not in self._items],
                    [n for n in config.COMPANIONS if n not in self._items], True)
            try:
                try:
                    found = self.find_scene_items()
                except OBSSDKRequestError as e:
                    if e.code != _RESOURCE_NOT_FOUND:
                        raise
                    self._items = {}
                    self.report = ItemReport(list(ALL_CAMERAS), list(config.COMPANIONS), False)
                    return self.report
                self._items = {n: found[n] for n in ALL_CAMERAS + config.COMPANIONS if n in found}
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                raise
            self.report = ItemReport(
                missing_cameras=[n for n in ALL_CAMERAS if n not in self._items],
                missing_companions=[n for n in config.COMPANIONS if n not in self._items],
                scene_found=True)
            return self.report

    # --- conmutación -------------------------------------------------------
    def _set_enabled(self, name: str, enabled: bool):
        container, item_id = self._items[name]
        self._client.set_scene_item_enabled(container, item_id, enabled)

    def _set_companions(self, enabled: bool):
        for name in config.COMPANIONS:
            if name in self._items:
                self._set_enabled(name, enabled)

    def _hide_all(self):
        for cam in ALL_CAMERAS:
            if cam in self._items:
                self._set_enabled(cam, False)
        self._set_companions(False)
        self._last_camera = None

    def _remember(self, cam: str | None):
        self.pending_camera = cam
        self._has_pending = True

    def _refresh_if_due(self) -> bool:
        """Relee la escena si pasó ITEMS_REFRESH_S desde la última vez (así `apply` no se
        pone a escanear con cada cambio). False si la conexión se cayó al hacerlo."""
        now = self._clock()
        if self._last_refresh is not None and now - self._last_refresh < ITEMS_REFRESH_S:
            return True
        try:
            self.refresh_items()
        except Exception:  # noqa: BLE001 - refresh_items ya marcó la conexión como perdida
            return False
        return True

    def apply(self, cam: str | None, reason: str) -> None:
        """Enciende `cam` (None = ocultar todo). Cámara nueva antes de apagar la anterior;
        los acompañantes solo cambian al entrar/salir de "sin cámara". No lanza nunca y
        no espera a una reconexión en curso: si no hay conexión, o OBS falla, se marca
        `connected = False` y se guarda la cámara en `pending_camera`."""
        if not self.connected:           # sin lock: no esperar a una reconexión en curso
            self._remember(cam)
            return
        with self._lock:
            if not self.connected or self._client is None:
                self._remember(cam)
                return
            old = self._last_camera
            if cam == old:
                self.pending_camera, self._has_pending = None, False
                return
            if cam is not None and cam not in self._items:
                if not self._refresh_if_due():   # la conexión se cayó al releer la escena
                    self._remember(cam)
                    return
                if cam not in self._items:
                    # Sin esa cámara no hay nada que mostrar: se apaga la anterior y los acompañantes.
                    self._emit(tr("{cam} no está en la escena de OBS: se apaga la cámara anterior", cam=cam))
                    cam = None
                    if old is None:          # ya estaba todo apagado
                        self.pending_camera, self._has_pending = None, False
                        return
            try:
                self._emit(f"{old or tr('ninguna')} -> {cam or tr('oculto')}  {reason}")
                if cam:
                    self._set_enabled(cam, True)
                    if old is None:
                        self._set_companions(True)
                if old and old in self._items:
                    self._set_enabled(old, False)
                if not cam:
                    self._set_companions(False)
                self._last_camera = cam
                self.pending_camera, self._has_pending = None, False
            except Exception as e:  # noqa: BLE001
                self._remember(cam)
                self._fail(e)

    def ensure_connected(self, current_camera: str | None) -> bool:
        """Si no hay conexión: reconecta, recarga los IDs y reaplica la última cámara pedida
        (`pending_camera`, si la hay; si no, `current_camera`). Abrir el cliente se hace fuera
        del lock para que `apply` nunca espere; solo una reconexión a la vez."""
        if self.connected:
            return True
        if not self._reconnect_lock.acquire(blocking=False):
            return False                 # ya hay otra reconexión en curso
        try:
            client, err = self._build_client()
            if client is None:
                with self._lock:
                    self.error = err
                return False
            with self._lock:
                self._close()
                self._client = client
                try:
                    self.load_items()    # ya marca el fallo si OBS se cae otra vez
                except Exception:  # noqa: BLE001
                    return False
                self.connected = True
                self.error = None
                self._emit(tr("Reconectado a OBS en {host}:{port}", host=self.host, port=self.port))
                cam = self.pending_camera if self._has_pending else current_camera
                self.apply(cam, tr("reconexión"))
                return self.connected
        finally:
            self._reconnect_lock.release()

    # --- imágenes de los acompañantes -------------------------------------
    def get_image_path(self, name: str) -> str | None:
        with self._lock:
            if not self.connected or self._client is None:
                return None
            try:
                settings = self._client.get_input_settings(name).input_settings
            except OBSSDKRequestError:
                return None            # la entrada no existe
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                return None
            return settings.get("file")

    def set_image_path(self, name: str, path: str) -> bool:
        with self._lock:
            if not self.connected or self._client is None:
                return False
            try:
                self._client.set_input_settings(name, {"file": path}, True)
            except Exception as e:  # noqa: BLE001
                if isinstance(e, OBSSDKRequestError):
                    self._emit(tr("OBS rechazó cambiar la imagen de {name} ({error})", name=name, error=e))
                else:
                    self._fail(e)
                return False
            return True

    def create_companion(self, name: str) -> bool:
        """Crea el acompañante (fuente de imagen) en la escena, oculto, y lo registra."""
        with self._lock:
            if not self.connected or self._client is None:
                return False
            try:
                res = self._client.create_input(config.SCENE_NAME, name, "image_source", {}, False)
                self._items[name] = (config.SCENE_NAME, res.scene_item_id)
                if self._last_camera is not None:   # acompañantes visibles solo con cámara al aire
                    self._set_enabled(name, True)
            except Exception as e:  # noqa: BLE001
                if isinstance(e, OBSSDKRequestError):
                    self._emit(tr("OBS rechazó crear {name} ({error})", name=name, error=e))
                else:
                    self._fail(e)
                return False
            self._emit(tr("Creado {name} en la escena '{scene}'", name=name, scene=config.SCENE_NAME))
            return True
