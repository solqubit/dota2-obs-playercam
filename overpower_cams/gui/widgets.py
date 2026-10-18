"""Piezas chicas de la ventana principal: estilos, puntos de estado, filas de revisión
y la cuadrícula de cámaras."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from ..i18n import tr

COLORS = {"ok": "#2e9e44", "warn": "#c98a16", "error": "#d14b3a", "idle": "#8a8a8a"}
ICONS = {"ok": "✔", "warn": "!", "error": "✖"}
ZWSP = "​"   # espacio de ancho cero: permite cortar la línea sin que se vea


def not_dota_msg() -> str:
    return tr("Esa carpeta no parece ser Dota 2 (falta game\\dota). Elige la carpeta "
              "«dota 2 beta», la que contiene la carpeta «game».")


APP_STYLE = """
QFrame#panel { border: 1px solid rgba(127,127,127,90); border-radius: 8px; }
QFrame#topbar { background: rgba(127,127,127,38); border-radius: 8px; }
QLabel#panelTitle { font-size: 11px; font-weight: bold; letter-spacing: 1px; color: palette(mid); }
QLabel#detail { font-size: 11px; color: palette(dark); }
QLabel#teamLabel { font-size: 11px; color: palette(dark); margin-top: 6px; }
QFrame#checkRow { border-bottom: 1px dashed rgba(127,127,127,50); }
QPushButton#seg { padding: 6px 14px; border: 1px solid rgba(127,127,127,90); }
QPushButton#seg:checked { background: rgba(80,140,255,90); font-weight: bold; }
"""


def dot_html(name: str, state: str, text: str) -> str:
    """'OBS ● conectado' con el punto del color del estado."""
    return (f'{name} <span style="color:{COLORS.get(state, COLORS["idle"])}">●</span> '
            f'{text}')


def panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(12, 10, 12, 10)
    lbl = QLabel(title.upper())
    lbl.setObjectName("panelTitle")
    lay.addWidget(lbl)
    return frame, lay


def detail_label(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("detail")
    lbl.setWordWrap(True)
    return lbl


class Segmented(QWidget):
    """Selector de dos o más opciones exclusivas (botones pegados)."""

    def __init__(self, options: list[tuple[str, object]], on_pick):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._group = QButtonGroup(self)
        self.buttons: dict[object, QPushButton] = {}
        for text, value in options:
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, v=value: on_pick(v))   # solo clicks del usuario
            self._group.addButton(b)
            lay.addWidget(b)
            self.buttons[value] = b
        lay.addStretch(1)

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
        lay.setContentsMargins(0, 4, 0, 4)
        icon = QLabel(ICONS.get(result.status, "?"))
        icon.setStyleSheet(f"color:{COLORS.get(result.status, COLORS['idle'])};"
                           "font-weight:bold; font-size:14px;")
        icon.setFixedWidth(18)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(icon)
        texts = QVBoxLayout()
        texts.setSpacing(0)
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
        col.setSpacing(3)
        for b in buttons:
            col.addWidget(b)
        lay.addLayout(col)
        if result.instructions:
            self.setToolTip(result.instructions)


class CameraGrid(QWidget):
    """Las 5 cámaras de un equipo; la que está al aire va resaltada."""

    def __init__(self, cameras: list[str]):
        super().__init__()
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(5)
        self.cells: dict[str, QLabel] = {}
        for i, cam in enumerate(cameras):
            cell = QLabel(str(i + 1))
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setToolTip(cam)
            cell.setMinimumHeight(28)
            lay.addWidget(cell, 0, i)
            self.cells[cam] = cell
        self._live = object()
        self.set_live(None)

    def set_live(self, camera: str | None) -> None:
        if camera == self._live:
            return   # sin cambios: no re-aplicar estilos cada segundo
        self._live = camera
        for cam, cell in self.cells.items():
            if cam == camera:
                cell.setStyleSheet("background: rgba(46,158,68,110); border-radius: 5px;"
                                   "font-weight: bold;")
            else:
                cell.setStyleSheet("background: rgba(127,127,127,30); border-radius: 5px;")
