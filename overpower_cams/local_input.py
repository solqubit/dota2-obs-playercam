"""Entrada local: teclas y clicks en la PC de Dota, mientras Dota es la ventana activa."""
import ctypes
import ctypes.wintypes
import queue
import threading
import time

from .i18n import tr

MODIFIER_VKS = {16, 17, 18, 160, 161, 162, 163, 164, 165}   # shift, ctrl, alt (izq/der)
IGNORED_VKS = {9, 13, 27, 91, 92} | MODIFIER_VKS            # + tab, enter, esc, win

_user32 = ctypes.windll.user32
_user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
_user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
_user32.GetClientRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
_user32.ClientToScreen.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.POINT)]

_STOP = object()   # centinela que despierta y detiene al hilo trabajador


def set_dpi_awareness() -> None:
    """Coordenadas reales aunque Windows escale la pantalla. Llamar una vez al arrancar la app."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            _user32.SetProcessDPIAware()
        except Exception:
            pass


def dota_client_rect():
    """(left, top, ancho, alto) del área de juego si Dota es la ventana activa; si no, None."""
    hwnd = _user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(64)
    _user32.GetWindowTextW(hwnd, title, 64)
    if not title.value.startswith("Dota 2"):
        return None
    rect = ctypes.wintypes.RECT()
    _user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = ctypes.wintypes.POINT(0, 0)
    _user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right, rect.bottom


def _vk(key):
    if isinstance(key, int):
        return key
    return getattr(key, "vk", None) or getattr(getattr(key, "value", None), "vk", None)


class LocalInput:
    def __init__(self, engine, *, get_rect=dota_client_rect, clock=time.monotonic,
                 on_event=None, keyboard_listener=None, mouse_listener=None):
        self._engine = engine
        self._get_rect = get_rect
        self._clock = clock
        self._on_event = on_event
        self._keyboard_listener = keyboard_listener   # clase tipo pynput.keyboard.Listener
        self._mouse_listener = mouse_listener         # clase tipo pynput.mouse.Listener
        self.queue: queue.Queue = queue.Queue()
        self._held_keys: set[int] = set()
        self._listeners: list = []
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    # --- hooks (deben volver rápido: solo encolan) ---------------------------
    def on_press(self, key) -> None:
        vk = _vk(key)
        if vk is None or vk in self._held_keys:
            return   # tecla desconocida o auto-repetición
        self._held_keys.add(vk)
        if vk in IGNORED_VKS or self._held_keys & MODIFIER_VKS or not self._get_rect():
            return   # Ctrl/Alt/Shift + tecla es otra acción en Dota
        self.queue.put((self._clock(), "key", vk))

    def on_release(self, key) -> None:
        self._held_keys.discard(_vk(key))

    def on_click(self, x, y, button, pressed) -> None:
        if not pressed or button.name != "left":
            return
        r = self._get_rect()
        if not r:
            return
        left, top, w, h = r
        if left <= x < left + w and top <= y < top + h:
            # La barra superior de Dota escala con el alto y va centrada: sirve en cualquier resolución.
            self.queue.put((self._clock(), "click", ((x - (left + w / 2)) / h, (y - top) / h)))

    # --- ciclo de vida -------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._worker is not None:
                return
            keyboard_cls, mouse_cls = self._keyboard_listener, self._mouse_listener
            if keyboard_cls is None or mouse_cls is None:
                from pynput import keyboard, mouse
                keyboard_cls = keyboard_cls or keyboard.Listener
                mouse_cls = mouse_cls or mouse.Listener
            self._drain()
            self._held_keys.clear()
            self._stop_event = threading.Event()
            self._worker = threading.Thread(
                target=self._run, args=(self._stop_event,), name="local-input", daemon=True)
            self._worker.start()
            self._listeners = [
                mouse_cls(on_click=self.on_click),
                keyboard_cls(on_press=self.on_press, on_release=self.on_release),
            ]
            for listener in self._listeners:
                listener.start()

    def stop(self) -> None:
        with self._lock:
            if self._worker is None:
                return
            listeners, worker = self._listeners, self._worker
            self._listeners, self._worker = [], None
            self._stop_event.set()
        for listener in listeners:
            try:
                listener.stop()
            except Exception:
                pass
        self.queue.put(_STOP)
        worker.join(timeout=2)

    # --- hilo trabajador -----------------------------------------------------
    def _drain(self) -> None:
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                return

    def _run(self, stop_event: threading.Event) -> None:
        # Los hooks de Windows deben volver rápido: OBS se llama desde este hilo, no desde el hook.
        while True:
            item = self.queue.get()
            if item is _STOP or stop_event.is_set():
                return
            try:
                t, kind, value = item
                self._engine.handle_input(t, kind, value)
            except Exception as e:
                if self._on_event:
                    try:
                        self._on_event("[ERROR] " + tr("entrada local: {error}", error=e))
                    except Exception:
                        pass
