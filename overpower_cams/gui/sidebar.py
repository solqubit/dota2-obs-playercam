"""Menú lateral fijo (boceto D v2): logo, las 5 páginas con sus nombres y el número de
revisiones pendientes junto a Revisión."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import config
from ..i18n import tr

PAGE_KEYS = ("players", "checks", "scene", "events", "settings")
NAV_ICONS = {"players": "👥", "checks": "✔", "scene": "🎬", "events": "📜", "settings": "⚙"}


def nav_title(key: str) -> str:
    return {"players": tr("Jugadores"), "checks": tr("Revisión"), "scene": tr("Escena OBS"),
            "events": tr("Eventos"), "settings": tr("Ajustes")}[key]


class Sidebar(QFrame):
    def __init__(self, on_pick):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(208)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 20, 10, 18)
        lay.setSpacing(4)
        brand, _, sub = config.app_name().partition(" · ")
        b = QLabel(brand)
        b.setObjectName("brand")
        s = QLabel(sub)
        s.setObjectName("brandSub")
        for w in (b, s):
            w.setContentsMargins(12, 0, 0, 0)
            lay.addWidget(w)
        lay.addSpacing(18)
        self._group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for key in PAGE_KEYS:
            btn = QPushButton(f"{NAV_ICONS[key]} {nav_title(key)}")
            btn.setObjectName("navItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: on_pick(k))
            self._group.addButton(btn)
            self.buttons[key] = btn
            lay.addWidget(btn)
        badge_lay = QHBoxLayout(self.buttons["checks"])
        badge_lay.setContentsMargins(0, 0, 10, 0)
        badge_lay.addStretch(1)
        self.badge = QLabel()
        self.badge.setObjectName("badge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.badge.hide()
        badge_lay.addWidget(self.badge)
        lay.addStretch(1)

    def set_pending(self, n: int) -> None:
        self.badge.setText(str(n))
        self.badge.setVisible(n > 0)
