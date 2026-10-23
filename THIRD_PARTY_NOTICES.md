# Third-party notices

dota2-obs-playercam is released under the **GPL-3.0** license (see `LICENSE`). The packaged
build (.exe) includes these libraries, each under its own license:

| Library | License | Project |
|---|---|---|
| obsws-python | GPL-3.0-only | https://github.com/aatikturk/obsws-python |
| websocket-client | Apache-2.0 | https://github.com/websocket-client/websocket-client |
| pynput | LGPL-3.0 | https://github.com/moses-palmer/pynput |
| six | MIT | https://github.com/benjaminp/six |
| PySide6 / Shiboken6 (Qt for Python) | LGPL-3.0 (or GPL-2.0 / GPL-3.0) | https://www.qt.io/qt-for-python |
| Qt 6 (bundled with PySide6) | LGPL-3.0 | https://www.qt.io |
| Python | PSF License | https://www.python.org |
| OpenDota dotaconstants (legacy innate names retained for older GSI data) | MIT, Copyright (c) 2017 The OpenDota Project | https://github.com/odota/dotaconstants |

The release demo also redistributes **Move Transition 3.2.1** by Exeldro, a separate OBS
plugin under GPL-2.0 (see its included license and source headers for per-file terms).
The original Windows installer, matching upstream source archive and license are together
in `Camaraman/Plugins/`. All three files are verified with pinned SHA-256 hashes during
packaging. Upstream: https://github.com/exeldro/obs-move-transition/releases/tag/3.2.1.
The app talks to OBS through WebSocket; the plugin is installed separately by the user.

The executable is built with PyInstaller. PyInstaller is GPL-2.0 with a bootloader
exception, which allows distributing packaged programs under any license.

The LGPL libraries ship as separate files inside the app folder (`_internal/`), so they can
be replaced with other compatible versions.

The full source code of this app is at https://github.com/solqubit/dota2-obs-playercam.

Dota 2 is a trademark of Valve Corporation. OBS Studio is a project of the OBS Project.
Current innate HUD behavior metadata is a snapshot of Valve's public Dota 2 data feed
(https://www.dota2.com/datafeed/herodata), refreshed with `tools/update_innates.py`.
This project is not affiliated with or endorsed by Valve or the OBS Project.
