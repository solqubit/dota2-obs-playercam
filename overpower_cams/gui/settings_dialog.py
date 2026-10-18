"""Diálogo de Ajustes (botón ⚙): contraseña y puerto de OBS, carpeta de Dota, bando
inicial del Equipo 1, idioma y "Olvidar retratos". No guarda nada en disco: la ventana principal
lee `values()` al aceptar y se encarga de guardar."""
from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import config, paths
from ..i18n import LANGUAGES, get_language, tr
from ..portraits import PortraitModel
from ..storage import Settings
from .widgets import detail_label, not_dota_msg


def _row(label: str, detail: str, field: QWidget) -> tuple[QWidget, QWidget]:
    left = QWidget()
    lay = QVBoxLayout(left)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(QLabel(label))
    if detail:
        lay.addWidget(detail_label(detail))
    # QFormLayout no siempre le da a la fila el alto del texto cortado en varias líneas (se
    # pisaban título y detalle): que nunca quede más baja que lo que pide.
    left.setMinimumHeight(left.sizeHint().height())
    return left, field


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, portraits: PortraitModel, *,
                 detected_dota: Path | None = None, intro: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Ajustes · {app}", app=config.app_name()))
        self.setMinimumWidth(520)
        self._settings = settings
        self._portraits = portraits
        self._dota_dir = settings.dota_dir
        self.portraits_forgotten = False

        root = QVBoxLayout(self)
        if intro:
            lbl = QLabel(intro)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-weight:bold;")
            root.addWidget(lbl)
        form = QFormLayout()
        root.addLayout(form)

        # Contraseña de OBS (oculta, con botón para mostrarla)
        self.password_edit = QLineEdit(settings.obs_password)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(tr("Pega aquí la contraseña de OBS"))
        self.show_button = QPushButton(tr("Mostrar"))
        self.show_button.setCheckable(True)
        self.show_button.toggled.connect(self._toggle_password)
        pw = QWidget()
        pw_lay = QHBoxLayout(pw)
        pw_lay.setContentsMargins(0, 0, 0, 0)
        pw_lay.addWidget(self.password_edit, 1)
        pw_lay.addWidget(self.show_button)
        form.addRow(*_row(tr("Contraseña de OBS WebSocket"),
                          tr("Se guarda solo en esta PC. En OBS: Herramientas → Ajustes del servidor "
                             "WebSocket → Mostrar información de conexión."), pw))

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(settings.obs_port)
        form.addRow(*_row(tr("Puerto de OBS"), tr("Por defecto {port}", port=config.DEFAULT_OBS_PORT),
                          self.port_spin))

        self.dota_label = QLabel()
        self.dota_label.setWordWrap(True)
        self._detected = detected_dota
        browse = QPushButton(tr("Buscar…"))
        browse.clicked.connect(self._browse_dota)
        dota = QWidget()
        dota_lay = QHBoxLayout(dota)
        dota_lay.setContentsMargins(0, 0, 0, 0)
        dota_lay.addWidget(self.dota_label, 1)
        dota_lay.addWidget(browse)
        self._dota_detail = detail_label()
        left, _ = _row(tr("Carpeta de Dota"), "", dota)
        left.layout().addWidget(self._dota_detail)
        form.addRow(left, dota)
        self._refresh_dota()

        self.team_combo = QComboBox()
        self.team_combo.addItem("Radiant", 1)
        self.team_combo.addItem("Dire", 2)
        self.team_combo.setCurrentIndex(0 if settings.default_radiant_team == 1 else 1)
        form.addRow(*_row(tr("Bando inicial del Equipo 1"),
                          tr("Valor por defecto si no hay uno guardado"), self.team_combo))

        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        current = settings.language or get_language()
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(current)))
        form.addRow(*_row(tr("Idioma / Language"), tr("Se aplica al reiniciar la app"),
                          self.language_combo))

        self.forget_button = QPushButton(tr("Olvidar"))
        self.forget_button.clicked.connect(self._forget_portraits)
        self._portraits_detail = detail_label()
        left, _ = _row(tr("Retratos aprendidos"), "", self.forget_button)
        left.layout().addWidget(self._portraits_detail)
        form.addRow(left, self.forget_button)
        self._refresh_portraits()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Guardar"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ---- acciones ----
    def _toggle_password(self, visible: bool) -> None:
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal if visible
                                       else QLineEdit.EchoMode.Password)
        self.show_button.setText(tr("Ocultar") if visible else tr("Mostrar"))

    def _refresh_dota(self) -> None:
        if self._dota_dir:
            self.dota_label.setText(self._dota_dir)
            self._dota_detail.setText(tr("Elegida a mano"))
        elif self._detected:
            self.dota_label.setText(str(self._detected))
            self._dota_detail.setText(tr("Encontrada automáticamente"))
        else:
            self.dota_label.setText(tr("(no encontrada)"))
            self._dota_detail.setText(tr("Pulsa «Buscar…» y elige la carpeta «dota 2 beta»"))

    def _browse_dota(self) -> None:
        start = self._dota_dir or (str(self._detected) if self._detected else "")
        d = QFileDialog.getExistingDirectory(self, tr("Elige la carpeta de Dota 2 («dota 2 beta»)"),
                                             start)
        if not d:
            return
        if not paths.is_dota_dir(d):
            QMessageBox.warning(self, tr("Carpeta equivocada"), not_dota_msg())
            return
        self._dota_dir = str(Path(d))
        self._refresh_dota()

    def _refresh_portraits(self) -> None:
        n = len(self._portraits.as_dict())
        self._portraits_detail.setText(tr("{n} afinados con tus clicks. «Olvidar» vuelve a la "
                                          "posición inicial.", n=n))

    def _forget_portraits(self) -> None:
        r = QMessageBox.question(
            self, tr("Olvidar retratos"),
            tr("Se borra lo que la app aprendió de tus clicks en los retratos y vuelve a la "
               "posición inicial (los 10 siguen ubicados). ¿Continuar?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self._portraits.forget_all()
            self.portraits_forgotten = True
            self._refresh_portraits()

    # ---- resultado ----
    def values(self) -> Settings:
        """Ajustes nuevos (copia; el original no se toca)."""
        return replace(self._settings,
                       obs_password=self.password_edit.text().strip(),
                       obs_port=self.port_spin.value(),
                       dota_dir=self._dota_dir,
                       default_radiant_team=self.team_combo.currentData(),
                       language=self.language_combo.currentData())
