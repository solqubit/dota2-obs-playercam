import hashlib
import importlib.util
from pathlib import Path
import zipfile

import pytest

from overpower_cams.demo import prepare_demo

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("release_zip", ROOT / "packaging/make_zip.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def release_tree(tmp_path):
    files = {
        "packaging/FIRST_RUN_GUIDE.txt", "packaging/GUIA_PRIMERA_VEZ.txt",
        "packaging/PREPARAR_DEMO.cmd", "docs/DEMO_CAMARAMAN.md", "LICENSE",
        "packaging/RELEASE_NOTES_v2.0.0.md",
        "THIRD_PARTY_NOTICES.md", "obs/example-scene.json", "assets/Borde.png",
        "docs/img/app.png", "docs/img/in-game.png",
        "assets/Mascara camara.png", "assets/Marco sin camara.png",
    }
    for relative in files:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    exe = tmp_path / "dist/DotaPlayerCams/DotaPlayerCams.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"test executable")
    plugin_files = {}
    for name in release.MOVE_FILES:
        path = tmp_path / name
        path.write_bytes(b"plugin fixture")
        plugin_files[name] = path
    return plugin_files


def test_zip_completo_se_extrae_y_reubica_y_sus_hashes_coinciden(tmp_path):
    plugin_files = release_tree(tmp_path)
    target = release.build_zip(tmp_path, "2.0.0", plugin_files)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert "PREPARAR_DEMO.cmd" in names
        assert "Camaraman/Plugins/move-transition-3.2.1-windows-installer.exe" in names
        assert "Camaraman/Plugins/move-transition-3.2.1-source.tar.xz" in names
        for line in archive.read("SHA256SUMS.txt").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        destination = tmp_path / "Otra ubicación"
        archive.extractall(destination)
    assert prepare_demo(destination / "Camaraman").is_file()


def test_un_recurso_ausente_conserva_el_zip_anterior(tmp_path):
    plugin_files = release_tree(tmp_path)
    target = release.build_zip(tmp_path, "2.0.0", plugin_files)
    original = target.read_bytes()
    (tmp_path / "assets/Borde.png").unlink()
    with pytest.raises(ValueError, match="Falta un recurso"):
        release.build_zip(tmp_path, "2.0.0", plugin_files)
    assert target.read_bytes() == original


def test_rechaza_un_instalador_local_que_no_coincide_con_el_oficial(tmp_path):
    (tmp_path / "move-transition-3.2.1-windows-installer.exe").write_bytes(b"wrong installer")
    with pytest.raises(ValueError, match="SHA-256 incorrecto"):
        with release.plugin_bundle(tmp_path):
            pytest.fail("An invalid plugin must not be packaged")
