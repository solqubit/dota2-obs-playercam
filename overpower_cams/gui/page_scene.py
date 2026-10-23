"""Página Escena OBS: la escena principal (si tiene las 10 escenas de jugador y el Borde), los
filtros H 4/5/6 con su posición y escala y un botón Probar, el estado de las 10 escenas con
«Crear las que faltan» y la imagen del Borde (Arreglar / Buscar…).

No lee OBS por su cuenta: muestra lo que dejaron las revisiones (`set_results`, con el
`SceneReport` que leyó `checks`) y reusa sus arreglos. Todo lo que habla con OBS va en otro hilo.

Usa de la ventana (`host`): `obs`, `_ctx_factory`, `_is_running`, `_run_bg`, `_events`,
`_closed`, `_fix_running`, `_confirm_fix`, `_show_instructions`, `_browse_companion`,
`run_checks` y `players_page`."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .. import checks, config
from ..checks import FixRefused
from ..i18n import tr
from ..obs_link import BORDE
from ..scene_builder import SceneBuildError
from .widgets import ElidedLabel, StatusIcon, card, detail_label, page_header

TEMPLATE = checks.TEMPLATE_SCENE
BODY_MAX_WIDTH = 980


def _num(v: float) -> str:
    return f"{v:g}"


def preset_text(preset: dict | None, main_scene: str) -> str:
    if preset is None:
        return tr("No está en «{scene}»", scene=main_scene)
    (x, y), (sx, sy) = preset["pos"], preset["scale"]
    return tr("Posición {x}, {y} · escala {sx} / {sy}", x=_num(x), y=_num(y), sx=_num(sx), sy=_num(sy))


class _Line(QWidget):
    """Icono de estado, texto en negrita, detalle y botones a la derecha."""

    def __init__(self, title: str, *buttons: QPushButton, elide_detail: bool = False):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(10)
        self.icon = StatusIcon("idle")
        lay.addWidget(self.icon)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight:bold;")
        lay.addWidget(self.title)
        if elide_detail:
            self.detail = ElidedLabel()
            self.detail.setObjectName("detail")
        else:
            self.detail = detail_label()
        lay.addWidget(self.detail, 1)
        for b in buttons:
            lay.addWidget(b)

    def set(self, status: str, detail: str) -> None:
        self.icon.set_status(status)
        if isinstance(self.detail, ElidedLabel):
            self.detail.set_full_text(detail)
        elif self.detail.text() != detail:
            self.detail.setText(detail)


class ScenePage(QWidget):
    def __init__(self, host):
        super().__init__()
        self._host = host
        self._results: dict = {}
        self._report = None            # SceneReport de la última revisión con OBS conectado
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(14)
        self.reload_button = QPushButton("↻ " + tr("Volver a leer"))
        self.reload_button.clicked.connect(lambda: host.run_checks())
        root.addWidget(page_header(tr("Escena OBS"),
                                   tr("Lo que la app usa de OBS. Nada se cambia sin preguntarte."),
                                   self.reload_button))
        body = QWidget()
        body.setMaximumWidth(BODY_MAX_WIDTH)
        cards = QVBoxLayout(body)
        cards.setContentsMargins(0, 0, 6, 0)
        cards.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ---- escena principal ----
        frame, lay = card(tr("Escena principal"))
        self.main_fix_button = self._button(tr("Arreglar"), self._fix_main)
        self.main_line = _Line("", self.main_fix_button)
        self.inside_line = _Line(tr("Escenas de jugador"))
        self.borde_line = _Line(BORDE)
        for w in (self.main_line, self.inside_line, self.borde_line):
            lay.addWidget(w)
        cards.addWidget(frame)

        # ---- filtros ----
        frame, lay = card(tr("Filtros de habilidades"))
        self.test_buttons: dict[int, QPushButton] = {}
        self.filter_lines: dict[int, _Line] = {}
        self.filter_details: dict[int, QLabel] = {}
        for n, name in config.HUD_FILTERS.items():
            b = self._button(tr("Probar"), lambda n=n: self._test(n))
            line = _Line(name, b)
            self.test_buttons[n] = b
            self.filter_lines[n] = line
            self.filter_details[n] = line.detail
            lay.addWidget(line)
        foot = QHBoxLayout()
        foot.addWidget(detail_label(tr("Probar activa el filtro sobre la escena al aire, o sobre "
                                       "«{template}» si no hay ninguna.", template=TEMPLATE)), 1)
        self.filters_help_button = self._button(tr("Ver instrucciones"), self._filters_help)
        foot.addWidget(self.filters_help_button)
        lay.addLayout(foot)
        cards.addWidget(frame)

        # ---- escenas de jugador ----
        frame, lay = card(tr("Escenas de jugador"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        self.scene_icons: dict[str, StatusIcon] = {}
        self.scene_details: dict[str, QLabel] = {}
        for col, scenes in enumerate((config.PLAYER_SCENES_TEAM1, config.PLAYER_SCENES_TEAM2)):
            for r, scene in enumerate(scenes):
                cell = QHBoxLayout()
                cell.setSpacing(8)
                icon = StatusIcon("idle")
                name = QLabel(scene)
                detail = ElidedLabel()
                detail.setObjectName("detail")
                cell.addWidget(icon)
                cell.addWidget(name)
                cell.addWidget(detail, 1)
                grid.addLayout(cell, r, col)
                self.scene_icons[scene] = icon
                self.scene_details[scene] = detail
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        row = QHBoxLayout()
        self.scenes_summary = detail_label()
        row.addWidget(self.scenes_summary, 1)
        self.create_button = self._button(
            tr("Crear las que faltan copiando «{template}»", template=TEMPLATE), self._create)
        self.create_button.setObjectName("primary")
        row.addWidget(self.create_button)
        lay.addLayout(row)
        cards.addWidget(frame)

        # ---- imagen del Borde ----
        frame, lay = card(tr("Imagen del Borde"))
        self.borde_fix_button = self._button(tr("Arreglar"), self._fix_images)
        self.borde_browse_button = self._button(tr("Buscar…"),
                                                lambda: host._browse_companion(BORDE))
        self.borde_image_line = _Line(BORDE, self.borde_fix_button, self.borde_browse_button,
                                      elide_detail=True)
        self.borde_path = self.borde_image_line.detail
        lay.addWidget(self.borde_image_line)
        lay.addWidget(detail_label(tr("El Borde se ve solo cuando hay una cámara al aire. Es fijo: "
                                      "no se mueve ni cambia de tamaño con la cámara.")))
        cards.addWidget(frame)
        cards.addStretch(1)
        self.set_results([], None)

    @staticmethod
    def _button(text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(lambda _=False: slot())
        return b

    # ------------------------------------------------------------------ datos
    def set_results(self, results, obs) -> None:
        """Muestra el resultado de las revisiones (y el SceneReport que leyeron)."""
        self._results = {r.id: r for r in results}
        connected = obs is not None and obs.connected
        report = obs.report if connected else None
        self._report = report if report is not None and report.main_found else None
        main = obs.main_scene if obs is not None else self._host.obs.main_scene
        rep = self._report
        self.main_line.title.setText(f"«{main}»")
        scene_r = self._results.get("scene")
        if scene_r is not None:
            self.main_line.set(scene_r.status if rep is None else "ok",
                               scene_r.detail if rep is None else tr("Existe en OBS"))
        else:
            self.main_line.set("idle", tr("Revisando…"))
        if rep is None:
            unknown = (tr("Sin revisar: OBS no está conectado") if not connected
                       else tr("Sin revisar: no existe la escena «{scene}»", scene=main))
            for line in (self.inside_line, self.borde_line):
                line.set("warn", unknown)
            for n, line in self.filter_lines.items():
                line.set("warn", unknown)
            for scene in config.PLAYER_SCENES:
                self.scene_icons[scene].set_status("idle")
                self.scene_details[scene].set_full_text("")
            self.scenes_summary.setText(unknown)
            self.borde_image_line.set("warn", unknown)
        else:
            inside = len(config.PLAYER_SCENES) - len(rep.missing_scenes)
            self.inside_line.set("ok" if not rep.missing_scenes else "warn",
                                 tr("{n} de 10 dentro de «{scene}»", n=inside, scene=main))
            self.borde_line.set("ok" if rep.borde else "warn",
                                tr("Está en «{scene}»", scene=main) if rep.borde
                                else tr("Falta en «{scene}»", scene=main))
            for n, line in self.filter_lines.items():
                preset = rep.filters.get(n)
                line.set("ok" if preset is not None else "error", preset_text(preset, main))
            for scene in config.PLAYER_SCENES:
                missing = rep.missing_sources.get(scene, [])
                if scene in rep.missing_scenes:
                    status, detail = "error", tr("falta")
                elif missing:
                    status, detail = "warn", tr("faltan: {names}", names=", ".join(missing))
                else:
                    status, detail = "ok", tr("lista")
                self.scene_icons[scene].set_status(status)
                self.scene_details[scene].set_full_text(detail)
            pr = self._results.get("player_scenes")
            self.scenes_summary.setText(pr.detail if pr is not None else "")
            if rep.borde:
                self.borde_image_line.set("idle", tr("Leyendo…"))
                self._read_borde(obs)
            else:
                self.borde_image_line.set("warn", tr("Falta {name} en «{scene}»", name=BORDE,
                                                     scene=main))
        self._refresh_buttons()

    def _read_borde(self, obs) -> None:
        def done(path, exc):
            if self._host._closed or obs is not self._host.obs:
                return
            if exc is not None or path is None:
                self.borde_image_line.set("warn", tr("No pude leer la imagen"))
            elif not path:
                self.borde_image_line.set("warn", tr("Sin imagen"))
            elif not Path(path).is_file():
                self.borde_image_line.set("warn", tr("No existe en esta PC: {path}", path=path))
            else:
                self.borde_image_line.set("ok", path)
        self._host._run_bg(lambda: obs.get_image_path(BORDE), done)

    def _refresh_buttons(self) -> None:
        obs = self._host.obs
        connected = obs.connected
        rep = self._report if connected else None
        for n, b in self.test_buttons.items():
            b.setEnabled(rep is not None and rep.filters.get(n) is not None)
        scene_r = self._results.get("scene")
        self.main_fix_button.setVisible(bool(scene_r and scene_r.fix_label))
        self.main_fix_button.setEnabled(connected)
        mf = self._results.get("move_filters")
        self.filters_help_button.setVisible(bool(mf and mf.status != "ok" and mf.instructions))
        self.create_button.setEnabled(rep is not None and bool(rep.missing_scenes)
                                      and not self._busy)
        images = self._results.get("scene_images")
        self.borde_fix_button.setVisible(bool(images and images.fix_label))
        self.borde_fix_button.setToolTip((images.instructions or "") if images else "")
        self.borde_fix_button.setEnabled(connected)
        self.borde_browse_button.setEnabled(rep is not None and rep.borde)

    def refresh_live(self, _st) -> None:
        """Cada segundo (página visible): los botones siguen a la conexión con OBS."""
        self._refresh_buttons()

    # ------------------------------------------------------------------ acciones
    def _fix_main(self) -> None:
        r = self._results.get("scene")
        if r is not None and r.fix_label:
            self._host._confirm_fix(r)

    def _fix_images(self) -> None:
        r = self._results.get("scene_images")
        if r is not None and r.fix_label:
            self._host._confirm_fix(r)

    def _filters_help(self) -> None:
        r = self._results.get("move_filters")
        if r is not None:
            self._host._show_instructions(r)

    def _test(self, n: int) -> None:
        host = self._host
        obs = host.obs
        name = config.HUD_FILTERS[n]

        def done(ok, exc):
            if host._closed:
                return
            if ok and exc is None:
                host._events.post(tr("Probando {name}", name=name))
            else:
                QMessageBox.warning(self, tr("No se pudo probar"),
                                    tr("No pude activar «{name}». ¿OBS está abierto y conectado?",
                                       name=name))
        host._run_bg(lambda: obs.test_filter(n), done)

    def _create(self) -> None:
        host = self._host
        rep = self._report
        if rep is None or not rep.missing_scenes or self._busy or host._fix_running:
            return
        main = host.obs.main_scene
        text = tr("Voy a crear en OBS estas escenas copiando «{template}» (con sus 4 fuentes, filtros "
                  "y posición) y agregarlas apagadas a «{scene}»:\n\n{names}\n\nNo toco las escenas "
                  "que ya existen. ¿Sigo?", template=TEMPLATE, scene=main,
                  names="\n".join(f"• {s}" for s in rep.missing_scenes))
        ok = QMessageBox.question(self, tr("Crear escenas"), text,
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
        if ok != QMessageBox.StandardButton.Yes:
            return
        ctx = host._ctx_factory(host.obs)
        is_running = host._is_running
        self._busy = True
        host._fix_running = True
        self._refresh_buttons()
        host._run_bg(lambda: checks.apply_fix("player_scenes", ctx, is_running=is_running),
                     self._create_done)

    def _create_done(self, msg, exc) -> None:
        host = self._host
        self._busy = False
        host._fix_running = False
        if host._closed:
            return
        cause = getattr(exc, "__cause__", None)
        if isinstance(cause, SceneBuildError):
            done = ", ".join(cause.created) if cause.created else "—"
            QMessageBox.warning(self, tr("No se pudieron crear las escenas"),
                                tr("OBS no me dejó terminar la escena «{scene}» ({error}). Ya creé: "
                                   "{done}.\n\n«{scene}» pudo quedar a medias: bórrala en OBS antes "
                                   "de volver a intentar.", scene=cause.target, error=cause.cause,
                                   done=done))
            if cause.created:
                host.players_page.push_all()
        elif isinstance(exc, FixRefused):
            QMessageBox.warning(self, tr("No se pudieron crear las escenas"), str(exc))
        elif exc is not None:
            QMessageBox.critical(self, tr("Error al arreglar"), f"{type(exc).__name__}: {exc}")
        else:
            host._events.post(msg)
            host.players_page.push_all()          # las escenas nuevas reciben nombres y links
            QMessageBox.information(self, tr("Listo"), msg)
        host.run_checks()
