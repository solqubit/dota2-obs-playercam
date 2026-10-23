# Releasing a new version

## 1. Build

From the project root, with the `.venv` set up:

```
.venv\Scripts\pyinstaller packaging/overpower_cams.spec --noconfirm
.venv\Scripts\python packaging/make_zip.py 2.0.1
```

Result:

- `dist\DotaPlayerCams\DotaPlayerCams.exe`: a folder build with no UPX and embedded
  version info. `assets\Borde.png` ends up in `_internal\assets\`.
- `dist\DotaPlayerCams-v2.0.1-windows.zip`, containing:
  - the app folder;
  - `FIRST_RUN_GUIDE.txt` and `GUIA_PRIMERA_VEZ.txt`;
  - `LICENSE.txt` and `THIRD_PARTY_NOTICES.md`;
  - `PREPARAR_DEMO.cmd` and `Camaraman/` with the scene template, all three graphics,
    bilingual demo guide, official Move Transition 3.2.1 installer, its source and license;
  - `SHA256SUMS.txt` for every file in the ZIP.

`make_zip.py` downloads the pinned plugin files and verifies their SHA-256 hashes.
To use a local original installer instead, pass `--resources "D:\OverPower\Camaraman"`.
It must match the pinned official digest. Temporary downloads are removed automatically.
Extract to a temporary test folder, run the preparer and verify all 31 graphic references
resolve, the H 4/5/6 presets are unchanged, and the ZIP has no personal settings or links.

When bumping the version, update `packaging/version_info.txt` (`filevers`/`prodvers` and
`FileVersion`/`ProductVersion`) and pass the same number to `make_zip.py`.

## 2. Before publishing every version (required)

1. Upload the `.zip` to <https://www.virustotal.com> and review the result.
2. If Microsoft Defender flags it, submit it as a **false positive** at
   <https://www.microsoft.com/en-us/wdsi/filesubmission> (choose "Software developer").
3. Nothing guarantees that no antivirus will ever flag it. The first-run guide explains
   how to add a folder exclusion.

## 3. Publish on GitHub

Create a release with tag `vX.Y.Z` on `main` and attach the `.zip` as a release asset.
The `.zip` never goes inside the repository.

## Packaging decisions (to reduce false positives)

- Folder build (onedir) instead of a single .exe, `upx=False`, `console=False`, embedded
  version info.
- The spec isolates DLL lookup from unrelated applications on the build machine's PATH.
  Keep this isolation: collecting another program's `icuuc.dll` can make QtWidgets fail
  to import even when the Python app and the build both succeed. After building, launch
  the executable with temporary APPDATA, hidden mode and a disconnected OBS endpoint;
  check that its local GSI server responds and that no `error.log` is created.
- No code signing. SmartScreen will show "Unknown publisher", and the guide explains how
  to continue.

## Notes for v2 (Camaraman)

- `obs/example-scene.json` is generated from a migrated Camaraman collection, read-only:
  `.venv\Scripts\python tools\migrate_camaraman.py "%APPDATA%\obs-studio\basic\scenes\Camaraman.json" --example obs\example-scene.json`
  (never pass `--apply` for this). It strips paths, URLs, player names, test scenes and plugin
  content (such as Aitum Vertical). Review it for personal data before committing.
- The release notes must say that **Move Transition 3.2.1** (Exeldro) is required, its
  installer/source/license are included in the demo and installation is manual. v1 scenes
  do not work with v2 (v1.0.1 stays available).
- The demo uses a **3840×2160 base canvas**; QHD/1080p output does not require changing
  its Move Source presets. Link `docs/DEMO_CAMARAMAN.md` for exact conversion details.
- `tools/gsi_capture.py` records real GSI data (used to fix the ability-counting rule). It is a
  development tool and is not mentioned in the user guides.
- Mark the release as the latest version.
