"""Graba los POST del GSI de Dota 2 en un archivo .jsonl (una línea por POST).

Uso, desde la raíz del repositorio y con la app cerrada (usa el mismo puerto):
    .venv/Scripts/python tools/gsi_capture.py [salida.jsonl]
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from overpower_cams import paths                      # noqa: E402
from overpower_cams.config import GSI_HOST, GSI_PORT   # noqa: E402
from overpower_cams.engine import get_selected_hero   # noqa: E402
from overpower_cams.gsi_cfg import write_cfg          # noqa: E402
from overpower_cams.gsi_server import GsiServer, PortInUse   # noqa: E402


def cfg_pide_habilidades(texto: str) -> bool:
    return re.search(r'"abilities"\s+"1"', texto) is not None


def revisar_cfg(ruta: Path, preguntar=input, decir=print) -> None:
    """Si el .cfg de GSI no pide habilidades, ofrece corregirlo (solo escribe si responde "s")."""
    try:
        texto = Path(ruta).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        texto = ""
    if cfg_pide_habilidades(texto):
        decir("El archivo GSI de Dota ya pide las habilidades.")
        return
    decir(f"El archivo GSI de Dota no pide las habilidades ({ruta}).")
    try:
        respuesta = preguntar("¿Corregirlo ahora? (s/n) ").strip().lower()
    except EOFError:
        respuesta = "n"
    if respuesta == "s":
        write_cfg(Path(ruta))
        decir("Archivo GSI corregido. Reinicia Dota para que lo lea.")
    else:
        decir("No se tocó el archivo: la captura no traerá habilidades.")


class Captura:
    """Servidor GSI que guarda cada POST como {"t": monotonic, "data": payload}."""

    def __init__(self, salida: Path, host=GSI_HOST, port=GSI_PORT, on_post=None):
        self.salida = Path(salida)
        self.count = 0
        self._on_post = on_post
        self._f = None
        self._server = GsiServer(self, host=host, port=port)

    @property
    def port(self) -> int:
        return self._server.server_port

    def process(self, data) -> None:   # lo llama GsiServer en cada POST
        self._f.write(json.dumps({"t": time.monotonic(), "data": data}) + "\n")
        self._f.flush()
        self.count += 1
        if self._on_post:
            self._on_post(self.count, get_selected_hero(data)[1])

    def __enter__(self):
        self._f = self.salida.open("a", encoding="utf-8")
        try:
            self._server.start()
        except BaseException:
            self._f.close()
            raise
        return self

    def __exit__(self, *exc):
        self._server.stop()
        self._f.close()


def main(argv: list[str]) -> int:
    salida = Path(argv[1] if len(argv) > 1
                  else f"gsi_captura_{datetime.now():%Y-%m-%d_%H%M%S}.jsonl")
    dota = paths.find_dota(paths.steam_path())
    if dota is None:
        print("No encontré Dota 2; no reviso el archivo GSI.")
    else:
        revisar_cfg(paths.gsi_cfg_path(dota))

    def en_vivo(n, heroe):
        nombre = heroe[len("npc_dota_hero_"):] if heroe else "-"
        print(f"\rPOST recibidos: {n}   héroe seleccionado: {nombre:<25}", end="", flush=True)

    try:
        with Captura(salida, on_post=en_vivo) as cap:
            print(f"Escuchando en http://{GSI_HOST}:{cap.port}/ -> {salida}")
            print("Entra a la partida y selecciona héroes. Ctrl+C para terminar.")
            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
            print(f"\nListo: {cap.count} POST guardados en {salida}")
    except PortInUse:
        print(f"El puerto {GSI_PORT} está ocupado. Cierra la app (o la consola) y vuelve a intentar.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
