"""Menú lateral fijo (boceto D v2): logo, las 5 páginas con sus nombres y el número de
revisiones pendientes junto a Revisión. Los iconos se dibujan a mano, de un solo color (gris
o el del elegido): nunca con emojis de color."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import config
from ..i18n import tr
from .widgets import THEMES, theme_name

PAGE_KEYS = ("players", "checks", "scene", "events", "settings")
ICON_SIZE = 16
BADGE_HEIGHT = 18


def _draw_icon(p: QPainter, key: str, s: float) -> None:
    """Icono lineal de 16×16 para cada página (con la pluma ya elegida)."""
    if key == "players":                       # dos personas
        p.drawEllipse(QRectF(2.5, 2.5, 5, 5))
        p.drawArc(QRectF(1, 9, 8, 8), 0, 180 * 16)
        p.drawEllipse(QRectF(9, 3.5, 4.5, 4.5))
        p.drawArc(QRectF(8.5, 9.5, 6.5, 6.5), 0, 180 * 16)
    elif key == "checks":                      # visto
        p.drawPolyline([QPointF(2.5, 8.5), QPointF(6.5, 12.5), QPointF(13.5, 4)])
    elif key == "scene":                       # pantalla con su pie
        p.drawRoundedRect(QRectF(1.5, 2.5, 13, 9), 1.5, 1.5)
        p.drawLine(QPointF(5.5, 14), QPointF(10.5, 14))
    elif key == "events":                      # lista
        for y in (4, 8, 12):
            p.drawPoint(QPointF(2.5, y))
            p.drawLine(QPointF(5.5, y), QPointF(14, y))
    else:                                      # ajustes: engranaje simple
        p.drawEllipse(QRectF(5, 5, 6, 6))
        for a, b in (((8, 1.5), (8, 3.5)), ((8, 12.5), (8, 14.5)), ((1.5, 8), (3.5, 8)),
                     ((12.5, 8), (14.5, 8)), ((3.4, 3.4), (4.8, 4.8)), ((11.2, 11.2), (12.6, 12.6)),
                     ((3.4, 12.6), (4.8, 11.2)), ((11.2, 4.8), (12.6, 3.4))):
            p.drawLine(QPointF(*a), QPointF(*b))


def nav_pixmap(key: str, color: str, dpr: float = 2.0) -> QPixmap:
    pm = QPixmap(int(ICON_SIZE * dpr), int(ICON_SIZE * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    _draw_icon(p, key, ICON_SIZE)
    p.end()
    return pm


def nav_icon(key: str, muted: str, active: str) -> QIcon:
    """Gris si no está elegido, del color del elegido si lo está."""
    icon = QIcon()
    icon.addPixmap(nav_pixmap(key, muted), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(nav_pixmap(key, active), QIcon.Mode.Normal, QIcon.State.On)
    return icon


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
        colors = THEMES[theme_name(self.palette())]
        self._group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for key in PAGE_KEYS:
            btn = QPushButton(nav_title(key))
            btn.setIcon(nav_icon(key, colors["muted"], colors["nav_active"]))
            btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
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
        self.badge.setFixedHeight(BADGE_HEIGHT)      # pastilla redonda, no un óvalo alto
        self.badge.setMinimumWidth(BADGE_HEIGHT)
        self.badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.badge.hide()
        badge_lay.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch(1)

    def set_pending(self, n: int) -> None:
        self.badge.setText(str(n))
        self.badge.setVisible(n > 0)
