# Releasing a new version

## 1. Build

From the project root, with the `.venv` set up:

```
.venv\Scripts\pyinstaller packaging/overpower_cams.spec --noconfirm
.venv\Scripts\python packaging/make_zip.py 1.0.0
```

Result:

- `dist\DotaPlayerCams\DotaPlayerCams.exe`: a folder build with no UPX and embedded
  version info. `assets\Borde.png` ends up in `_internal\assets\`.
- `dist\DotaPlayerCams-v1.0.0-windows.zip`, containing:
  - the app folder;
  - `FIRST_RUN_GUIDE.txt` and `GUIA_PRIMERA_VEZ.txt`;
  - `LICENSE.txt` and `THIRD_PARTY_NOTICES.md`;
  - `example-scene.json`.

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
- No code signing. SmartScreen will show "Unknown publisher", and the guide explains how
  to continue.
