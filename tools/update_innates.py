"""Actualiza las innatas de todos los héroes usando los indicadores de UI de Valve.

Uso: python tools/update_innates.py --refresh
     python tools/update_innates.py captura_metadata.json

--refresh consulta herolist/herodata de dota2.com y escribe solo si todas las consultas
terminan. En ejecución la app usa el catálogo empaquetado, sin conexión a Internet.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from overpower_cams.abilities import INNATE_UI, innate_uses_hud_slot  # noqa: E402

SOURCE = "https://www.dota2.com/datafeed/"
DESTINO = ROOT / "overpower_cams" / "data" / "innate_abilities.json"


def _get_heroes(query):
    with urlopen(SOURCE + query, timeout=30) as response:
        heroes = json.load(response)["result"]["data"]["heroes"]
    if not heroes:
        raise ValueError("Valve no devolvió héroes; se conserva el catálogo anterior")
    return heroes


def fetch_metadata():
    heroes = _get_heroes("herolist?language=english")

    def fetch(hero):
        data = _get_heroes(f"herodata?language=english&hero_id={hero['id']}")[0]
        if data["name"] != hero["name"] or not data["abilities"]:
            raise ValueError(f"Metadata incompleta de {hero['name']}")
        return data

    with ThreadPoolExecutor(max_workers=8) as pool:
        details = list(pool.map(fetch, heroes))
    records = {a["name"]: {"behavior": a["behavior"], "innate": a["ability_is_innate"]}
               for hero in details for a in hero["abilities"]}
    return {"heroes": len(details), "abilities": records}


def build_catalog(metadata, previous):
    records = metadata["abilities"]
    if not metadata["heroes"] or not records:
        raise ValueError("Metadata vacía; se conserva el catálogo anterior")
    # Las habilidades antiguas siguen reconocibles en repeticiones. Si Valve las vuelve
    # a listar, su definición actual sustituye siempre la clasificación anterior.
    legacy = set(previous.get("legacy_non_slots", []))
    legacy.update(name for name, flags in previous.get("abilities", {}).items()
                  if not innate_uses_hud_slot(int(flags)))
    legacy.difference_update(records)
    innates = {name: str(int(a["behavior"])) for name, a in sorted(records.items())
               if a["innate"] or int(a["behavior"]) & INNATE_UI}
    return {"source": SOURCE, "hero_count": metadata["heroes"], "abilities": innates,
            "legacy_non_slots": sorted(legacy)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--refresh", action="store_true")
    source.add_argument("metadata", nargs="?")
    args = parser.parse_args(argv)
    metadata = (fetch_metadata() if args.refresh else
                json.loads(Path(args.metadata).read_text(encoding="utf-8")))
    previous = json.loads(DESTINO.read_text(encoding="utf-8")) if DESTINO.exists() else {}
    catalog = build_catalog(metadata, previous)
    fd, temporary = tempfile.mkstemp(dir=DESTINO.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(catalog, output, indent=2, ensure_ascii=False)
            output.write("\n")
        os.replace(temporary, DESTINO)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"{catalog['hero_count']} héroes; {len(catalog['abilities'])} innatas -> {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
