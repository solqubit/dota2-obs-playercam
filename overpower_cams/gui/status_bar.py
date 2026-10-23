"""Barra de estados (OBS, Dota, Partida y quién está al aire) y barra en vivo (qué equipo
es Radiant y el modo), siempre visibles arriba de la ventana. Solo muestran: la ventana
les pasa los datos y recibe los clicks."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..i18n import tr
from ..players import PlayerConfig, TeamsConfig
from .widgets import ElidedLabel, Segmented, field_label, repolish


def hero_display(hero: str | None) -> str:
    return hero.replace("_", " ").title() if hero else ""


def team_names(teams: TeamsConfig) -> tuple[str, str]:
    """Nombres de los equipos; si están vacíos, "Equipo 1" / "Equipo 2"."""
    return (teams.team1.strip() or tr("Equipo 1"), teams.team2.strip() or tr("Equipo 2"))


def ago_text(seconds: float) -> str:
    s = max(0, int(seconds))
    return tr("hace {n} s", n=s) if s < 120 else tr("hace {n} min", n=s // 60)


def clock_text(clock_time: int | None) -> str:
    if clock_time is None:
        return "—"
    sign = "-" if clock_time < 0 else ""
    m, s = divmod(abs(clock_time), 60)
    return f"{sign}{m}:{s:02d}"


def input_note(mode: str) -> str:
    if mode == "auto":
        return tr("Para cambiar al instante, la app detecta las teclas y clicks mientras "
                  "Dota está activo.")
    return tr("Con «Ocultar todo» la app no escucha el teclado ni el mouse.")


def on_air_text(st, players: dict[str, PlayerConfig]) -> str:
    """'Al aire: jugador · escena · héroe · N habilidades' (o que no hay nada al aire)."""
    if not st.camera:
        if st.mode == "hidden":
            return tr("Al aire: nada (Ocultar todo)")
        return tr("Al aire: ninguna cámara")
    p = players.get(st.camera)
    parts = [p.name.strip()] if p is not None and p.name.strip() else []
    parts.append(st.camera)
    hero = hero_display(st.hero)
    if hero:
        parts.append(hero)
    parts.append(tr("{n} habilidades", n=st.abilities.get(st.camera, 4)))
    return tr("Al aire: {details}", details=" · ".join(parts))


class StatusItem(QWidget):
    """Título en negrita con su punto de color y una línea chica debajo."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        self.title = QLabel()
        self.title.setObjectName("statusTitle")
        self.title.setTextFormat(Qt.TextFormat.RichText)
        self.detail = QLabel()
        self.detail.setObjectName("statusDetail")
        lay.addWidget(self.title)
        lay.addWidget(self.detail)

    def set(self, title_html: str, detail: str) -> None:
        if self.title.text() != title_html:
            self.title.setText(title_html)
        if self.detail.text() != detail:
            self.detail.setText(detail)


class StatusBar(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 12, 10)
        lay.setSpacing(28)
        self.obs, self.dota, self.game = StatusItem(), StatusItem(), StatusItem()
        for item in (self.obs, self.dota, self.game):
            lay.addWidget(item)
        lay.addStretch(1)
        self.on_air = QFrame()
        self.on_air.setObjectName("onAir")
        self.on_air.setProperty("live", False)
        pill = QHBoxLayout(self.on_air)
        pill.setContentsMargins(12, 6, 14, 6)
        pill.setSpacing(6)
        self.on_air_dot = QLabel("●")
        self.on_air_dot.setObjectName("onAirDot")
        self.on_air_label = QLabel()
        pill.addWidget(self.on_air_dot)
        pill.addWidget(self.on_air_label)
        lay.addWidget(self.on_air)

    def set_on_air(self, text: str, live: bool) -> None:
        if self.on_air_label.text() != text:
            self.on_air_label.setText(text)
        if self.on_air.property("live") != live:
            self.on_air.setProperty("live", live)
            repolish(self.on_air)


class LiveBar(QFrame):
    """'Radiant es: [equipo 1 | equipo 2]' y 'Modo: [Automático | Ocultar todo]'."""

    def __init__(self, on_side, on_mode):
        super().__init__()
        self.setObjectName("card")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(8)
        lay = QHBoxLayout()
        root.addLayout(lay)
        lay.setSpacing(10)
        lay.addWidget(field_label(tr("Radiant es")))
        t1, t2 = team_names(TeamsConfig())
        self.side_selector = Segmented([(t1, 1), (t2, 2)], on_side)
        for button in self.side_selector.buttons.values():
            button.setProperty("sideChoice", True)
        lay.addWidget(self.side_selector)
        lay.addSpacing(18)
        lay.addWidget(field_label(tr("Modo")))
        self.mode_selector = Segmented([(tr("Automático"), "auto"), (tr("Ocultar todo"), "hidden")],
                                       on_mode)
        lay.addWidget(self.mode_selector)
        lay.addSpacing(18)
        self.note = ElidedLabel()      # una línea: si no entra, "…" y el texto entero en el tooltip
        self.note.setObjectName("detail")
        lay.addWidget(self.note, 1)
        sides = QHBoxLayout()
        sides.setSpacing(10)
        self.radiant_label, self.dire_label = QLabel(), QLabel()
        for label, side in ((self.radiant_label, "radiant"), (self.dire_label, "dire")):
            label.setObjectName("sideBadge")
            label.setProperty("side", side)
            label.setTextFormat(Qt.TextFormat.PlainText)
            sides.addWidget(label)
        sides.addStretch(1)
        root.addLayout(sides)
        self._teams = TeamsConfig()
        self._radiant_team = 1
        self._refresh_assignment()

    def set_team_names(self, teams: TeamsConfig) -> None:
        self._teams = TeamsConfig(teams.team1, teams.team2)
        t1, t2 = team_names(teams)
        self.side_selector.set_label(1, t1)
        self.side_selector.set_label(2, t2)
        self._refresh_assignment()

    def _refresh_assignment(self) -> None:
        names = team_names(self._teams)
        radiant, dire = names[self._radiant_team - 1], names[2 - self._radiant_team]
        self.radiant_label.setText(f"Radiant: {radiant}")
        self.dire_label.setText(f"Dire: {dire}")

    def set_values(self, radiant_team: int, mode: str) -> None:
        self._radiant_team = radiant_team
        self.side_selector.set_value(radiant_team)
        self._refresh_assignment()
        self.mode_selector.set_value(mode)
        note = input_note(mode)
        self.note.set_full_text(note)
