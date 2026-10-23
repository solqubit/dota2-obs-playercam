"""Piezas chicas de la ventana: tema (oscuro/claro, boceto D v2), puntos de estado,
encabezados de página, tarjetas, selector segmentado y filas de revisión."""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..i18n import tr

# Colores de estado (oscuro, del boceto) y su versión para fondo claro (más contraste).
COLORS = {"ok": "#3fb950", "warn": "#d29922", "error": "#f85149", "idle": "#8a8a8a"}
COLORS_LIGHT = {"ok": "#1a7f37", "warn": "#9a6700", "error": "#cf222e", "idle": "#6e7781"}
ZWSP = "​"   # espacio de ancho cero: permite cortar la línea sin que se vea

# Colores del boceto D v2 (oscuro) y su variante clara.
THEMES = {
    "dark": {
        "bg": "#16191f", "card": "#1f232b", "border": "#2c323c", "text": "#e6e8ec",
        "muted": "#9aa3af", "input": "#11141a", "input_text": "#c9d1d9", "hover": "#262b34",
        "accent": "#2f6feb", "accent_soft": "rgba(47,111,235,46)", "nav_active": "#ffffff",
        "onair_bg": "#173b22", "onair_border": "#2ea043", "onair_text": "#e6e8ec",
        "intro_bg": "#3a2d12", "intro_border": "#d29922", "onair_row": "rgba(46,160,67,40)",
    },
    "light": {
        "bg": "#f3f5f8", "card": "#ffffff", "border": "#d5dae1", "text": "#1f2328",
        "muted": "#5f5f5f", "input": "#ffffff", "input_text": "#1f2328", "hover": "#e8ecf1",
        "accent": "#2f6feb", "accent_soft": "rgba(47,111,235,30)", "nav_active": "#1747a6",
        "onair_bg": "#dafbe1", "onair_border": "#2ea043", "onair_text": "#0f3d1c",
        "intro_bg": "#fff3d6", "intro_border": "#d29922", "onair_row": "rgba(46,160,67,34)",
    },
}


def not_dota_msg() -> str:
    return tr("Esa carpeta no parece ser Dota 2 (falta game\\dota). Elige la carpeta "
              "«dota 2 beta», la que contiene la carpeta «game».")


SEG_PADDING_X = 14   # px a cada lado del texto en los botones del selector


def theme_name(palette: QPalette) -> str:
    """"dark" o "light", según el tema del sistema."""
    return "dark" if palette.color(QPalette.ColorRole.Window).lightness() < 128 else "light"


def status_colors(palette: QPalette) -> dict[str, str]:
    return COLORS if theme_name(palette) == "dark" else COLORS_LIGHT


def muted_color(palette: QPalette) -> str:
    """Gris para textos secundarios, legible sobre el fondo del tema (claro u oscuro).
    Los roles del tema (mid, dark) quedan casi negros en el modo oscuro de Windows."""
    return THEMES[theme_name(palette)]["muted"]


def app_style(palette: QPalette) -> str:
    c = dict(THEMES[theme_name(palette)], seg=SEG_PADDING_X, warn=COLORS["warn"])
    return """
QMainWindow, QWidget#central {{ background: {bg}; }}
QWidget {{ color: {text}; }}
QToolTip {{ background: {card}; color: {text}; border: 1px solid {border}; padding: 4px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QFrame#card {{ background: {card}; border: 1px solid {border}; border-radius: 10px; }}
QFrame#card QLabel {{ background: transparent; }}
QLabel#cardTitle, QLabel#panelTitle {{ font-size: 11px; font-weight: bold; letter-spacing: 1px;
    color: {muted}; }}
QLabel#detail {{ font-size: 11px; color: {muted}; }}
QLabel#fieldLabel {{ font-size: 11px; color: {muted}; }}
QLabel#pageTitle {{ font-size: 19px; font-weight: 600; }}
QLabel#pageSubtitle {{ font-size: 12px; color: {muted}; }}
QLabel#intro {{ background: {intro_bg}; border: 1px solid {intro_border}; border-radius: 8px;
    padding: 8px 12px; font-weight: bold; }}

QFrame#sidebar {{ background: {bg}; }}
QLabel#brand {{ font-size: 15px; font-weight: bold; }}
QLabel#brandSub {{ font-size: 11px; color: {muted}; }}
QPushButton#navItem {{ text-align: left; padding: 9px 12px; border: none; border-radius: 8px;
    background: transparent; color: {muted}; font-size: 13px; }}
QPushButton#navItem:hover {{ background: {hover}; color: {text}; }}
QPushButton#navItem:checked {{ background: {accent_soft}; color: {nav_active}; font-weight: 600;
    border-left: 3px solid {accent}; border-top-left-radius: 3px; border-bottom-left-radius: 3px;
    padding-left: 9px; }}
QLabel#badge {{ background: {warn}; color: #000000; border-radius: 9px; padding: 0px 5px;
    font-size: 10px; font-weight: bold; }}

QLabel#statusTitle {{ font-size: 13px; font-weight: bold; }}
QLabel#statusDetail {{ font-size: 11px; color: {muted}; }}
QFrame#onAir {{ border-radius: 8px; border: 1px solid {border}; background: transparent; }}
QFrame#onAir QLabel {{ color: {muted}; font-weight: 600; }}
QFrame#onAir[live="true"] {{ background: {onair_bg}; border: 1px solid {onair_border}; }}
QFrame#onAir[live="true"] QLabel {{ color: {onair_text}; }}
QFrame#onAir[live="true"] QLabel#onAirDot {{ color: {onair_border}; }}

QLineEdit, QComboBox {{ background: {input}; color: {input_text};
    border: 1px solid {border}; border-radius: 7px; padding: 5px 8px; min-height: 18px;
    selection-background-color: {accent}; selection-color: #ffffff; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {accent}; }}
QComboBox QAbstractItemView {{ background: {card}; color: {text}; border: 1px solid {border};
    selection-background-color: {accent}; selection-color: #ffffff; outline: none; }}

QPushButton {{ background: {hover}; color: {text}; border: 1px solid {border}; border-radius: 7px;
    padding: 6px 14px; }}
QPushButton:hover {{ border: 1px solid {accent}; }}
QPushButton:pressed {{ background: {hover}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#primary {{ background: {accent}; color: #ffffff; border: 1px solid {accent};
    font-weight: 600; }}

QPushButton#seg {{ padding: 5px {seg}px; border: 1px solid {border}; border-radius: 0px;
    background: {input}; color: {muted}; }}
QPushButton#seg[pos="first"] {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
QPushButton#seg[pos="last"] {{ border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
QPushButton#seg[pos="middle"], QPushButton#seg[pos="last"] {{ border-left: none; }}
QPushButton#seg:hover {{ color: {text}; }}
QPushButton#seg:checked {{ background: {accent}; color: #ffffff; font-weight: 600;
    border-color: {accent}; }}

QListWidget#eventList {{ background: {card}; border: 1px solid {border}; border-radius: 10px;
    padding: 8px; font-family: Consolas, monospace; font-size: 12px; }}
QListWidget#eventList::item {{ padding: 3px 4px; border-bottom: 1px solid {border}; }}
QFrame#checkRow {{ border: none; border-bottom: 1px solid {border}; }}
QFrame#tableRow {{ background: transparent; border: none; border-bottom: 1px solid {border};
    border-radius: 0px; }}
QFrame#tableRow[onair="true"] {{ background: {onair_row}; }}
QLabel#colHeader {{ font-size: 12px; color: {muted}; }}
QLabel#teamHint {{ font-size: 12px; color: {muted}; }}
""".format(**c)


def dot_html(name: str, state: str, text: str, colors: dict[str, str] = COLORS) -> str:
    """'OBS ● conectado' con el punto del color del estado (● no es emoji: respeta el color)."""
    return (f'{name} <span style="color:{colors.get(state, colors["idle"])}">●</span> '
            f'{text}')


def card(title: str | None = None, *, margins=(16, 14, 16, 14)) -> tuple[QFrame, QVBoxLayout]:
    """Tarjeta del boceto (fondo, borde y esquinas redondeadas), con título opcional."""
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(10)
    if title:
        lbl = QLabel(title.upper())
        lbl.setObjectName("cardTitle")
        lay.addWidget(lbl)
    return frame, lay


def page_header(title: str, subtitle: str = "", *right: QWidget) -> QWidget:
    """Título grande de la página, una línea de ayuda y botones opcionales a la derecha."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    texts = QVBoxLayout()
    texts.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("pageTitle")
    texts.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("pageSubtitle")
        s.setWordWrap(True)
        texts.addWidget(s)
    lay.addLayout(texts, 1)
    for r in right:
        lay.addWidget(r, 0, Qt.AlignmentFlag.AlignBottom)
    return w


def page_layout(title: str, subtitle: str = "", *right: QWidget) -> tuple[QWidget, QVBoxLayout]:
    """Página vacía con su encabezado; devuelve (página, layout para el contenido)."""
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(0, 4, 0, 0)
    lay.setSpacing(14)
    lay.addWidget(page_header(title, subtitle, *right))
    return page, lay


def detail_label(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("detail")
    lbl.setWordWrap(True)
    return lbl


def field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("fieldLabel")
    return lbl


def repolish(w: QWidget) -> None:
    """Vuelve a aplicar el estilo tras cambiar una propiedad usada en los selectores."""
    for x in [w, *w.findChildren(QWidget)]:
        x.style().unpolish(x)
        x.style().polish(x)


class StatusIcon(QWidget):
    """Círculo del color del estado con ✓ / ! / ✕ dibujados a mano (no depende de fuentes:
    un emoji de color haría que error y ok se vean iguales)."""
    SIZE = 18

    def __init__(self, status: str, palette: QPalette | None = None):
        super().__init__()
        self.status = status
        self._colors = status_colors(palette if palette is not None else self.palette())
        self.setFixedSize(self.SIZE, self.SIZE)

    def color(self) -> QColor:
        return QColor(self._colors.get(self.status, self._colors["idle"]))

    def set_status(self, status: str) -> None:
        if status != self.status:
            self.status = status
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.SIZE, self.SIZE)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = float(self.SIZE)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color())
        p.drawEllipse(QRectF(0.5, 0.5, s - 1, s - 1))
        pen = QPen(QColor("#ffffff"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.status == "ok":
            path = QPainterPath(QPointF(s * 0.28, s * 0.52))
            path.lineTo(QPointF(s * 0.44, s * 0.68))
            path.lineTo(QPointF(s * 0.73, s * 0.35))
            p.drawPath(path)
        elif self.status == "error":
            a, b = s * 0.33, s * 0.67
            p.drawLine(QPointF(a, a), QPointF(b, b))
            p.drawLine(QPointF(a, b), QPointF(b, a))
        else:   # warn u otro: signo de exclamación
            p.drawLine(QPointF(s / 2, s * 0.27), QPointF(s / 2, s * 0.56))
            p.drawPoint(QPointF(s / 2, s * 0.73))
        p.end()


class ElidedLabel(QLabel):
    """Una sola línea; si no entra, se corta con "…" y el texto entero queda en el tooltip."""

    def __init__(self, text: str = ""):
        super().__init__()
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        if text == self._full:
            return
        self._full = text
        self.setToolTip(text)
        self._elide()

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight,
                                              max(0, self.width()))
        if shown != self.text():
            self.setText(shown)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()


class Segmented(QWidget):
    """Selector de dos o más opciones exclusivas (botones pegados)."""

    def __init__(self, options: list[tuple[str, object]], on_pick):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._group = QButtonGroup(self)
        self.buttons: dict[object, QPushButton] = {}
        n = len(options)
        for i, (text, value) in enumerate(options):
            b = QPushButton()
            b.setObjectName("seg")
            b.setProperty("pos", "first" if i == 0 else "last" if i == n - 1 else "middle")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=value: on_pick(v))   # solo clicks del usuario
            self._group.addButton(b)
            lay.addWidget(b)
            self.buttons[value] = b
            self.set_label(value, text)
        lay.addStretch(1)

    def set_label(self, value, text: str) -> None:
        b = self.buttons[value]
        if b.text() == text:
            return
        b.setText(text)
        # el elegido va en negrita: reservar ese ancho para que el texto no se corte
        bold = QFont(b.font())
        bold.setBold(True)
        b.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(text) + 2 * SEG_PADDING_X + 8)

    def set_value(self, value) -> None:
        b = self.buttons.get(value)
        if b is not None and not b.isChecked():
            b.setChecked(True)   # setChecked no emite clicked


class CheckRow(QFrame):
    """Una revisión: icono, título, detalle y botones a la derecha."""

    def __init__(self, result, buttons: list[QPushButton]):
        super().__init__()
        self.setObjectName("checkRow")
        self.result = result
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 8, 2, 10)
        lay.setSpacing(10)
        self.icon = StatusIcon(result.status)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel(result.title)
        title.setStyleSheet("font-weight:bold;")
        texts.addWidget(title)
        # Las rutas largas no tienen espacios: se les da dónde cortar para no ensanchar la columna.
        breakable = result.detail.replace("\\", "\\" + ZWSP).replace("/", "/" + ZWSP)
        detail = detail_label(breakable)
        detail.setMinimumWidth(1)
        texts.addWidget(detail)
        lay.addLayout(texts, 1)
        col = QVBoxLayout()
        col.setSpacing(4)
        for b in buttons:
            col.addWidget(b)
        col.addStretch(1)
        lay.addLayout(col)
        if result.instructions:
            self.setToolTip(result.instructions)
