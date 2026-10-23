"""Graba los POST del GSI de Dota 2 en un archivo .jsonl (una línea por POST).

Uso, desde la raíz del repositorio y con la app cerrada (usa el mismo puerto):
    .venv/Scripts/python tools/gsi_capture.py [salida.jsonl]

Captura con Dota abierto: usa su envío actual sin cambiar el cfg.
Sonda experimental para un nuevo inicio de Dota:
    .venv/Scripts/python tools/gsi_capture.py --all-data [salida.jsonl]
Si Dota ya está abierto, --all-data pasa automáticamente a captura en vivo.
Si estaba cerrado, ábrelo después de iniciar la sonda; Ctrl+C restaura el cfg respaldado.
"""
import json
import argparse
from contextlib import contextmanager, nullcontext
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from overpower_cams import paths                      # noqa: E402
from overpower_cams.config import GSI_HOST, GSI_PORT   # noqa: E402
from overpower_cams.engine import get_selected_hero   # noqa: E402
from overpower_cams.gsi_cfg import write_cfg          # noqa: E402
from overpower_cams.gsi_server import GsiServer, PortInUse   # noqa: E402
from overpower_cams.storage import Storage                 # noqa: E402

# Solicitudes de diagnóstico: algunas dependen del modo/versión del juego y pueden
# ser ignoradas. Su presencia en el cfg no demuestra que Dota publique esa sección.
DIAGNOSTIC_DATA_KEYS = (
    "provider", "map", "player", "hero", "abilities", "items", "draft", "wearables",
    "buildings", "units", "events", "league", "minimap", "roshan", "couriers", "neutralitems",
)


def config_con_unidades(texto: str) -> str:
    """Sonda experimental: activa las solicitudes de diagnóstico dentro de data.

    No cambia URI, token ni tiempos. Pedir una sección no garantiza que Dota la publique.
    """
    bloque = re.search(r'("data"\s*\{)([^{}]*)(\})', texto)
    if bloque is None:
        raise ValueError("No encontré un bloque data simple; no se modificó el archivo GSI.")
    body = bloque[2]
    for key in DIAGNOSTIC_DATA_KEYS:
        body, count = re.subn(r'("' + key + r'"\s*)"[^"]*"', r'\g<1>"1"', body)
        if not count:
            body = body.rstrip() + f'\n        "{key}" "1"\n    '
    return texto[:bloque.start(2)] + body + texto[bloque.end(2):]


def _atomic_bytes(path: Path, data: bytes) -> None:
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def config_temporal_unidades(path: Path, storage: Storage, *, is_running=paths.is_running):
    """Con Dota cerrado, respalda el cfg y lo restaura al terminar la captura."""
    if is_running("dota2.exe"):
        raise RuntimeError("Cierra Dota antes de iniciar la captura ampliada.")
    original = path.read_bytes()
    probe = config_con_unidades(original.decode("utf-8-sig")).encode("utf-8")
    backup = storage.backup(path)
    _atomic_bytes(path, probe)
    try:
        yield backup
    finally:
        # No pisar cambios hechos por otra aplicación mientras se capturaba.
        if path.read_bytes() != probe:
            raise RuntimeError(f"El cfg cambió durante la prueba. No lo sobrescribí; respaldo: {backup}")
        _atomic_bytes(path, original)


def describir_seleccion(data) -> str:
    """Distingue el héroe local del formato jugador y la selección del observador.

    En Probar héroe GSI puede enviar hero.name sin selected_unit. Ese nombre no
    demuestra qué unidad se seleccionó: nunca presentarlo como selección confirmada.
    """
    if not isinstance(data, dict) or not isinstance(data.get("hero"), dict):
        return "sin datos de héroe"
    heroes = data["hero"]
    local = heroes.get("name")
    if isinstance(local, str) and local.startswith("npc_dota_hero_"):
        nombre = local.removeprefix("npc_dota_hero_")
        return f"formato jugador/demo | héroe local: {nombre} | selección no verificada"
    if any(str(k).startswith("team") for k in heroes):
        heroe = get_selected_hero(data)[1]
        nombre = heroe.removeprefix("npc_dota_hero_") if heroe else "ninguno"
        return f"formato observador | héroe seleccionado: {nombre}"
    return "sin datos de héroe"


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

    def __init__(self, salida: Path, host=GSI_HOST, port=GSI_PORT, on_post=None,
                 requested_sections=(), capture_mode=None):
        self.salida = Path(salida)
        self.count = 0
        self.status = "esperando datos"
        self.unit_posts = 0
        self.requested_sections = tuple(requested_sections)
        self.capture_mode = capture_mode
        self.sections_seen: set[str] = set()
        self._on_post = on_post
        self._f = None
        self._server = GsiServer(self, host=host, port=port)

    @property
    def port(self) -> int:
        return self._server.server_port

    def process(self, data) -> None:   # lo llama GsiServer en cada POST
        row = {"t": time.monotonic(), "data": data}
        if self.count == 0 and self.requested_sections:
            row["requested_data"] = list(self.requested_sections)
        if self.count == 0 and self.capture_mode:
            row["capture_mode"] = self.capture_mode
        self._f.write(json.dumps(row) + "\n")
        self._f.flush()
        self.count += 1
        self.status = describir_seleccion(data)
        if isinstance(data, dict) and data.get("units"):
            self.unit_posts += 1
        if isinstance(data, dict):
            self.sections_seen.update(set(data) - {"auth", "previously", "added"})
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("salida", nargs="?")
    parser.add_argument("--all-data", "--units", dest="units", action="store_true",
                        help="activa el diagnóstico si Dota está cerrado; con Dota abierto captura su envío actual")
    parser.add_argument("--live", action="store_true",
                        help="captura sin modificar el archivo GSI, incluso si Dota está cerrado")
    args = parser.parse_args(argv[1:])
    salida = Path(args.salida if args.salida
                  else f"gsi_captura_{datetime.now():%Y-%m-%d_%H%M%S}.jsonl")
    dota = paths.find_dota(paths.steam_path())
    dota_abierto = paths.is_running("dota2.exe")
    en_vivo = args.live or dota_abierto
    ampliar = args.units and dota is not None and not en_vivo
    if en_vivo:
        print("CAPTURA EN VIVO: puedes mantener Dota abierto y seguir viendo la partida.")
        print("Se guarda todo lo que Dota ya envía; el archivo GSI no se modifica.")
        if args.units:
            print("Las 16 solicitudes nuevas no se activan en esta sesión de captura en vivo.")
    elif dota is None:
        print("No encontré Dota 2; no reviso el archivo GSI.")
    elif not args.units:
        revisar_cfg(paths.gsi_cfg_path(dota))

    def mostrar_estado(n, heroe):
        print(f"\rPOST recibidos: {n} | con units: {cap.unit_posts} | {cap.status:<110}",
              end="", flush=True)

    cap = Captura(salida, on_post=mostrar_estado,
                  requested_sections=DIAGNOSTIC_DATA_KEYS if ampliar else (),
                  capture_mode="diagnostic_all" if ampliar else "live_existing" if en_vivo else "current_config")
    try:
        with cap:
            cfg_context = (config_temporal_unidades(paths.gsi_cfg_path(dota), Storage(paths.app_data_dir()))
                           if ampliar else nullcontext())
            with cfg_context as backup:
                if ampliar:
                    print(f"Respaldo del archivo GSI: {backup}")
                    print("Solicitudes de diagnóstico activadas en 1: " + ", ".join(DIAGNOSTIC_DATA_KEYS))
                    print("Algunas solicitudes son experimentales; comprobaremos qué devuelve Dota.")
                    print("AHORA abre Dota y entra como observador. Al terminar se restaura el cfg.")
                print(f"Escuchando en http://{GSI_HOST}:{cap.port}/ -> {salida}")
                print("Para verificar la unidad seleccionada necesitamos formato observador.")
                print("En jugador/demo, 'héroe local' no confirma si seleccionaste al héroe o su invocación.")
                print("Ctrl+C para terminar y restaurar la configuración temporal, si se usó.")
                try:
                    while True:
                        time.sleep(0.5)
                except KeyboardInterrupt:
                    pass
            print(f"\nListo: {cap.count} POST guardados en {salida}")
            print("Secciones recibidas: " + (", ".join(sorted(cap.sections_seen)) or "ninguna"))
            if ampliar:
                missing = sorted(set(DIAGNOSTIC_DATA_KEYS) - cap.sections_seen)
                print("Solicitadas pero no recibidas: " + (", ".join(missing) or "ninguna"))
                print("Archivo GSI original restaurado. Dota volverá a cargarlo en su próximo inicio.")
    except PortInUse:
        print(f"El puerto {GSI_PORT} está ocupado. Cierra la app (o la consola) y vuelve a intentar.")
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"\nNo pude completar la captura: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
