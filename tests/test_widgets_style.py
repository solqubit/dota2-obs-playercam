"""Estilos de la ventana: textos secundarios legibles en tema claro y oscuro, y los botones
elegidos (en negrita) sin texto cortado."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # antes de crear QApplication

import pytest
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from overpower_cams.gui.widgets import Segmented, app_style, muted_color


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _palette(window: str) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(window))
    return p


def _contraste(a: QColor, b: QColor) -> float:
    def lum(c):
        def ch(v):
            v /= 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_texto_secundario_legible_en_tema_oscuro_y_claro(qapp):
    for fondo in ("#1e1e1e", "#202020", "#f0f0f0", "#ffffff"):
        color = QColor(muted_color(_palette(fondo)))
        assert _contraste(color, QColor(fondo)) >= 4.5, fondo


def test_el_estilo_no_usa_colores_del_tema_que_desaparecen_en_oscuro(qapp):
    estilo = app_style(_palette("#1e1e1e"))
    assert "palette(mid)" not in estilo and "palette(dark)" not in estilo
    assert muted_color(_palette("#1e1e1e")) in estilo


def test_boton_elegido_reserva_el_ancho_de_la_negrita(qapp):
    seg = Segmented([("Radiant", 1), ("Dire", 2)], lambda v: None)
    seg.set_value(1)
    for b in seg.buttons.values():
        negrita = QFont(b.font())
        negrita.setBold(True)
        assert b.minimumWidth() >= QFontMetrics(negrita).horizontalAdvance(b.text()) + 28
