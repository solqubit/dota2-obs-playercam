"""Estilos de la ventana: textos secundarios legibles en tema claro y oscuro, y los botones
elegidos (en negrita) sin texto cortado."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # antes de crear QApplication

from PySide6.QtGui import QColor, QFont, QFontMetrics, QPalette  # noqa: E402

from overpower_cams.gui.widgets import Segmented, app_style, muted_color


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


def test_icono_de_estado_tiene_un_color_distinto_por_estado(qapp):
    from overpower_cams.gui.widgets import StatusIcon
    for fondo in ("#1e1e1e", "#f0f0f0"):
        colores = {s: StatusIcon(s, _palette(fondo)).color().name() for s in ("ok", "warn", "error")}
        assert len(set(colores.values())) == 3, fondo
        for c in colores.values():
            assert _contraste(QColor(c), QColor(fondo)) >= 2.5, (fondo, c)
    assert StatusIcon("ok", _palette("#1e1e1e")).color().name() == "#3fb950"
    assert StatusIcon("error", _palette("#1e1e1e")).color().name() == "#f85149"


def test_icono_de_estado_se_dibuja_sin_texto(qapp):
    from PySide6.QtGui import QImage
    from overpower_cams.gui.widgets import StatusIcon
    icon = StatusIcon("error", _palette("#1e1e1e"))
    img = icon.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    centro_izq = img.pixelColor(3, img.height() // 2)          # el círculo, en rojo
    assert abs(centro_izq.red() - 0xf8) < 40 and centro_izq.green() < 120


def test_texto_largo_se_corta_con_puntos_suspensivos(qapp):
    from overpower_cams.gui.widgets import ElidedLabel
    lbl = ElidedLabel()
    lbl.set_full_text("una frase bastante larga que no entra en el ancho disponible")
    lbl.resize(120, 20)
    lbl.show()
    qapp.processEvents()
    assert lbl.text().endswith("…") and lbl.toolTip() == lbl.full_text()
    lbl.resize(2000, 20)
    qapp.processEvents()
    assert lbl.text() == lbl.full_text()
