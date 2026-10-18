# dota2-obs-playercam

**OverPower Dota Player Cams**: a Windows desktop app that automatically switches player
webcams in OBS during Dota 2 broadcasts. The camera switches instantly on spectator
hotkeys and top-bar portrait clicks, and Game State Integration confirms it. The app also
checks your setup and fixes it in one click. The interface is available in **English and
Spanish**.

![The app: setup checks on the left, live controls on the right](docs/img/app.png)

*The interface is also available in Spanish (Settings → Language).*

*In game, the selected player's camera (here the "1" placeholder from a test scene) shows up
between the minimap and the HUD, with its border.*

![The player camera on stream](docs/img/in-game.png)

## What it does

While you spectate a match, the app turns on the OBS camera of the player you have
selected (for example, a VDO.Ninja link):

- **Instantly**, when you press a player's spectator hotkey (read from your Dota settings)
  or click their portrait in the top bar.
- **Confirmed by Dota's Game State Integration (GSI).** GSI also covers clicks on a hero in
  the world, with about 1 s of delay because Dota sends data once per second.
- **Turns the camera off** when you select something that isn't a hero (tower, creep,
  courier…) or when you leave the match.
- **Companions** (`Borde`, `Marco`): OBS elements that are only visible while a camera is
  on air, such as a border or a frame.
- **Sides:** you set whether Team 1 is Radiant or Dire, and the app remembers it.

### It checks and fixes your setup for you

When the app opens, each item shows green, yellow or red. When something is missing, the
app **fixes it in one click** (always asking first) or tells you exactly what to do:

| Check | What the app does |
|---|---|
| Dota installed | Finds it in any Steam library, or lets you pick the folder |
| GSI file | Creates Dota's Game State Integration file (and its folder, if missing) or fixes it |
| Data from Dota | Confirms data is arriving; if not, tells you how to enable it |
| Spectator hotkeys | Assigns keys 1–0 to the 10 players and resolves clashes with other actions, only with Dota closed and after making a backup |
| OBS & WebSocket | Checks the connection and password, and guides you if it isn't enabled |
| OBS scene | Lists what's missing and creates the `Borde` and `Marco` companions if needed |
| Border and frame images | Sets them from the app's image folder (see [Images](#border-and-frame-images)) |

Hotkeys and portrait clicks work from the first use. If you change your Dota hotkeys while
the app is open, it reloads them on its own. If OBS closes mid-broadcast, the app
reconnects when it comes back.

### How it talks to Dota and OBS

```
Dota 2  ──(GSI over local HTTP, ~1/s)──▶  App (127.0.0.1:3000)  ──(OBS WebSocket)──▶  OBS
```

- **Dota → app:** the app writes the GSI config file for you. Dota then posts the match
  state to the app on this PC only.
- **App → OBS:** set up once by you. OBS doesn't let other programs enable its WebSocket
  server or set its password, so you turn it on in OBS and paste the password into the
  app's Settings.

## Requirements

**Nothing to install:** the `.zip` contains everything the app needs (Python, Qt and the
Visual C++ runtime). You only need:

- Windows 10 or 11.
- Dota 2 (Steam).
- OBS Studio 30 or later, with the WebSocket server enabled (Tools → WebSocket Server
  Settings).
- An OBS scene with the structure below. An example is included.

## Installation

1. Download the latest `DotaPlayerCams-vX.Y.Z-windows.zip` from
   [Releases](https://github.com/solqubit/dota2-obs-playercam/releases) and extract the
   **whole** zip.
2. Open `DotaPlayerCams\DotaPlayerCams.exe`.
3. Follow `FIRST_RUN_GUIDE.txt` (or `GUIA_PRIMERA_VEZ.txt` in Spanish). It explains the
   Windows SmartScreen warning (the executable isn't signed) and what to do if your
   antivirus blocks it.

**Language:** the app starts in your Windows language (Spanish if Windows is in Spanish,
English otherwise). Change it in **Settings → Language**; it stays fixed until you change
it again.

Antivirus tools may be suspicious because the app listens to the keyboard and mouse. It only
does so in **Automatic** mode, and it ignores everything that doesn't happen with Dota as
the active window. It doesn't store anything you type, and it only uses the input to detect
spectator hotkeys and clicks.

## The OBS scene

### Start with the example scene

The repository includes a scene ready to import:
[`obs/example-scene.json`](obs/example-scene.json). The release `.zip` includes it as
`example-scene.json`. It has the 10 camera groups, `Borde`, `Marco` and a Dota 2 game
capture, and contains no devices or paths from any PC.

1. In OBS: **Scene Collection → Import**. Add `example-scene.json` and click **Import**.
2. **Scene Collection → Dota Player Cams (example)** to switch to it. Your current
   collection is left untouched.
3. **Cameras:** each group `CAM_EQ1_1` … `CAM_EQ2_5` contains a browser source
   `VDO_EQ…` that shows "Team N · Player N". Double-click each one and replace the URL with
   that player's VDO.Ninja *view* link (for example `https://vdo.ninja/?view=...`).
4. **Border and frame:** open the app and, under **Checks → Border and frame images**,
   click **Fix**. The border uses the image bundled with the app. For the frame, or to
   change the border, see [Images](#border-and-frame-images).
5. **Player name** (optional): add it as a text source **inside** the player's camera group,
   so it turns on and off with the camera.
6. **Layout:** the 10 groups sit in the same spot, since only one is ever shown at a time.
   Move or scale them as you like. The scene is designed for 16:9; with a different canvas,
   make sure everything stays on screen.

The app checks the scene when it opens and flags anything missing in red or yellow.

### Use your own scene

The app looks for these **exact** names inside the scene `Escena Dota`, either directly in
the scene or inside groups. The names are fixed so existing scenes keep working:

| Element | What it is |
|---|---|
| `CAM_EQ1_1` … `CAM_EQ1_5` | Cameras for players 1–5 of Team 1 (required) |
| `CAM_EQ2_1` … `CAM_EQ2_5` | Cameras for players 1–5 of Team 2 (required) |
| `Borde`, `Marco` | Companions (border, frame): visible only while a camera is on air (optional) |

Each `CAM_…` can be a single source (for example, a VDO.Ninja browser source) or a
**group** holding the camera, the frame and the player's name. The app turns the whole
element on and off.

The camera number is the player's position in their team. Radiant player 1 is the leftmost
portrait in the top bar.

### Border and frame images

The app keeps its images in **`DotaPlayerCams\_internal\assets\`** (in the source tree,
`assets/`). We recommend keeping yours there too:

| File | Used for |
|---|---|
| `Borde.png` | The border around the camera (bundled) |
| `Marco.png` | The shared frame (not bundled: add your own) |

With the file in that folder, click **Fix** under **Checks → Border and frame images** and
the app applies it to OBS live, without closing anything. The file name must match the OBS
element (`Marco.png` for `Marco`). You can also use the **Browse…** buttons, which open that
folder, or pick any image on your PC.

> Installing a new version replaces that folder. Keep a copy of your images and put them
> back afterwards.

## Development

Tested with Python 3.14.

```bash
python -m venv .venv
```
```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

Run the app:
```bash
.venv\Scripts\python -m overpower_cams.app
```

Console version (no window, same settings as the app):
```bash
.venv\Scripts\python console.py
```

Tests (they never touch your real Steam, Dota or OBS):
```bash
.venv\Scripts\python -m pytest
```

### Project layout

| Path | Contents |
|---|---|
| `overpower_cams/engine.py` | Engine: selected hero → camera (confirmed by GSI) |
| `overpower_cams/obs_link.py` | OBS connection, companions, reconnection |
| `overpower_cams/gsi_server.py` | HTTP server that receives Dota's data |
| `overpower_cams/local_input.py` | Hotkeys and clicks while Dota is active |
| `overpower_cams/portraits.py` | Positions of the top-bar portraits |
| `overpower_cams/dota_keys.py`, `gsi_cfg.py` | Spectator hotkeys and the GSI file |
| `overpower_cams/checks.py` | Checks and fixes |
| `overpower_cams/i18n.py` | Translations (English / Spanish) |
| `overpower_cams/gui/` | Window (PySide6) |
| `console.py` | Console version |
| `assets/` | App images (`Borde.png`); in the .exe they live in `_internal\assets\` |
| `obs/example-scene.json` | Example OBS scene, ready to import |
| `packaging/` | PyInstaller build, zip script and first-run guides |
| `docs/gamestate_integration_obs.cfg` | Example of the GSI file the app creates |

Per-PC data (settings, language, side, learned portraits, backups and `error.log`) is
stored in `%APPDATA%\OverPowerCamarasDota\`.

### Build

```bash
.venv\Scripts\pyinstaller packaging/overpower_cams.spec --noconfirm
```
```bash
.venv\Scripts\python packaging/make_zip.py 1.0.1
```

This creates two git-ignored folders:
- `dist\` with the results: `dist\DotaPlayerCams\` (the app, ready to run) and
  `dist\DotaPlayerCams-v1.0.1-windows.zip`. The zip contains the app, both first-run guides,
  the license, the third-party notices and the example scene.
- `build\` with PyInstaller's temporary files, safe to delete.

### Releasing

See [`packaging/RELEASING.md`](packaging/RELEASING.md). In short:
1. Bump the version and build.
2. Run the zip through VirusTotal.
3. Create a GitHub release with tag `vX.Y.Z` and attach the zip.

## License

[GPL-3.0](LICENSE). Bundled libraries and their licenses are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Dota 2 is a trademark of Valve Corporation. OBS Studio is a project of the OBS Project. This
project is not affiliated with or endorsed by either.
