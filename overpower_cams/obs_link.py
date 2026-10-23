"""Conexión con OBS (obs-websocket vía obsws-python) para la colección Camaraman.

Las 10 escenas de jugador son escenas anidadas dentro de la escena principal (`Juego`); cada una trae
sus fuentes `Camara · X` y `Foto · X`. Esta clase enciende la escena del jugador al aire (ya en la posición
y escala de su filtro de habilidades, leídas de los filtros Move Source), elige cámara o foto dentro de ella,
muestra el Borde solo con una escena al aire, apunta los filtros al jugador y se recupera si OBS se reinicia.
"""
import threading
import time
from dataclasses import dataclass, field

import obsws_python
import websocket
from obsws_python.error import OBSSDKError, OBSSDKRequestError, OBSSDKTimeoutError

from . import config
from .config import source_name
from .i18n import tr
from .players import PlayerConfig, effective_use

ITEMS_REFRESH_S = 2.0        # tope de frecuencia al releer la colección cuando falta una escena
OBS_TIMEOUT_S = 5.0          # tope de espera por conexión/respuesta (nunca bloquear al motor)
_RESOURCE_NOT_FOUND = 600    # código de obs-websocket: la escena/entrada no existe

KINDS = ("Camara", "Foto", "Fondo", "Nombre")   # fuentes que lleva cada escena de jugador
BORDE = config.COMPANIONS[0]


@dataclass
class SceneReport:
    """Resultado de `load_items()`: qué falta en la colección de OBS."""
    main_found: bool = True
    missing_scenes: list[str] = field(default_factory=list)
    missing_sources: dict[str, list[str]] = field(default_factory=dict)
    # n habilidades -> {"pos": (x, y), "scale": (sx, sy)} leído del filtro, o None si falta
    filters: dict[int, dict | None] = field(default_factory=lambda: {n: None for n in config.HUD_FILTERS})
    borde: bool = True


def clamp_abilities(n: int | None) -> int:
    """Sin datos (None o 0) se usa 4; fuera del rango 4-6 se ajusta al extremo más cercano."""
    lo, hi = min(config.HUD_FILTERS), max(config.HUD_FILTERS)
    return min(max(n or lo, lo), hi)


def _preset(f: dict | None) -> dict | None:
    """Posición y escala de la configuración de un filtro Move Source (`pos`/`scale` con x e y)."""
    try:
        s = f["filterSettings"]
        return {"pos": (float(s["pos"]["x"]), float(s["pos"]["y"])),
                "scale": (float(s["scale"]["x"]), float(s["scale"]["y"]))}
    except (KeyError, TypeError, ValueError):
        return None


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
                 main_scene: str = config.DEFAULT_MAIN_SCENE,
                 players_provider=lambda: {},
                 client_factory=obsws_python.ReqClient, on_event=lambda text: None,
                 clock=time.monotonic):
        self.host = host
        self.port = port
        self.password = password
        self.main_scene = main_scene
        self._players = players_provider   # () -> {escena: PlayerConfig}
        self._factory = client_factory
        self._emit = on_event
        self._clock = clock
        self._last_refresh: float | None = None  # cuándo se releyó la colección por última vez
        self._lock = threading.RLock()
        self._client = None
        self._scene_ids: dict[str, int] = {}          # ítems de la escena principal (escenas y Borde)
        self._inner: dict[str, dict[str, int]] = {}   # escena de jugador -> {fuente: id}
        self._presets: dict[int, dict | None] = {n: None for n in config.HUD_FILTERS}
        self._warned: set[str] = set()                # escenas ausentes ya avisadas
        self._last_scene: str | None = None           # escena encendida hoy en OBS
        self.connected = False
        self.error: str | None = None
        self.pending_scene: str | None = None   # última escena pedida y NO entregada a OBS
        self._pending_abilities = 4
        self._last_abilities = 4                # últimas habilidades pedidas (para reaplicar)
        self._has_pending = False               # distingue "ocultar" (None) de "sin pedido"
        self._reconnect_lock = threading.Lock()  # una sola reconexión a la vez
        self.report: SceneReport | None = None  # resultado del último `load_items()`

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
        escena. Devuelve si sigue conectado; si se cayó, queda `connected = False` ("lost")."""
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

    # --- lectura de la colección --------------------------------------------
    def find_scene_items(self, scene: str | None = None) -> dict[str, tuple[str, int]]:
        """nombre -> (contenedor, item_id) de todo lo que hay en la escena (por defecto la principal),
        también dentro de grupos. Para un ítem dentro de un grupo, OBS pide el GRUPO como contenedor."""
        scene = scene or self.main_scene
        with self._lock:
            found: dict[str, tuple[str, int]] = {}
            for it in self._client.get_scene_item_list(scene).scene_items:
                found.setdefault(it["sourceName"], (scene, it["sceneItemId"]))
                if it.get("isGroup"):
                    subs = self._client.get_group_scene_item_list(it["sourceName"]).scene_items
                    for sub in subs:
                        found.setdefault(sub["sourceName"], (it["sourceName"], sub["sceneItemId"]))
            return found

    def _read_presets(self) -> dict[int, dict | None]:
        """Posición y escala de los filtros H 4/5/6 (None si el filtro falta)."""
        try:
            filters = self._client.get_source_filter_list(self.main_scene).filters
        except OBSSDKRequestError as e:
            if e.code != _RESOURCE_NOT_FOUND:
                raise
            filters = []
        by_name = {f.get("filterName"): f for f in filters}
        return {n: _preset(by_name.get(name)) for n, name in config.HUD_FILTERS.items()}

    def _scan(self) -> SceneReport:
        """Relee IDs y presets SIN apagar nada. Relanza los fallos de conexión."""
        main = self.main_scene
        try:
            items = self._client.get_scene_item_list(main).scene_items
        except OBSSDKRequestError as e:
            if e.code != _RESOURCE_NOT_FOUND:
                raise
            self._scene_ids, self._inner = {}, {}
            self._presets = {n: None for n in config.HUD_FILTERS}
            return SceneReport(False, list(config.PLAYER_SCENES), {}, dict(self._presets), False)
        ids: dict[str, int] = {}
        for it in items:
            ids.setdefault(it["sourceName"], it["sceneItemId"])
        missing_scenes = [s for s in config.PLAYER_SCENES if s not in ids]
        inner: dict[str, dict[str, int]] = {}
        missing_sources: dict[str, list[str]] = {}
        for scene in config.PLAYER_SCENES:
            if scene in missing_scenes:
                continue
            try:
                sub = {it["sourceName"]: it["sceneItemId"]
                       for it in self._client.get_scene_item_list(scene).scene_items}
            except OBSSDKRequestError as e:
                if e.code != _RESOURCE_NOT_FOUND:
                    raise
                sub = {}
            inner[scene] = sub
            faltan = [source_name(k, scene) for k in KINDS if source_name(k, scene) not in sub]
            if faltan:
                missing_sources[scene] = faltan
        presets = self._read_presets()
        self._scene_ids = {n: i for n, i in ids.items() if n in config.PLAYER_SCENES or n == BORDE}
        self._inner = inner
        self._presets = presets
        self._warned &= set(missing_scenes)
        return SceneReport(True, missing_scenes, missing_sources, dict(presets), BORDE in ids)

    def load_items(self) -> SceneReport:
        """Carga IDs y presets y apaga todo. Si falla la conexión, marca `connected = False`
        y relanza la excepción."""
        with self._lock:
            self._last_scene = None
            try:
                report = self._scan()
                if not report.main_found:
                    self.report = report
                    self._emit(tr("La escena '{scene}' no existe en OBS", scene=self.main_scene))
                    return report
                self._hide_all()
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                raise
            self.report = report
            self._emit(tr("Fuentes de OBS cargadas"))
            return report

    def refresh_items(self) -> SceneReport:
        """Vuelve a leer la colección SIN apagar nada: `_last_scene` se conserva (load_items lo
        apaga todo). Si falla la conexión, marca `connected = False` y relanza la excepción."""
        with self._lock:
            self._last_refresh = self._clock()
            if not self.connected or self._client is None:
                return self.report or SceneReport()
            try:
                self.report = self._scan()
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                raise
            return self.report

    # --- conmutación -------------------------------------------------------
    def _soft(self, what: str, fn, *args, quiet: bool = False) -> bool:
        """Una llamada cuyo rechazo por OBS (p. ej. el filtro no existe) no impide el resto.
        Los fallos de conexión sí se propagan."""
        try:
            fn(*args)
            return True
        except OBSSDKRequestError as e:
            if not (quiet and e.code == _RESOURCE_NOT_FOUND):
                self._emit(tr("OBS rechazó un cambio en {name} ({error})", name=what, error=e))
            return False

    def _enable_main(self, name: str, enabled: bool):
        if name in self._scene_ids:
            self._soft(name, self._client.set_scene_item_enabled, self.main_scene,
                       self._scene_ids[name], enabled)

    def _hide_all(self):
        for name in config.PLAYER_SCENES + [BORDE]:
            self._enable_main(name, False)
        self._last_scene = None

    def _remember(self, scene: str | None, abilities: int):
        self.pending_scene = scene
        self._pending_abilities = abilities
        self._has_pending = True

    def _clear_pending(self):
        self.pending_scene, self._has_pending = None, False

    def _refresh_if_due(self) -> bool:
        """Relee la colección si pasó ITEMS_REFRESH_S desde la última vez (así `apply` no se
        pone a escanear con cada cambio). False si la conexión se cayó al hacerlo."""
        now = self._clock()
        if self._last_refresh is not None and now - self._last_refresh < ITEMS_REFRESH_S:
            return True
        try:
            self.refresh_items()
        except Exception:  # noqa: BLE001 - refresh_items ya marcó la conexión como perdida
            return False
        return True

    def _place(self, scene: str, n: int):
        """Pone la escena en la posición y escala del filtro de `n` habilidades (leídas ahora, así
        los ajustes que se hagan en OBS valen de inmediato). Sin filtro no se toca nada."""
        self._presets = self._read_presets()
        preset = self._presets.get(n)
        if preset is None:
            return
        (x, y), (sx, sy) = preset["pos"], preset["scale"]
        self._soft(scene, self._client.set_scene_item_transform, self.main_scene, self._scene_ids[scene],
                   {"positionX": x, "positionY": y, "scaleX": sx, "scaleY": sy})

    def _provided_players(self) -> dict[str, PlayerConfig]:
        try:
            return self._players() or {}
        except Exception:  # noqa: BLE001 - un proveedor roto no debe tumbar el cambio de escena
            return {}

    def _set_mode(self, scene: str):
        """Dentro de la escena: enciende Camara o Foto según la configuración y apaga la otra."""
        player = self._provided_players().get(scene)
        use = effective_use(player) if player is not None else None
        if use is None:
            self._emit(tr("{scene} no tiene cámara ni foto configuradas", scene=scene))
        inner = self._inner.get(scene, {})
        chosen = {"camera": "Camara", "photo": "Foto"}.get(use)
        order = ([chosen] if chosen else []) + [k for k in ("Camara", "Foto") if k != chosen]
        for kind in order:
            name = source_name(kind, scene)
            if name in inner:
                self._soft(name, self._client.set_scene_item_enabled, scene, inner[name], kind == chosen)

    def _point_filters(self, scene: str):
        for name in config.HUD_FILTERS.values():
            self._soft(name, self._client.set_source_filter_settings, self.main_scene, name,
                       {"source": scene}, True, quiet=True)

    def apply(self, scene: str | None, reason: str, abilities: int = 4) -> None:
        """Pone `scene` al aire (None = ocultar todo): posición del filtro, cámara o foto,
        escena nueva antes de apagar la anterior, Borde y filtros apuntando al jugador. No lanza
        nunca y no espera a una reconexión en curso: si no hay conexión, o OBS falla, se marca
        `connected = False` y se guarda la escena en `pending_scene`."""
        if not self.connected:           # sin lock: no esperar a una reconexión en curso
            self._remember(scene, abilities)
            return
        with self._lock:
            if not self.connected or self._client is None:
                self._remember(scene, abilities)
                return
            self._last_abilities = abilities
            old = self._last_scene
            if scene == old:
                self._clear_pending()
                return
            if scene is not None and scene not in self._scene_ids:
                if not self._refresh_if_due():   # la conexión se cayó al releer la colección
                    self._remember(scene, abilities)
                    return
                if scene not in self._scene_ids:
                    # Sin esa escena no hay nada que mostrar: se apaga la anterior y el Borde.
                    if scene not in self._warned:
                        self._warned.add(scene)
                        self._emit(tr("{scene} no está en la escena de OBS: se apaga la escena anterior",
                                      scene=scene))
                    scene = None
                    if old is None:          # ya estaba todo apagado
                        self._clear_pending()
                        return
            try:
                self._emit(f"{old or tr('ninguna')} -> {scene or tr('oculto')}  {reason}")
                if scene is not None:
                    self._place(scene, clamp_abilities(abilities))
                    self._set_mode(scene)
                    self._enable_main(scene, True)
                if old is not None:
                    self._enable_main(old, False)
                self._enable_main(BORDE, scene is not None)
                if scene is not None:
                    self._point_filters(scene)
                self._last_scene = scene
                self._clear_pending()
            except Exception as e:  # noqa: BLE001
                self._remember(scene, abilities)
                self._fail(e)

    def _enable_filter(self, abilities: int):
        name = config.HUD_FILTERS[clamp_abilities(abilities)]
        self._soft(name, self._client.set_source_filter_enabled, self.main_scene, name, True, quiet=True)

    def retrigger(self, scene: str, abilities: int) -> None:
        """Las habilidades del jugador al aire cambiaron: activa solo el filtro de esa cantidad
        (los filtros ya apuntan a `scene`). No lanza nunca."""
        with self._lock:
            if not self.connected or self._client is None:
                return
            try:
                self._enable_filter(abilities)
            except Exception as e:  # noqa: BLE001
                self._fail(e)

    def test_filter(self, abilities: int) -> bool:
        """Botón «Probar»: apunta los filtros a la escena al aire (o a la primera) y activa el
        de `abilities`. No lanza nunca; devuelve si OBS lo recibió."""
        with self._lock:
            if not self.connected or self._client is None:
                return False
            try:
                self._point_filters(self._last_scene or config.PLAYER_SCENES[0])
                self._enable_filter(abilities)
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                return False
            return True

    def ensure_connected(self, current_scene: str | None) -> bool:
        """Si no hay conexión: reconecta, recarga los IDs y reaplica la última escena pedida
        (`pending_scene`, si la hay; si no, `current_scene`). Abrir el cliente se hace fuera
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
                if self._has_pending:
                    scene, abilities = self.pending_scene, self._pending_abilities
                else:
                    scene, abilities = current_scene, self._last_abilities
                self.apply(scene, tr("reconexión"), abilities)
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

    def create_companion(self, name: str, scene: str | None = None) -> bool:
        """Crea el acompañante (fuente de imagen) en la escena (por defecto la principal), oculto."""
        scene = scene or self.main_scene
        with self._lock:
            if not self.connected or self._client is None:
                return False
            try:
                res = self._client.create_input(scene, name, "image_source", {}, False)
                if scene == self.main_scene and name == BORDE:
                    self._scene_ids[name] = res.scene_item_id
                    if self._last_scene is not None:   # el Borde se ve solo con una escena al aire
                        self._enable_main(name, True)
            except Exception as e:  # noqa: BLE001
                if isinstance(e, OBSSDKRequestError):
                    self._emit(tr("OBS rechazó crear {name} ({error})", name=name, error=e))
                else:
                    self._fail(e)
                return False
            self._emit(tr("Creado {name} en la escena '{scene}'", name=name, scene=scene))
            return True
