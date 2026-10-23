r"""Builds dist/DotaPlayerCams-v<version>-windows.zip: the DotaPlayerCams/ app folder, the
first-run guides (English and Spanish), the license (GPL-3.0), the third-party notices and the
example OBS scene.

Usage (from the project root, after PyInstaller):
    .venv\Scripts\python packaging/make_zip.py [version]
Uses "/" inside the zip (PowerShell 5.1's Compress-Archive writes "\", which some unzip
tools do not handle).
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = sys.argv[1] if len(sys.argv) > 1 else "2.0.0"   # keep in sync with version_info.txt
APP = "DotaPlayerCams"

EXTRAS = [
    (ROOT / "packaging" / "FIRST_RUN_GUIDE.txt", "FIRST_RUN_GUIDE.txt"),
    (ROOT / "packaging" / "GUIA_PRIMERA_VEZ.txt", "GUIA_PRIMERA_VEZ.txt"),
    (ROOT / "LICENSE", "LICENSE.txt"),
    (ROOT / "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
    (ROOT / "obs" / "example-scene.json", "example-scene.json"),
]


def main() -> None:
    folder = ROOT / "dist" / APP
    if not (folder / f"{APP}.exe").is_file():
        sys.exit(f"dist/{APP} is missing: run PyInstaller first (see packaging/RELEASING.md).")
    target = ROOT / "dist" / f"{APP}-v{VERSION}-windows.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for src, name in EXTRAS:
            z.write(src, name)
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, f"{APP}/" + p.relative_to(folder).as_posix())
    print(target)


if __name__ == "__main__":
    main()
