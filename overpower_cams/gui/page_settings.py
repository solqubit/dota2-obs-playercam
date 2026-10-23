"""Página Ajustes: OBS (dirección, puerto, contraseña y escena principal), Dota (carpeta y
"Olvidar retratos"), idioma y qué pasa al arrancar (equipo Radiant y modo).

No guarda nada en disco: "Guardar" llama a `on_save(values())` y la ventana se encarga de
guardar y reconectar. "Olvidar retratos" actúa al momento (tras confirmar) y avisa con
`on_forget_portraits()`."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
                               QVBoxLayout, QWidget)

from .. import config, paths
from ..i18n import LANGUAGES, get_language, tr
from ..players import TeamsConfig
from ..portraits import PortraitModel
from ..storage import Settings
from .status_bar import team_names
from .widgets import card, detail_label, not_dota_msg, page_header

COMBO_MIN_WIDTH = 240
BODY_MAX_WIDTH = 880   # en ventanas anchas, los campos no se estiran de más


def _row(label: str, detail: str = "") -> tuple[QWidget, QVBoxLayout]:
    left = QWidget()
    lay = QVBoxLayout(left)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(1)
    lay.addWidget(QLabel(label))
    if detail:
        lay.addWidget(detail_label(detail))
    left.setMinimumWidth(240)
    return left, lay


def _hbox(*widgets, stretch_first=True) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for i, x in enumerate(widgets):
        lay.addWidget(x, 1 if (i == 0 and stretch_first) else 0)
    return w


class SettingsPage(QWidget):
    def __init__(self, settings: Settings, portraits: PortraitModel, *,
                 detected_dota: Path | None = None, teams: TeamsConfig | None = None,
                 on_save=None, on_forget_portraits=None):
        super().__init__()
        self._portraits = portraits
        self._on_save = on_save
        self._on_forget = on_forget_portraits

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(14)
        root.addWidget(page_header(tr("Ajustes"), tr("Se guardan solo en esta PC.")))
        self.intro_label = QLabel()
        self.intro_label.setObjectName("intro")
        self.intro_label.setWordWrap(True)
        self.intro_label.hide()
        root.addWidget(self.intro_label)

        body = QWidget()
        body.setMaximumWidth(BODY_MAX_WIDTH)
        cards = QVBoxLayout(body)
        cards.setContentsMargins(0, 0, 6, 0)
        cards.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ---- OBS ----
        frame, lay = card("OBS")
        form = self._form(lay)
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText(config.OBS_HOST)
        form.addRow(_row(tr("Dirección de OBS"), tr("Normalmente {host} (esta misma PC)",
                                                    host=config.OBS_HOST))[0], self.host_edit)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        form.addRow(_row(tr("Puerto de OBS"), tr("Por defecto {port}", port=config.DEFAULT_OBS_PORT))[0],
                    self.port_spin)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(tr("Pega aquí la contraseña de OBS"))
        self.show_button = QPushButton(tr("Mostrar"))
        self.show_button.setCheckable(True)
        self.show_button.toggled.connect(self._toggle_password)
        form.addRow(_row(tr("Contraseña de OBS WebSocket"),
                         tr("Se guarda solo en esta PC. En OBS: Herramientas → Ajustes del servidor "
                            "WebSocket → Mostrar información de conexión."))[0],
                    _hbox(self.password_edit, self.show_button))
        self.main_scene_edit = QLineEdit()
        self.main_scene_edit.setPlaceholderText(config.DEFAULT_MAIN_SCENE)
        form.addRow(_row(tr("Escena principal"),
                         tr("La escena que tiene las 10 escenas de jugador. Por defecto «{scene}».",
                            scene=config.DEFAULT_MAIN_SCENE))[0], self.main_scene_edit)
        cards.addWidget(frame)

        # ---- Dota ----
        frame, lay = card("Dota")
        form = self._form(lay)
        self.dota_label = QLabel()
        self.dota_label.setWordWrap(True)
        self.browse_button = QPushButton(tr("Buscar…"))
        self.browse_button.clicked.connect(self._browse_dota)
        left, left_lay = _row(tr("Carpeta de Dota"))
        self._dota_detail = detail_label()
        left_lay.addWidget(self._dota_detail)
        form.addRow(left, _hbox(self.dota_label, self.browse_button))
        self.forget_button = QPushButton(tr("Olvidar"))
        self.forget_button.clicked.connect(self._forget_portraits)
        left, left_lay = _row(tr("Retratos aprendidos"))
        self._portraits_detail = detail_label()
        left_lay.addWidget(self._portraits_detail)
        form.addRow(left, _hbox(QWidget(), self.forget_button))
        cards.addWidget(frame)

        # ---- Idioma ----
        frame, lay = card(tr("Idioma"))
        form = self._form(lay)
        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        form.addRow(_row(tr("Idioma / Language"), tr("Se aplica al reiniciar la app"))[0],
                    self.language_combo)
        cards.addWidget(frame)

        # ---- Al arrancar ----
        frame, lay = card(tr("Al arrancar"))
        form = self._form(lay)
        self.team_combo = QComboBox()
        self.team_combo.addItem("", 1)
        self.team_combo.addItem("", 2)
        form.addRow(_row(tr("Radiant al arrancar"),
                         tr("Qué equipo es Radiant si no hay uno guardado de la vez anterior"))[0],
                    self.team_combo)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("Automático"), "auto")
        self.mode_combo.addItem(tr("Ocultar todo"), "hidden")
        form.addRow(_row(tr("Modo inicial"),
                         tr("El modo si no hay uno guardado de la vez anterior"))[0], self.mode_combo)
        cards.addWidget(frame)
        cards.addStretch(1)

        # ---- botones ----
        self.revert_button = QPushButton(tr("Descartar cambios"))
        self.revert_button.clicked.connect(lambda: self.load(self._source))
        self.save_button = QPushButton(tr("Guardar"))
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._save)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.revert_button)
        buttons.addWidget(self.save_button)
        root.addLayout(buttons)

        for w in (self.port_spin, self.language_combo, self.team_combo, self.mode_combo):
            w.setMinimumWidth(COMBO_MIN_WIDTH)
            w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._detected = detected_dota
        self.set_team_names(teams or TeamsConfig())
        self.load(settings, detected_dota)

    @staticmethod
    def _form(lay: QVBoxLayout) -> QFormLayout:
        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        lay.addLayout(form)
        return form

    # ---- cargar / leer ----
    def load(self, settings: Settings, detected_dota: Path | None = None) -> None:
        """Muestra `settings` (descarta lo no guardado). El original no se toca."""
        self._source = settings
        if detected_dota is not None:
            self._detected = detected_dota
        self.host_edit.setText(settings.obs_host)
        self.port_spin.setValue(settings.obs_port)
        self.password_edit.setText(settings.obs_password)
        self.main_scene_edit.setText(settings.main_scene)
        self._dota_dir = settings.dota_dir
        self._refresh_dota()
        self._refresh_portraits()
        current = settings.language or get_language()
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(current)))
        self.team_combo.setCurrentIndex(0 if settings.default_radiant_team == 1 else 1)
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(settings.default_mode)))
        self._loaded = self.values()

    def values(self) -> Settings:
        """Ajustes nuevos (copia; el original no se toca)."""
        return replace(self._source,
                       obs_host=self.host_edit.text().strip() or config.OBS_HOST,
                       obs_port=self.port_spin.value(),
                       obs_password=self.password_edit.text().strip(),
                       main_scene=self.main_scene_edit.text().strip() or config.DEFAULT_MAIN_SCENE,
                       dota_dir=self._dota_dir,
                       language=self.language_combo.currentData(),
                       default_radiant_team=self.team_combo.currentData(),
                       default_mode=self.mode_combo.currentData())

    def is_dirty(self) -> bool:
        return self.values() != self._loaded

    def set_intro(self, text: str | None) -> None:
        self.intro_label.setText(text or "")
        self.intro_label.setVisible(bool(text))

    def set_team_names(self, teams: TeamsConfig) -> None:
        for i, name in enumerate(team_names(teams)):
            self.team_combo.setItemText(i, name)

    # ---- acciones ----
    def _save(self) -> None:
        if self._on_save is not None:
            self._on_save(self.values())

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
            self._refresh_portraits()
            if self._on_forget is not None:
                self._on_forget()
