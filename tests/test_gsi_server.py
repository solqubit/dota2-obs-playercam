"""Tests del servidor GSI (en un puerto libre, con un motor falso)."""
import json
import socket
import urllib.request

import pytest

from overpower_cams.gsi_server import GsiServer, PortInUse
from tests.conftest import FakeClock, gsi_payload


class FakeEngine:
    def __init__(self, fail=False):
        self.received = []
        self.fail = fail

    def process(self, data):
        if self.fail:
            raise RuntimeError("fallo simulado del motor")
        self.received.append(data)


def _post(port, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/", data=json.dumps(payload).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, resp.read()


def test_post_llega_al_motor():
    engine, clock = FakeEngine(), FakeClock(42.0)
    server = GsiServer(engine, port=0, clock=clock)
    assert server.last_post_t is None
    server.start()
    try:
        status, body = _post(server.server_port, gsi_payload("r1"))
        assert (status, body) == (200, b"OK")
        assert engine.received == [gsi_payload("r1")]
        assert server.last_post_t == 42.0
    finally:
        server.stop()


def test_get_responde_200():
    server = GsiServer(FakeEngine(), port=0)
    server.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=5) as r:
            assert (r.status, r.read()) == (200, b"OK")
    finally:
        server.stop()


def test_error_del_motor_igual_responde_200_y_el_servidor_sigue():
    engine = FakeEngine(fail=True)
    events = []
    server = GsiServer(engine, port=0, on_event=events.append)
    server.start()
    try:
        assert _post(server.server_port, gsi_payload("r1"))[0] == 200
        assert _post(server.server_port, gsi_payload("r2"))[0] == 200
        assert server.last_post_t is not None
        assert events == ["[ERROR] GSI: fallo simulado del motor"] * 2
    finally:
        server.stop()


def test_callback_de_eventos_que_falla_no_rompe_el_200():
    def malo(msg):
        raise RuntimeError("callback roto")

    server = GsiServer(FakeEngine(fail=True), port=0, on_event=malo)
    server.start()
    try:
        assert _post(server.server_port, gsi_payload("r1"))[0] == 200
    finally:
        server.stop()


def test_json_invalido_responde_200():
    events = []
    server = GsiServer(FakeEngine(), port=0, on_event=events.append)
    server.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/", data=b"{no es json", method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
        assert len(events) == 1 and events[0].startswith("[ERROR] GSI:")
    finally:
        server.stop()


def test_puerto_ocupado():
    busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    busy.bind(("127.0.0.1", 0))
    busy.listen(1)
    try:
        server = GsiServer(FakeEngine(), host="127.0.0.1", port=busy.getsockname()[1])
        with pytest.raises(PortInUse) as info:
            server.start()
        msg = str(info.value)
        assert (f"El puerto {busy.getsockname()[1]} está en uso por otra copia de la app, "
                "la consola u otro programa") in msg
        assert "(" in msg and msg.endswith(")")      # lleva el texto de error del sistema
    finally:
        busy.close()


def test_stop_libera_el_puerto_para_un_servidor_nuevo():
    first = GsiServer(FakeEngine(), port=0)
    first.start()
    port = first.server_port
    _post(port, gsi_payload("r1"))   # deja una conexión cerrada (TIME_WAIT)
    first.stop()
    second = GsiServer(FakeEngine(), port=port)
    second.start()
    try:
        assert second.server_port == port
        assert _post(port, gsi_payload("r2"))[0] == 200
    finally:
        second.stop()


def test_stop_sin_start_y_start_doble_no_fallan():
    server = GsiServer(FakeEngine(), port=0)
    server.stop()
    server.start()
    port = server.server_port
    server.start()   # no-op
    assert server.server_port == port
    server.stop()
    server.stop()
