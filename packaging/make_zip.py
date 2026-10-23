r"""Empaqueta app y demo. Uso: python packaging/make_zip.py [version] [--resources CARPETA].

Verifica SHA-256 del instalador original de Move y distribuye también su fuente y licencia.
"""
import argparse
from contextlib import contextmanager
import hashlib
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent.parent
APP = "DotaPlayerCams"
DEFAULT_VERSION = "2.0.1"
MOVE_RELEASE = "https://github.com/exeldro/obs-move-transition/releases/download/3.2.1/"
MOVE_FILES = {
    "move-transition-3.2.1-windows-installer.exe": (
        MOVE_RELEASE + "move-transition-3.2.1-windows-installer.exe",
        "a3777ac68c0e7c86dbab8ea94146dbf4a48223e128696c32defd99ddaa56f8c8"),
    "move-transition-3.2.1-source.tar.xz": (
        MOVE_RELEASE + "move-transition-3.2.1-source.tar.xz",
        "d7c599ffd65fb445a7e088b8c11cdbc6e5d135b23a3f866c3f045b0d571ce48a"),
    "LICENSE-Move-Transition.txt": (
        "https://raw.githubusercontent.com/exeldro/obs-move-transition/3.2.1/LICENSE",
        "8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643"),
}


@contextmanager
def plugin_bundle(resources=None):
    with tempfile.TemporaryDirectory(prefix="playercam-release-") as temporary:
        files = {}
        for name, (url, expected) in MOVE_FILES.items():
            local = Path(resources) / name if resources and name.endswith(".exe") else None
            if local is not None and local.is_file():
                data = local.read_bytes()
            else:
                with urlopen(Request(url, headers={"User-Agent": "DotaPlayerCams-release"}), timeout=60) as response:
                    data = response.read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f"SHA-256 incorrecto: {name}; no se genera el release.")
            dest = Path(temporary) / name
            dest.write_bytes(data)
            files[name] = dest
        yield files


def build_zip(root: Path, version: str, plugin_files: dict[str, Path]) -> Path:
    folder = root / "dist" / APP
    if not (folder / f"{APP}.exe").is_file():
        raise ValueError(f"Falta dist/{APP}/{APP}.exe; ejecuta PyInstaller primero.")
    notes = root / "packaging" / f"RELEASE_NOTES_v{version}.md"
    if not notes.is_file():
        raise ValueError(f"Faltan las notas de la versión {version}: crea packaging/{notes.name} "
                         "(o revisa el número de versión).")
    entries = [
        (root / "packaging/FIRST_RUN_GUIDE.txt", "FIRST_RUN_GUIDE.txt"),
        (root / "packaging/GUIA_PRIMERA_VEZ.txt", "GUIA_PRIMERA_VEZ.txt"),
        (root / "packaging/PREPARAR_DEMO.cmd", "PREPARAR_DEMO.cmd"),
        (notes, "RELEASE_NOTES.md"),
        (root / "docs/DEMO_CAMARAMAN.md", "Camaraman/LEEME-DEMO.md"),
        (root / "docs/img/app.png", "Camaraman/img/app.png"),
        (root / "docs/img/in-game.png", "Camaraman/img/in-game.png"),
        (root / "LICENSE", "LICENSE.txt"),
        (root / "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
        (root / "obs/example-scene.json", "Camaraman/Ecenas/Camaraman.json"),
        (root / "assets/Borde.png", "Camaraman/Borde.png"),
        (root / "assets/Mascara camara.png", "Camaraman/Mascara camara.png"),
        (root / "assets/Marco sin camara.png", "Camaraman/Marcos/Marco sin camara.png"),
    ]
    entries += [(path, f"Camaraman/Plugins/{name}") for name, path in plugin_files.items()]
    entries += [(path, f"{APP}/{path.relative_to(folder).as_posix()}")
                for path in sorted(folder.rglob("*")) if path.is_file()]
    for path, _ in entries:
        if not path.is_file():
            raise ValueError(f"Falta un recurso del release: {path}")
    target = root / "dist" / f"{APP}-v{version}-windows.zip"
    with tempfile.TemporaryDirectory(dir=target.parent, prefix="release-") as temporary:
        staging = Path(temporary) / target.name
        sums = []
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, name in entries:
                archive.write(path, name)
                sums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}")
            archive.writestr("SHA256SUMS.txt", "\n".join(sums) + "\n")
        staging.replace(target)
    return target


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", default=DEFAULT_VERSION)
    parser.add_argument("--resources", type=Path)
    args = parser.parse_args(argv)
    with plugin_bundle(args.resources) as files:
        print(build_zip(ROOT, args.version, files))


if __name__ == "__main__":
    main()
