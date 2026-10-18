"""Servidor HTTP local que recibe los POST del Game State Integration de Dota 2."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import GSI_HOST, GSI_PORT
from .i18n import tr


class PortInUse(Exception):
    """El puerto GSI ya está ocupado por otro programa."""


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # En Windows SO_REUSEADDR permite enlazar un puerto que otro proceso ya escucha;
    # sin él, un puerto ocupado falla como debe (y uno recién cerrado se puede reabrir).
    allow_reuse_address = False

    def __init__(self, address, handler, owner):
        self.owner = owner
        super().__init__(address, handler)

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        owner = self.server.owner
        owner.last_post_t = owner._clock()
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            owner._engine.process(json.loads(body.decode()))
        except Exception as e:
            # Como el script: un POST malo o un fallo del motor no tumba al servidor
            # (siempre se responde 200), pero se avisa para que la interfaz lo muestre.
            owner._report(f"[ERROR] GSI: {e}")   # sin texto propio: no hay nada que traducir
        self._ok()

    def do_GET(self):
        self._ok()

    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        return


class GsiServer:
    def __init__(self, engine, host=GSI_HOST, port=GSI_PORT, *, clock=time.monotonic,
                 on_event=None):
        self._engine = engine
        self._host = host
        self._port = port
        self._clock = clock
        self._on_event = on_event
        self._httpd = None
        self._thread = None
        self.last_post_t: float | None = None

    def _report(self, msg: str) -> None:
        if self._on_event:
            try:
                self._on_event(msg)
            except Exception:
                pass   # un callback que falla no debe romper la respuesta 200

    @property
    def server_port(self) -> int:
        """Puerto real en el que escucha (útil con port=0)."""
        return self._httpd.server_address[1] if self._httpd else self._port

    def start(self) -> None:
        if self._httpd is not None:
            return
        try:
            httpd = _Server((self._host, self._port), _Handler, self)
        except OSError as e:
            raise PortInUse(tr("El puerto {port} está en uso por otra copia de la app, la consola "
                               "u otro programa ({error})", port=self._port, error=e)) from e
        self._httpd = httpd
        self._thread = threading.Thread(
            target=lambda: httpd.serve_forever(poll_interval=0.05), name="gsi-server", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        httpd, thread = self._httpd, self._thread
        if httpd is None:
            return
        self._httpd = self._thread = None
        self._port = httpd.server_address[1]
        httpd.shutdown()
        httpd.server_close()
        if thread is not None:
            thread.join(timeout=5)
