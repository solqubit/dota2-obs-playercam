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
| OpenDota dotaconstants (data: list of innate passive abilities) | MIT, Copyright (c) 2017 The OpenDota Project | https://github.com/odota/dotaconstants |

**Not bundled:** the app expects the **Move Transition** plugin by Exeldro to be installed in
OBS (https://obsproject.com/forum/resources/move-transition.913/). It is a separate OBS plugin
with its own license; this app neither includes nor redistributes it, and only talks to OBS
through the WebSocket server.

The executable is built with PyInstaller. PyInstaller is GPL-2.0 with a bootloader
exception, which allows distributing packaged programs under any license.

The LGPL libraries ship as separate files inside the app folder (`_internal/`), so they can
be replaced with other compatible versions.

The full source code of this app is at https://github.com/solqubit/dota2-obs-playercam.

Dota 2 is a trademark of Valve Corporation. OBS Studio is a project of the OBS Project.
This project is not affiliated with or endorsed by Valve or the OBS Project.
