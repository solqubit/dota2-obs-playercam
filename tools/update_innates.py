"""Regenera overpower_cams/data/innate_passives.json desde el abilities.json de OpenDota
dotaconstants (https://github.com/odota/dotaconstants, build/abilities.json, MIT).

Uso:  python tools/update_innates.py ruta/a/abilities.json

Guarda los nombres de habilidades con `is_innate: true` y comportamiento "Passive": esas
innatas pasivas no ocupan un lugar del HUD (se ven como un icono chico aparte).
"""
import json
import sys
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "overpower_cams" / "data" / "innate_passives.json"


def es_innata_pasiva(ab) -> bool:
    if not isinstance(ab, dict) or ab.get("is_innate") is not True:
        return False
    comportamiento = ab.get("behavior")
    if isinstance(comportamiento, str):
        comportamiento = [comportamiento]
    return "Passive" in (comportamiento or [])


def nombres(abilities: dict) -> list[str]:
    return sorted(k for k, v in abilities.items() if es_innata_pasiva(v))


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    datos = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    lista = nombres(datos)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(lista, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(lista)} innatas pasivas -> {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
