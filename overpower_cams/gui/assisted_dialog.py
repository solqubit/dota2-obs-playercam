"""Diálogo «Cámara asistida»: captura la próxima tecla que se pulsa, la muestra con el nombre
que usa Dota y dice en vivo si está libre o qué acción de Dota ya la usa (entonces no deja
guardar). Lo abren los botones Configurar… / Cambiar… de Revisión; quien lo abre escribe el
autoexec.cfg (en otro hilo) si el usuario guarda o quita."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..dota_keys import _KP_NAMES, normalize_key
from ..i18n import tr
from .widgets import app_style, detail_label, repolish, status_colors

_K = Qt.Key
MODIFIER_KEYS = {int(k) for k in (_K.Key_Shift, _K.Key_Control, _K.Key_Alt, _K.Key_Meta,
                                  _K.Key_AltGr, _K.Key_Super_L, _K.Key_Super_R)}
EXTENDED = 0x100   # Qt en Windows: código de exploración con el bit "extendida" (lParam bit 24)

# Dota asigna las teclas por su POSICIÓN en un teclado US, no por la letra que escribe la
# distribución de Windows (en un teclado español la tecla a la derecha del 0 escribe «'», pero
# para Dota es «-»). Por eso se mapea el código de exploración (set 1) y no QKeyEvent.key().
# El bit extendido separa el teclado numérico (sin extendido) de Inicio/Fin/flechas dedicadas
# (con extendido), con Bloq Num activado o no.
_SCAN_NAMES: dict[int, str] = {
    0x0C: "-", 0x0D: "=", 0x0E: "BACKSPACE", 0x0F: "TAB", 0x1A: "[", 0x1B: "]", 0x1C: "ENTER",
    0x27: "SEMICOLON", 0x28: "'", 0x29: "`", 0x2B: "\\", 0x33: ",", 0x34: ".", 0x35: "/",
    0x39: "SPACE", 0x3A: "CAPSLOCK", 0x45: "PAUSE", 0x46: "SCROLLLOCK", 0x57: "F11", 0x58: "F12",
    # teclado numérico (sin bit extendido)
    0x47: "KP_HOME", 0x48: "KP_UPARROW", 0x49: "KP_PGUP", 0x4A: "KP_MINUS",
    0x4B: "KP_LEFTARROW", 0x4C: "KP_5", 0x4D: "KP_RIGHTARROW", 0x4E: "KP_PLUS",
    0x4F: "KP_END", 0x50: "KP_DOWNARROW", 0x51: "KP_PGDN", 0x52: "KP_INS", 0x53: "KP_DEL",
    0x37: "KP_MULTIPLY", EXTENDED | 0x35: "KP_SLASH", EXTENDED | 0x1C: "KP_ENTER",
    EXTENDED | 0x45: "NUMLOCK",
    # bloque de navegación dedicado (con bit extendido)
    EXTENDED | 0x47: "HOME", EXTENDED | 0x48: "UPARROW", EXTENDED | 0x49: "PGUP",
    EXTENDED | 0x4B: "LEFTARROW", EXTENDED | 0x4D: "RIGHTARROW", EXTENDED | 0x4F: "END",
    EXTENDED | 0x50: "DOWNARROW", EXTENDED | 0x51: "PGDN", EXTENDED | 0x52: "INS",
    EXTENDED | 0x53: "DEL",
}
_SCAN_NAMES.update({0x02 + i: str((i + 1) % 10) for i in range(10)})          # 1..9, 0
_SCAN_NAMES.update({0x3B + i: f"F{i + 1}" for i in range(10)})                 # F1..F10
for _fila, _letras in ((0x10, "QWERTYUIOP"), (0x1E, "ASDFGHJKL"), (0x2C, "ZXCVBNM")):
    _SCAN_NAMES.update({_fila + i: c for i, c in enumerate(_letras)})
MODIFIER_SCANS = {0x1D, EXTENDED | 0x1D, 0x2A, 0x36, 0x38, EXTENDED | 0x38,
                  EXTENDED | 0x5B, EXTENDED | 0x5C}
ESCAPE_SCAN = 0x01

# Sin código de exploración (no debería pasar en Windows): solo teclas virtuales que no
# dependen de la distribución del teclado.
_VK_NAMES: dict[int, str] = {0x70 + i: f"F{i + 1}" for i in range(12)}
_VK_NAMES.update({0x60 + n: name for name, n in _KP_NAMES.items()})
_VK_NAMES.update({0x6A: "KP_MULTIPLY", 0x6B: "KP_PLUS", 0x6D: "KP_MINUS", 0x6F: "KP_SLASH"})


def native_key_to_dota(scan_code: int, virtual_key: int = 0) -> str | None:
    """Tecla física (código de exploración de Windows con el bit extendido 0x100, o si no hay,
    la tecla virtual) -> nombre de Dota según el teclado US ("F4", "A", "-", "KP_END", "END"…).
    None si no tiene un nombre seguro en Dota (modificadores, Escape, la tecla «<» de los
    teclados europeos, Windows, Imprimir pantalla…)."""
    scan = int(scan_code or 0) & 0x1FF
    if scan:
        if scan in MODIFIER_SCANS or scan == ESCAPE_SCAN:
            return None
        return _SCAN_NAMES.get(scan)
    return _VK_NAMES.get(int(virtual_key or 0))


_MODS = (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier
         | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)


def _is_modifier_press(e) -> bool:
    return int(e.key()) in MODIFIER_KEYS or (int(e.nativeScanCode()) & 0x1FF) in MODIFIER_SCANS


def _is_escape(e) -> bool:
    scan = int(e.nativeScanCode()) & 0x1FF
    return scan == ESCAPE_SCAN or (not scan and int(e.key()) == int(_K.Key_Escape))


class AssistedKeyDialog(QDialog):
    """`current`: la tecla que ya tiene (o None). `conflicts(key) -> [nombres]`: qué de Dota
    usa esa tecla. Al cerrar con Guardar queda `key`; con Quitar, `remove_requested`."""

    def __init__(self, parent, current: str | None, conflicts):
        super().__init__(parent)
        self.setObjectName("keyDialog")
        if parent is None:                       # suelto (tests, capturas): el tema de la app
            self.setStyleSheet(app_style(self.palette()))
        self.setWindowTitle(tr("Cámara asistida"))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(460)
        self._conflicts = conflicts
        self._current = normalize_key(current) if current else None
        self.key: str | None = None
        self.remove_requested = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        title = QLabel(tr("Cámara asistida"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        self.prompt_label = QLabel(tr("Pulsa la tecla que quieres usar para la cámara asistida"))
        self.prompt_label.setWordWrap(True)
        lay.addWidget(self.prompt_label)
        self.key_label = QLabel(self._current or "—")
        self.key_label.setObjectName("keyCap")
        self.key_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.key_label, 0, Qt.AlignmentFlag.AlignHCenter)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.status_label)
        lay.addWidget(detail_label(tr("Esc cancela. Los atajos de Dota le ganan a esta tecla: "
                                      "tiene que estar libre en Dota (Ajustes → Teclas rápidas).")))

        botones = QHBoxLayout()
        self.remove_button = QPushButton(tr("Quitar"))
        self.remove_button.clicked.connect(self._remove)
        self.remove_button.setVisible(self._current is not None)
        self.cancel_button = QPushButton(tr("Cancelar"))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton(tr("Guardar"))
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.accept)
        for b in (self.remove_button, self.cancel_button, self.save_button):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # las teclas van al diálogo, no a un botón
            b.setAutoDefault(False)
        botones.addWidget(self.remove_button)
        botones.addStretch(1)
        botones.addWidget(self.cancel_button)
        botones.addWidget(self.save_button)
        lay.addLayout(botones)

        self.save_button.setEnabled(False)
        if self._current:
            self._status("idle", tr("Tecla actual: {key}. Pulsa otra para cambiarla.", key=self._current))
        else:
            self._status("idle", tr("Esperando una tecla…"))

    def _status(self, state: str, text: str) -> None:
        color = status_colors(self.palette()).get(state, status_colors(self.palette())["idle"])
        self.status_label.setText(f'<span style="color:{color}">●</span> {text}')

    def _remove(self) -> None:
        self.remove_requested = True
        self.accept()

    def set_key(self, key: str) -> None:
        """Elige `key` (nombre de Dota) y muestra si está libre."""
        key = normalize_key(key)
        self.key = key
        self.key_label.setText(key)
        self.key_label.setProperty("chosen", True)
        repolish(self.key_label)
        if key == self._current:
            self.save_button.setEnabled(False)
            self._status("ok", tr("{key} ya es la tecla de la cámara asistida", key=key))
            return
        usan = self._conflicts(key)
        if usan:
            self.save_button.setEnabled(False)
            self._status("error", tr("{key} ya la usa «{actions}» en Dota; Dota gana. Elige otra "
                                     "tecla o cámbiala en Dota.", key=key, actions="», «".join(usan)))
        else:
            self.save_button.setEnabled(True)
            self._status("ok", tr("{key} está libre: nada de Dota la usa", key=key))

    def event(self, e) -> bool:
        # Todas las teclas (Tab y Enter incluidos) son la tecla elegida, no navegación.
        if e.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(e)
            return True
        return super().event(e)

    def keyPressEvent(self, e) -> None:
        if _is_escape(e):
            self.reject()
            return
        if _is_modifier_press(e):
            self._status("warn", tr("Shift, Ctrl o Alt solos no sirven: pulsa otra tecla"))
            return
        if e.modifiers() & _MODS:
            self._status("warn", tr("Pulsa la tecla sola, sin modificadores (Shift, Ctrl, Alt)"))
            return
        name = native_key_to_dota(e.nativeScanCode(), e.nativeVirtualKey())
        if name is None:
            self._status("warn", tr("Dota no conoce esa tecla: prueba con otra"))
            return
        self.set_key(name)
