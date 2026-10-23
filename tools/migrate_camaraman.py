"""Migra la colección de OBS "Camaraman" a la estructura v2 (sin conexión a OBS, con OBS cerrado).

Uso:
    python tools/migrate_camaraman.py <coleccion.json>                      informe en seco (no escribe nada)
    python tools/migrate_camaraman.py <coleccion.json> --apply              migra (copia .antes_v2.bak primero)
    python tools/migrate_camaraman.py <coleccion.json> --example <sal.json> escribe además la escena de ejemplo limpia

Qué hace (ver docs/_interno/2026-10-22-camaraman-design.md, sección 4.3):
  1. En `1 Hard carry` renombra las fuentes al patrón `<Tipo> · <escena>`.
  2. Reconstruye las otras 9 escenas de jugador como copia de `1 Hard carry` (fuentes propias, uuids nuevos,
     URL vacía, texto = nombre de la escena).
  3. Quita de esas 9 escenas los items viejos (Color, Marco, Fondo Texto, Foto X, Camara X, Nombre X) y las fuentes
     que queden sin ninguna escena que las use.
  4. Deja los 10 items de `Juego` con la transform de `1 Hard carry` (`Borde` y los filtros H 4/5/6 no se tocan).
"""
import argparse
import copy
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

SEP = " · "
MAIN_SCENE = "Juego"
TEMPLATE = "1 Hard carry"
SCENES = ["1 Hard carry", "1 Mid laner", "1 Offlaner", "1 Soft support", "1 Hard support",
          "2 Hard carry", "2 Mid laner", "2 Offlaner", "2 Soft support", "2 Hard support"]
ROLES = ("Camara", "Foto", "Fondo", "Nombre")
# nombre viejo (v1) de cada fuente de la plantilla -> rol
TEMPLATE_RENAMES = {"Camara Jugador URL": "Camara", "Foto Jugador URL": "Foto",
                    "Fondo Texto": "Fondo", "Nombre Jugador": "Nombre"}
# items de la estructura vieja que se quitan de las 9 escenas (sin el patrón nuevo)
_OLD_ITEM = re.compile(r"^(Color|Marco|Fondo Texto|Foto .+|Camara .+|Nombre .+)$", re.IGNORECASE)
# campos de transform que se copian a los items de `Juego` (no `visible`, `id` ni `name`)
TRANSFORM_KEYS = ["pos", "pos_rel", "scale", "scale_rel", "rot", "align", "scale_ref", "bounds_type",
                  "bounds_align", "bounds_crop", "bounds", "bounds_rel", "crop_left", "crop_top",
                  "crop_right", "crop_bottom"]
_REF_KEYS = {"source", "source_name", "sourceName"}      # campos de filtros que apuntan a una fuente por nombre
_RUTA_O_URL = re.compile(r"(?i)^([a-z]:[\\/]|https?://)")
OBS_EXE = "obs64.exe"


class ErrorMigracion(Exception):
    pass


def nombre_de(rol: str, escena: str) -> str:
    return f"{rol}{SEP}{escena}"


# ---------------------------------------------------------------- lectura / escritura

def cargar(ruta: Path):
    """(colección, fin de línea). OBS escribe con 4 espacios y sin salto final."""
    crudo = Path(ruta).read_bytes().decode("utf-8")
    return json.loads(crudo), ("\r\n" if "\r\n" in crudo else "\n")


def serializar(col, fin="\n") -> bytes:
    texto = json.dumps(col, ensure_ascii=False, indent=4)
    if fin != "\n":
        texto = texto.replace("\n", fin)
    return texto.encode("utf-8")


# ---------------------------------------------------------------- utilidades de la colección

def _fuentes(col) -> dict:
    return {s["name"]: s for s in col["sources"]}


def _contenedores(col):
    """Escenas y grupos: todo lo que tiene `settings.items`."""
    for s in col["sources"]:
        if s.get("id") == "scene":
            yield s
    for g in col.get("groups", []):
        yield g


def _uuids_usados(col) -> set:
    return {i.get("source_uuid") for c in _contenedores(col) for i in c["settings"].get("items", [])}


def _recorrer_referencias(obj, funcion):
    """Llama funcion(dict, clave) por cada campo de filtro que apunta a una fuente por nombre."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _REF_KEYS and isinstance(v, str):
                funcion(obj, k)
            else:
                _recorrer_referencias(v, funcion)
    elif isinstance(obj, list):
        for v in obj:
            _recorrer_referencias(v, funcion)


def _renombrar(col, viejo: str, nuevo: str):
    fuente = _fuentes(col)[viejo]
    fuente["name"] = nuevo
    for c in _contenedores(col):
        for it in c["settings"].get("items", []):
            if it.get("source_uuid") == fuente["uuid"]:
                it["name"] = nuevo

    def cambia(d, k):
        if d[k] == viejo:
            d[k] = nuevo
    for s in col["sources"]:
        _recorrer_referencias(s.get("filters", []), cambia)


def _nuevo_uuid() -> str:
    return str(uuid.uuid4())


def _clonar_fuente(origen: dict, nombre: str, escena: str, rol: str) -> dict:
    nueva = copy.deepcopy(origen)
    nueva["name"] = nombre
    nueva["uuid"] = _nuevo_uuid()
    ajustes = nueva.setdefault("settings", {})
    if "undo_uuid" in ajustes:
        ajustes["undo_uuid"] = nueva["uuid"]
    if rol in ("Camara", "Foto"):
        ajustes["url"] = ""
    elif rol == "Nombre":
        ajustes["text"] = escena
    for f in nueva.get("filters", []):
        f["uuid"] = _nuevo_uuid()
    return nueva


# ---------------------------------------------------------------- migración

def migrar(col):
    """Devuelve (colección migrada, informe). No modifica `col`."""
    col = copy.deepcopy(col)
    informe = {"renombres": [], "reconstruidas": [], "items_borrados": {}, "fuentes_borradas": [],
               "conservados": {}, "transforms": [], "avisos": []}
    fuentes = _fuentes(col)
    if TEMPLATE not in fuentes or MAIN_SCENE not in fuentes:
        raise ErrorMigracion(f"La colección no tiene las escenas `{MAIN_SCENE}` y `{TEMPLATE}`.")

    # 1. renombrar la plantilla
    for viejo, rol in TEMPLATE_RENAMES.items():
        nuevo = nombre_de(rol, TEMPLATE)
        if viejo in fuentes and nuevo not in fuentes:
            _renombrar(col, viejo, nuevo)
            informe["renombres"].append((viejo, nuevo))
            fuentes = _fuentes(col)
    plantilla = fuentes[TEMPLATE]["settings"]["items"]
    por_nombre = {i["name"]: i for i in plantilla}
    faltan = [nombre_de(r, TEMPLATE) for r in ROLES if nombre_de(r, TEMPLATE) not in por_nombre]
    if faltan:
        raise ErrorMigracion(f"`{TEMPLATE}` no tiene los items {faltan}.")
    items_plantilla = [por_nombre[nombre_de(r, TEMPLATE)] for r in ROLES]
    fuente_plantilla = {r: next(s for s in col["sources"] if s["uuid"] == it["source_uuid"])
                        for r, it in zip(ROLES, items_plantilla)}

    viejos = {fuentes[nuevo]["uuid"]: viejo for viejo, nuevo in informe["renombres"]}   # uuid -> nombre v1
    uuids_plantilla = {s["uuid"] for s in fuente_plantilla.values()}

    # 2 y 3. reconstruir las otras 9 escenas
    candidatas = {}          # uuid -> nombre de las fuentes de items borrados
    nuevas_fuentes = []
    for esc in SCENES:
        if esc == TEMPLATE or esc not in fuentes:
            continue
        ajustes = fuentes[esc]["settings"]
        items = ajustes.get("items", [])
        # también los items que apuntan a una fuente de la plantilla (p. ej. el viejo `Fondo Texto`, que era compartido)
        borrar = [i for i in items if i["source_uuid"] in uuids_plantilla
                  or (SEP not in i["name"] and _OLD_ITEM.match(i["name"]))]
        quedan = [i for i in items if i not in borrar]
        ya = {i["name"] for i in quedan}
        agregar = []
        for rol, it in zip(ROLES, items_plantilla):
            nombre = nombre_de(rol, esc)
            if nombre in ya:
                continue
            if nombre in fuentes:
                raise ErrorMigracion(f"Ya existe una fuente `{nombre}` fuera de la escena `{esc}`.")
            fuente = _clonar_fuente(fuente_plantilla[rol], nombre, esc, rol)
            nuevas_fuentes.append(fuente)
            item = copy.deepcopy(it)
            item["name"] = nombre
            item["source_uuid"] = fuente["uuid"]
            agregar.append(item)
        if not borrar and not agregar:
            continue
        for i in borrar:
            candidatas[i["source_uuid"]] = i["name"]
        otros = [i for i in quedan if SEP not in i["name"]]
        propios = [i for i in quedan if SEP in i["name"]]
        usados = {i["id"] for i in agregar + propios}
        contador = max([ajustes.get("id_counter", 0), *usados, *(i["id"] for i in otros)])
        for i in otros:                                   # lo que no es de la estructura vieja se respeta
            if i["id"] in usados:
                contador += 1
                i["id"] = contador
            usados.add(i["id"])
        ajustes["items"] = propios + agregar + otros
        ajustes["id_counter"] = max(contador, max(i["id"] for i in ajustes["items"]))
        informe["reconstruidas"].append(esc)
        informe["items_borrados"][esc] = [viejos.get(i["source_uuid"], i["name"]) for i in borrar]
        if otros:
            informe["conservados"][esc] = [i["name"] for i in otros]

    if nuevas_fuentes:
        pos = next((k for k, s in enumerate(col["sources"]) if s.get("id") == "scene"), len(col["sources"]))
        col["sources"][pos:pos] = nuevas_fuentes

    # fuentes que quedaron sin ninguna escena (solo entre las de items borrados)
    usados = _uuids_usados(col)
    huerfanas = {u: n for u, n in candidatas.items() if u not in usados}
    borradas = [s["name"] for s in col["sources"] if s["uuid"] in huerfanas]
    col["sources"] = [s for s in col["sources"] if s["uuid"] not in huerfanas]
    informe["fuentes_borradas"] = borradas
    for n in borradas:
        def avisa(d, k, n=n):
            if d[k] == n:
                informe["avisos"].append(f"Un filtro todavía apunta a la fuente borrada `{n}`.")
        for s in col["sources"]:
            _recorrer_referencias(s.get("filters", []), avisa)

    # 4. transform de `Juego`
    juego = {i["name"]: i for i in _fuentes(col)[MAIN_SCENE]["settings"]["items"]}
    base = juego.get(TEMPLATE)
    if base is None:
        raise ErrorMigracion(f"`{MAIN_SCENE}` no tiene el item `{TEMPLATE}`.")
    for esc in SCENES:
        it = juego.get(esc)
        if it is None or esc == TEMPLATE:
            continue
        cambia = [k for k in TRANSFORM_KEYS if k in base and it.get(k) != base[k]]
        if cambia:
            for k in cambia:
                it[k] = copy.deepcopy(base[k])
            informe["transforms"].append((esc, it_pos(it)))
    return col, informe


def it_pos(item) -> str:
    return f"posición {item['pos']['x']:g},{item['pos']['y']:g}, escala {item['scale']['x']:.3g}"


def informe_texto(inf, cambios: bool) -> str:
    if not cambios:
        return "La colección ya está migrada: no hay nada que cambiar."
    L = ["INFORME EN SECO (no se escribe nada)", ""]
    L.append("Fuentes que se renombran en `1 Hard carry`:")
    L += [f"  {a}  ->  {b}" for a, b in inf["renombres"]] or ["  (ninguna)"]
    L += ["", "Escenas que se reconstruyen como copia de `1 Hard carry` (fuentes nuevas, URL vacía, texto = escena):"]
    L += [f"  {e}" for e in inf["reconstruidas"]] or ["  (ninguna)"]
    L += ["", "Items que se quitan de cada escena:"]
    for esc, nombres in inf["items_borrados"].items():
        L.append(f"  {esc}: " + (", ".join(nombres) or "(ninguno)"))
    if inf["conservados"]:
        L += ["", "Items que NO son de la estructura vieja y se conservan tal cual:"]
        L += [f"  {e}: {', '.join(n)}" for e, n in inf["conservados"].items()]
    L += ["", "Fuentes que se borran de la colección (ninguna escena las usa después del cambio):"]
    L += [f"  {n}" for n in inf["fuentes_borradas"]] or ["  (ninguna)"]
    L += ["", f"Items de `{MAIN_SCENE}` que cambian a la transform de `{TEMPLATE}`:"]
    L += [f"  {e} ({d})" for e, d in inf["transforms"]] or ["  (ninguno)"]
    L += ["", "Sin cambios: `Borde`, filtros H 4/5/6 y cualquier otro filtro."]
    L += [f"AVISO: {a}" for a in inf["avisos"]]
    return "\n".join(L)


# ---------------------------------------------------------------- escena de ejemplo

def _limpiar_rutas(obj):
    """Vacía toda ruta de disco o URL dentro de los ajustes de una fuente o filtro."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and _RUTA_O_URL.match(v):
                obj[k] = ""
            else:
                _limpiar_rutas(v)
    elif isinstance(obj, list):
        for v in obj:
            _limpiar_rutas(v)


def ejemplo(col):
    """Colección de ejemplo limpia, a partir de una ya migrada. No modifica `col`."""
    col = copy.deepcopy(col)
    fuentes = _fuentes(col)
    prueba = fuentes.get("Prueba")
    if prueba is not None:
        col["sources"] = [s for s in col["sources"] if s is not prueba and s["uuid"] != prueba["uuid"]]
        for c in _contenedores(col):
            c["settings"]["items"] = [i for i in c["settings"]["items"] if i.get("source_uuid") != prueba["uuid"]]
    col["scene_order"] = [e for e in col.get("scene_order", []) if e.get("name") != "Prueba"]
    for clave in ("current_scene", "current_program_scene"):
        col[clave] = MAIN_SCENE
    for esc in SCENES:                                    # solo la estructura nueva en las escenas de jugador
        if esc in fuentes:
            ajustes = fuentes[esc]["settings"]
            ajustes["items"] = [i for i in ajustes["items"] if SEP in i["name"]]
    usados = _uuids_usados(col)
    col["sources"] = [s for s in col["sources"] if s.get("id") == "scene" or s["uuid"] in usados]
    for s in col["sources"]:
        if s.get("id") != "scene":
            _limpiar_rutas(s.get("settings", {}))
            for f in s.get("filters", []):
                _limpiar_rutas(f.get("settings", {}))
        if str(s.get("id", "")).startswith("wasapi_"):
            s["settings"] = {"device_id": "default"}
    for clave, valor in col.items():
        if "AudioDevice" in clave and isinstance(valor, dict):
            valor["settings"] = {"device_id": "default"}
    col["saved_projectors"] = []
    return col


# ---------------------------------------------------------------- línea de comandos

def _bak(ruta: Path) -> Path:
    bak = ruta.with_name(ruta.name + ".antes_v2.bak")
    n = 1
    while bak.exists():                                   # nunca pisar una copia anterior
        n += 1
        bak = ruta.with_name(f"{ruta.name}.antes_v2.{n}.bak")
    return bak


def main(argv=None, *, is_running=None) -> int:
    ap = argparse.ArgumentParser(description="Migra la colección Camaraman de OBS a la estructura v2.")
    ap.add_argument("coleccion", type=Path, help="Camaraman.json (en %%APPDATA%%\\obs-studio\\basic\\scenes)")
    ap.add_argument("--apply", action="store_true", help="escribe la migración (con OBS cerrado; hace copia)")
    ap.add_argument("--example", type=Path, metavar="SALIDA.json", help="escribe la escena de ejemplo limpia")
    args = ap.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):                # la consola de Windows no siempre es UTF-8
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if is_running is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from overpower_cams.paths import is_running
    if args.example and args.example.resolve() == args.coleccion.resolve():
        print("La salida del ejemplo no puede ser la colección de OBS.", file=sys.stderr)
        return 2
    if args.apply and is_running(OBS_EXE):
        print("OBS está abierto: ciérralo antes de migrar (no se escribió nada).", file=sys.stderr)
        return 1
    try:
        col, fin = cargar(args.coleccion)
        migrada, inf = migrar(col)
    except (OSError, ValueError, KeyError, ErrorMigracion) as e:
        print(f"No se pudo migrar: {e}", file=sys.stderr)
        return 2
    cambios = migrada != col
    if args.apply:
        if cambios:
            bak = _bak(args.coleccion)
            shutil.copy2(args.coleccion, bak)
            args.coleccion.write_bytes(serializar(migrada, fin))
            print(f"Colección migrada. Copia de seguridad: {bak}")
        else:
            print(informe_texto(inf, False))
    else:
        print(informe_texto(inf, cambios))
    if args.example:
        args.example.write_bytes(serializar(ejemplo(migrada), fin))
        print(f"Escena de ejemplo escrita en {args.example}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
