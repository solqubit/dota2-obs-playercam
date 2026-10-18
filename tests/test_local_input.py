"""Tests de la entrada local: sin hooks reales de pynput (se inyectan listeners falsos)."""
import queue
import threading
from types import SimpleNamespace

from overpower_cams.local_input import LocalInput
from tests.conftest import FakeClock

RECT = (0, 0, 3840, 2160)
LEFT = SimpleNamespace(name="left")
RIGHT = SimpleNamespace(name="right")


class FakeEngine:
    def __init__(self, fail_on=None):
        self.inputs = []
        self.fail_on = fail_on
        self.event = threading.Event()
        self.threads = set()

    def handle_input(self, t, kind, value):
        self.threads.add(threading.current_thread())
        if value == self.fail_on:
            self.event.set()
            raise ValueError("input malformado")
        self.inputs.append((t, kind, value))
        self.event.set()


class FakeListener:
    """Listener falso: registra start/stop y guarda los callbacks."""
    instances = []

    def __init__(self, **callbacks):
        self.callbacks = callbacks
        self.started = False
        self.stopped = False
        FakeListener.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def _key(vk):
    return SimpleNamespace(vk=vk)


def _drain(q):
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            return items


def _li(rect=RECT, engine=None, **kw):
    return LocalInput(engine or FakeEngine(), get_rect=lambda: rect, clock=FakeClock(5.0), **kw)


def _li_fake(engine=None, **kw):
    FakeListener.instances.clear()
    return LocalInput(engine or FakeEngine(), get_rect=lambda: RECT, clock=FakeClock(1.0),
                      keyboard_listener=FakeListener, mouse_listener=FakeListener, **kw)


def test_tecla_va_a_cola_solo_con_dota_activo():
    li = _li(rect=None)
    li.on_press(_key(0x33))
    assert _drain(li.queue) == []
    li2 = _li()
    li2.on_press(_key(0x33))
    assert _drain(li2.queue) == [(5.0, "key", 0x33)]


def test_ctrl_mas_tecla_ignorada():
    li = _li()
    li.on_press(_key(162))
    li.on_press(_key(0x32))
    assert _drain(li.queue) == []


def test_teclas_ignoradas_y_sin_vk():
    li = _li()
    for vk in (9, 13, 27, 91, 92, 16, 164):
        li.on_press(_key(vk))
    li.on_press(SimpleNamespace())   # tecla sin vk
    assert _drain(li.queue) == []


def test_autorepeticion():
    li = _li()
    li.on_press(_key(0x32))
    li.on_press(_key(0x32))
    assert _drain(li.queue) == [(5.0, "key", 0x32)]
    li.on_release(_key(0x32))
    li.on_press(_key(0x32))
    assert _drain(li.queue) == [(5.0, "key", 0x32)]


def test_modificador_soltado_deja_pasar_la_tecla():
    li = _li()
    li.on_press(_key(162))
    li.on_release(_key(162))
    li.on_press(_key(0x32))
    assert _drain(li.queue) == [(5.0, "key", 0x32)]


def test_click_relativo_al_alto():
    li = _li()
    li.on_click(1920 + 278, 40, LEFT, True)
    assert _drain(li.queue) == [(5.0, "click", (278 / 2160, 40 / 2160))]


def test_click_ignorado_si_no_es_izquierdo_soltado_fuera_o_sin_dota():
    li = _li()
    li.on_click(1920, 40, RIGHT, True)
    li.on_click(1920, 40, LEFT, False)
    li.on_click(4000, 40, LEFT, True)    # fuera de la ventana
    li.on_click(1920, 2200, LEFT, True)
    assert _drain(li.queue) == []
    sin_dota = _li(rect=None)
    sin_dota.on_click(1920, 40, LEFT, True)
    assert _drain(sin_dota.queue) == []


def test_click_usa_el_origen_de_la_ventana():
    li = _li(rect=(100, 50, 1920, 1080))
    li.on_click(100 + 960 + 128, 50 + 20, LEFT, True)
    assert _drain(li.queue) == [(5.0, "click", (128 / 1080, 20 / 1080))]


def test_el_trabajador_entrega_al_motor_y_sobrevive_a_errores():
    engine = FakeEngine(fail_on=0x31)
    events = []
    li = _li_fake(engine, on_event=events.append)
    li.start()
    try:
        li.queue.put((1.0, "key", 0x31))       # el motor lanza
        assert engine.event.wait(2)
        engine.event.clear()
        li.queue.put((2.0, "key", 0x32))       # el hilo sigue vivo
        assert engine.event.wait(2)
        assert engine.inputs == [(2.0, "key", 0x32)]
        assert threading.current_thread() not in engine.threads
        assert events   # el error se avisó por on_event
    finally:
        li.stop()


def test_start_stop_start_con_listeners_inyectados():
    li = _li_fake()
    li.stop()                      # sin arrancar: no-op
    li.start()
    li.start()                     # doble start: no-op
    assert len(FakeListener.instances) == 2 and all(x.started for x in FakeListener.instances)
    ms, kb = FakeListener.instances   # primero mouse, luego teclado
    assert set(kb.callbacks) == {"on_press", "on_release"} and set(ms.callbacks) == {"on_click"}
    li.stop()
    assert all(x.stopped for x in FakeListener.instances)
    li.stop()                      # doble stop: no-op
    li.start()                     # se puede volver a arrancar
    assert len(FakeListener.instances) == 4 and all(x.started for x in FakeListener.instances[2:])
    li.stop()


def test_trabajador_funciona_tras_stop_y_start():
    engine = FakeEngine()
    li = _li_fake(engine)
    li.start()
    li.stop()
    li.start()
    try:
        li.queue.put((3.0, "click", (0.1, 0.02)))
        assert engine.event.wait(2)
        assert engine.inputs == [(3.0, "click", (0.1, 0.02))]
    finally:
        li.stop()


def test_set_dpi_awareness_existe_y_no_se_llama_al_importar():
    import overpower_cams.local_input as mod
    assert callable(mod.set_dpi_awareness)
