"""Página Jugadores (boceto D v2): por equipo, el nombre del equipo (con su bando actual) y una
tabla con las 5 escenas de jugador: rol, nombre, link de cámara, link de foto, Cámara/Foto y
habilidades actuales. La fila al aire se resalta en verde.

Cada edición se guarda al momento (`players.json`) y se manda a OBS en otro hilo: los textos al
perder el foco o con Enter, el selector Cámara/Foto al hacer click. Los envíos a OBS van de a uno
y en orden (una cola sobre `run_bg`). Si OBS no está conectado se guarda igual, se avisa en
Eventos y `push_all()` (la ventana lo llama al conectar) lo manda después."""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                               QVBoxLayout, QWidget)

from .. import config
from ..i18n import tr
from ..players import PlayerConfig, TeamsConfig
from .widgets import Segmented, card, page_header, repolish, status_colors

FIELDS = ("name", "camera", "photo")          # lo que se manda a OBS por escena
URL_ATTR = {"camera": "camera_url", "photo": "photo_url"}
URL_HINT = "https://vdo.ninja/?view=…"
ROW_HEIGHT = 42
TEAM_EDIT_WIDTH = 220


def _attr(field: str) -> str:
    return URL_ATTR.get(field, field)


class PlayerRow(QFrame):
    """Fondo de una fila de la tabla (resaltable) y sus campos. Los campos van en la grilla del
    equipo, encima de este fondo, para que las columnas queden alineadas."""

    def __init__(self, scene: str):
        super().__init__()
        self.setObjectName("tableRow")
        self.setProperty("onair", False)
        self.scene = scene
        self.role_label = QLabel(scene)
        self.role_label.setTextFormat(Qt.TextFormat.RichText)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("Nombre del jugador"))
        self.camera_edit = QLineEdit()
        self.camera_edit.setPlaceholderText(URL_HINT)
        self.photo_edit = QLineEdit()
        self.photo_edit.setPlaceholderText(URL_HINT)
        self.use_selector: Segmented | None = None    # lo pone la página (necesita el callback)
        self.abilities_label = QLabel("—")
        self.abilities_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def edit(self, field: str) -> QLineEdit:
        return {"name": self.name_edit, "camera": self.camera_edit, "photo": self.photo_edit}[field]

    def set_on_air(self, on_air: bool, dot_color: str) -> None:
        role = (f'{self.scene} <span style="color:{dot_color}">●</span>' if on_air else self.scene)
        if self.role_label.text() != role:
            self.role_label.setText(role)
        if self.property("onair") != on_air:
            self.setProperty("onair", on_air)
            repolish(self)


class PlayersPage(QWidget):
    def __init__(self, storage, *, get_obs, run_bg, post_event, radiant_team, on_teams_changed):
        """`get_obs()` da el ObsLink actual, `run_bg(fn, callback)` corre `fn` en otro hilo,
        `radiant_team()` dice qué equipo es Radiant y `on_teams_changed()` avisa a la ventana
        que cambió el nombre de un equipo (barra en vivo y Ajustes)."""
        super().__init__()
        self._storage = storage
        self._get_obs = get_obs
        self._run_bg = run_bg
        self._post = post_event
        self._radiant_team = radiant_team
        self._on_teams_changed = on_teams_changed
        self._players: dict[str, PlayerConfig] = storage.load_players()
        self._teams: TeamsConfig = storage.load_teams()
        self._unsynced: set[tuple[str, str]] = set()   # (escena, campo) que no llegó a OBS
        self._jobs: deque = deque()
        self._job_running = False
        self.rows: dict[str, PlayerRow] = {}
        self.team_edits: dict[int, QLineEdit] = {}
        self.side_hints: dict[int, QLabel] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(14)
        lay.addWidget(page_header(tr("Jugadores"),
                                  tr("Los cambios se guardan y se aplican en OBS al momento.")))

        frame, card_lay = card(margins=(16, 12, 16, 14))
        card_lay.setSpacing(6)
        for team, scenes in ((1, config.PLAYER_SCENES_TEAM1), (2, config.PLAYER_SCENES_TEAM2)):
            if team == 2:
                card_lay.addSpacing(14)
            card_lay.addWidget(self._team_head(team))
            card_lay.addWidget(self._table(scenes))
        card_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(frame)
        lay.addWidget(scroll, 1)
        self.set_data(self._teams, self._players)
        self._refresh_sides()

    # ------------------------------------------------------------------ armado
    def _team_head(self, team: int) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(10)
        title = QLabel((tr("Equipo 1") if team == 1 else tr("Equipo 2")).upper())
        title.setObjectName("cardTitle")
        lay.addWidget(title)
        edit = QLineEdit()
        edit.setFixedWidth(TEAM_EDIT_WIDTH)
        edit.setPlaceholderText(tr("Nombre del equipo"))
        edit.editingFinished.connect(lambda t=team: self._team_edited(t))
        lay.addWidget(edit)
        hint = QLabel()
        hint.setObjectName("teamHint")
        lay.addWidget(hint)
        lay.addStretch(1)
        self.team_edits[team] = edit
        self.side_hints[team] = hint
        return w

    def _table(self, scenes: list[str]) -> QWidget:
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(0)
        last = 7                                   # columnas 0 y 7: margen dentro del fondo
        grid.setColumnMinimumWidth(0, 0)
        grid.setColumnMinimumWidth(last, 0)
        for col, stretch in ((2, 2), (3, 3), (4, 3)):
            grid.setColumnStretch(col, stretch)
        heads = [tr("Rol"), tr("Nombre"), tr("URL de cámara"), tr("URL de foto"),
                 tr("Usar"), tr("Habilidades")]
        head_bg = QFrame()
        head_bg.setObjectName("tableRow")
        grid.addWidget(head_bg, 0, 0, 1, last + 1)
        for i, text in enumerate(heads, start=1):
            lbl = QLabel(text)
            lbl.setObjectName("colHeader")
            grid.addWidget(lbl, 0, i, Qt.AlignmentFlag.AlignVCenter)
        grid.setRowMinimumHeight(0, 30)
        role_width = max(QLabel(s + " ●").sizeHint().width() for s in config.PLAYER_SCENES) + 6
        grid.setColumnMinimumWidth(1, role_width)
        for r, scene in enumerate(scenes, start=1):
            row = PlayerRow(scene)
            row.use_selector = Segmented([(tr("Cámara"), "camera"), (tr("Foto"), "photo")],
                                         lambda use, s=scene: self._use_picked(s, use))
            grid.addWidget(row, r, 0, 1, last + 1)     # fondo primero: los campos quedan encima
            cells = (row.role_label, row.name_edit, row.camera_edit, row.photo_edit,
                     row.use_selector, row.abilities_label)
            for c, w in enumerate(cells, start=1):
                grid.addWidget(w, r, c, Qt.AlignmentFlag.AlignVCenter)
            row.lower()
            grid.setRowMinimumHeight(r, ROW_HEIGHT)
            for field in FIELDS:
                row.edit(field).editingFinished.connect(
                    lambda s=scene, f=field: self._field_edited(s, f))
            self.rows[scene] = row
        return box

    # ------------------------------------------------------------------ datos
    def set_data(self, teams: TeamsConfig, players: dict[str, PlayerConfig]) -> None:
        """Muestra los datos guardados (al abrir o si `players.json` cambió). No pisa el campo
        que el usuario está editando."""
        self._teams = TeamsConfig(teams.team1, teams.team2)
        self._players = {s: PlayerConfig(**vars(p)) for s, p in players.items()}
        for team, value in ((1, self._teams.team1), (2, self._teams.team2)):
            self._set_text(self.team_edits[team], value)
        for scene, row in self.rows.items():
            p = self._players.get(scene, PlayerConfig())
            for field in FIELDS:
                self._set_text(row.edit(field), getattr(p, _attr(field)))
            row.use_selector.set_value(p.use if p.use in ("camera", "photo") else "camera")

    @staticmethod
    def _set_text(edit: QLineEdit, value: str) -> None:
        if not edit.hasFocus() and edit.text() != value:
            edit.setText(value)
            edit.setCursorPosition(0)

    def _save_players(self) -> bool:
        try:
            self._storage.save_players(self._players)
            return True
        except OSError as e:
            self._post("[ERROR] " + tr("no pude guardar los jugadores: {error}", error=e))
            return False

    def _team_edited(self, team: int) -> None:
        text = self.team_edits[team].text().strip()
        attr = f"team{team}"
        if text == getattr(self._teams, attr):
            return
        setattr(self._teams, attr, text)
        try:
            self._storage.save_teams(self._teams)
        except OSError as e:
            self._post("[ERROR] " + tr("no pude guardar los jugadores: {error}", error=e))
            return
        self._on_teams_changed()

    def _field_edited(self, scene: str, field: str) -> None:
        text = self.rows[scene].edit(field).text().strip()
        p = self._players.setdefault(scene, PlayerConfig())
        if text == getattr(p, _attr(field)):
            return
        setattr(p, _attr(field), text)
        if self._save_players():
            self._push(scene, field, text, warn=True)

    def _use_picked(self, scene: str, use: str) -> None:
        p = self._players.setdefault(scene, PlayerConfig())
        if use == p.use:
            return
        p.use = use
        if self._save_players():
            obs = self._get_obs()
            self._enqueue(lambda: obs.refresh_player_mode(scene), None)   # solo si está al aire

    # ------------------------------------------------------------------ OBS
    def _push(self, scene: str, field: str, value: str, *, warn: bool) -> None:
        obs = self._get_obs()

        def work():
            if field == "name":
                ok = obs.set_player_name(scene, value)
            else:
                ok = obs.set_player_url(scene, field, value)
                if ok:
                    obs.refresh_player_mode(scene)   # p. ej. apareció el link de la foto elegida
            return ok, obs.connected

        def done(res, exc):
            ok, connected = res if exc is None else (False, obs.connected)
            if ok:
                self._unsynced.discard((scene, field))
                return
            self._unsynced.add((scene, field))
            if not warn:
                return
            if not connected:
                self._post(tr("OBS no está conectado: el cambio de {scene} se guardó y se aplica "
                              "al reconectar", scene=scene))
            else:
                self._post(tr("No pude aplicar en OBS el cambio de {scene}: ¿existe la escena con "
                              "sus fuentes?", scene=scene))
        self._enqueue(work, done)

    def push_all(self) -> None:
        """Manda a OBS los nombres y links de las 10 escenas (al conectar o reconectar, o tras
        crear escenas). Los campos vacíos solo se mandan si se editaron sin llegar a OBS, para no
        borrar lo que OBS ya tiene en una instalación nueva."""
        for scene in config.PLAYER_SCENES:
            p = self._players.get(scene, PlayerConfig())
            for field in FIELDS:
                value = getattr(p, _attr(field))
                if value or (scene, field) in self._unsynced:
                    self._push(scene, field, value, warn=False)

    def _enqueue(self, fn, callback) -> None:
        self._jobs.append((fn, callback))
        self._next_job()

    def _next_job(self) -> None:
        if self._job_running or not self._jobs:
            return
        fn, callback = self._jobs.popleft()
        self._job_running = True

        def done(res, exc):
            self._job_running = False
            if exc is not None:
                self._post("[ERROR] OBS: " + str(exc))
            if callback is not None:
                callback(res, exc)
            self._next_job()
        self._run_bg(fn, done)

    # ------------------------------------------------------------------ en vivo
    def refresh_live(self, st) -> None:
        """Cada segundo (página visible): habilidades, fila al aire y bando de cada equipo."""
        green = status_colors(self.palette())["ok"]
        for scene, row in self.rows.items():
            n = st.abilities.get(scene)
            text = str(n) if n else "—"
            if row.abilities_label.text() != text:
                row.abilities_label.setText(text)
            row.set_on_air(st.camera == scene, green)
        self._refresh_sides()

    def _refresh_sides(self) -> None:
        radiant = self._radiant_team()
        for team, hint in self.side_hints.items():
            text = "→ Radiant" if team == radiant else "→ Dire"
            if hint.text() != text:
                hint.setText(text)
            side = "radiant" if team == radiant else "dire"
            if hint.property("side") != side:
                hint.setProperty("side", side)
                repolish(hint)
