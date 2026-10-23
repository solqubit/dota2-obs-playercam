"""Página Revisión de la ventana: correr las revisiones en otro hilo, dibujar una fila por
resultado y sus botones (arreglar con confirmación, instrucciones, Buscar…) y avisar cuántas
quedan pendientes (la insignia del menú).

Es un mixin de Shell: usa `_ctx_factory`, `obs`, `_settings`, `_events`, `_closed`,
`_is_running`, `_fix_running`, `_run_bg`, `_reload_keys`, `_save_settings`, `storage`,
`sidebar` y `_on_checks_rendered(results)`. `_build_checks_page()` arma la página y sus widgets
`_rows_lay` y `recheck_button`."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QMessageBox, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from .. import checks, config, paths
from ..checks import CheckResult, FixRefused
from ..i18n import tr
from .widgets import CheckRow, card, detail_label, not_dota_msg, page_layout


def image_filter() -> str:
    return (tr("Imágenes") + " (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;"
            + tr("Todos los archivos") + " (*)")


def pending_count(results) -> int:
    """Revisiones con aviso o error (el número de la insignia de Revisión)."""
    return sum(1 for r in results if r.status in ("warn", "error"))


class ChecksMixin:
    def _build_checks_page(self) -> QWidget:
        self.recheck_button = QPushButton("↻ " + tr("Revisar todo de nuevo"))
        self.recheck_button.clicked.connect(lambda: self.run_checks())
        page, lay = page_layout(tr("Revisión"),
                                tr("Lo que la app necesita para funcionar. Nada se cambia sin "
                                   "preguntarte."), self.recheck_button)
        frame, card_lay = card(margins=(16, 6, 12, 6))
        self._rows_box = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_box)
        self._rows_lay.setContentsMargins(0, 0, 4, 0)
        self._rows_lay.setSpacing(0)
        self._rows_lay.addWidget(detail_label(tr("Revisando…")))
        self._rows_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._rows_box)
        card_lay.addWidget(scroll, 1)
        lay.addWidget(frame, 1)
        return page

    def run_checks(self) -> None:
        if self._closed:
            return
        if self._checks_running:
            self._checks_again = True
            return
        self._checks_running = True
        self.recheck_button.setEnabled(False)
        self.recheck_button.setText(tr("Revisando…"))
        ctx = self._ctx_factory(self.obs)
        is_running = self._is_running
        self._run_bg(lambda: checks.run_checks(ctx, is_running=is_running), self._checks_done)

    def _checks_done(self, results, exc) -> None:
        self._checks_running = False
        self.recheck_button.setEnabled(True)
        self.recheck_button.setText("↻ " + tr("Revisar todo de nuevo"))
        if exc is not None:
            results = [CheckResult("app", "error", tr("Revisiones"),
                                   tr("Falló la revisión: {error}", error=exc))]
        self.check_results = results
        self._render_checks(results)
        if self._checks_again:
            self._checks_again = False
            self.run_checks()

    def _render_checks(self, results) -> None:
        while self._rows_lay.count():
            item = self._rows_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for r in results:
            self._rows_lay.addWidget(CheckRow(r, self._row_buttons(r)))
        self._rows_lay.addStretch(1)
        self._on_checks_rendered(results)

    def refresh_player_sources(self) -> None:
        """Recalcula solo «Fuentes de los jugadores» (en este hilo, sin OBS) y cambia su fila y la
        insignia. Lo usa la ventana al editar jugadores o equipos: correr todas las revisiones
        releería la colección de OBS con su lock tomado en plena partida."""
        if not any(r.id == "player_sources" for r in self.check_results):
            return                                 # todavía no hay revisión dibujada
        new = checks.player_sources_result(self.storage)
        self.check_results = [new if r.id == new.id else r for r in self.check_results]
        for i in range(self._rows_lay.count()):
            old = self._rows_lay.itemAt(i).widget()
            if isinstance(old, CheckRow) and old.result.id == new.id:
                self._rows_lay.insertWidget(i, CheckRow(new, self._row_buttons(new)))
                self._rows_lay.removeWidget(old)
                old.setParent(None)                # fuera de la página ya, no al borrarse
                old.deleteLater()
                break
        self.sidebar.set_pending(pending_count(self.check_results))

    def _button(self, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(lambda _=False: slot())
        return b

    def _row_buttons(self, r: CheckResult) -> list[QPushButton]:
        out = []
        if r.id == "dota" and r.fix_label:
            out.append(self._button(r.fix_label, self._browse_dota))
        elif r.fix_label:
            out.append(self._button(r.fix_label, lambda r=r: self._confirm_fix(r)))
        elif r.instructions:
            out.append(self._button(tr("Ver instrucciones"), lambda r=r: self._show_instructions(r)))
        if r.id == "scene_images":
            for name in config.COMPANIONS:
                out.append(self._button(tr("Buscar… {name}", name=name),
                                        lambda n=name: self._browse_companion(n)))
        return out

    def _show_instructions(self, r: CheckResult) -> None:
        QMessageBox.information(self, r.title, r.instructions or r.detail)

    def _confirm_fix(self, r: CheckResult) -> None:
        if self._fix_running:
            return                                 # un arreglo a la vez
        texto = (f"{r.title}: {r.detail}\n\n{r.instructions or ''}\n\n"
                 + tr("¿Quieres que haga este cambio ahora?"))
        ok = QMessageBox.question(self, tr("Confirmar cambio"), texto.replace("\n\n\n", "\n\n"),
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
        if ok != QMessageBox.StandardButton.Yes:
            return
        ctx = self._ctx_factory(self.obs)
        is_running = self._is_running
        self._fix_running = True
        self._run_bg(lambda: checks.apply_fix(r.id, ctx, is_running=is_running),
                     lambda msg, exc, ctx=ctx: self._fix_done(r, ctx, msg, exc))

    def _fix_done(self, r: CheckResult, ctx, msg, exc) -> None:
        self._fix_running = False
        if self._closed:
            return
        if isinstance(exc, FixRefused):
            QMessageBox.warning(self, tr("No se pudo arreglar"), str(exc))
        elif exc is not None:
            QMessageBox.critical(self, tr("Error al arreglar"), f"{type(exc).__name__}: {exc}")
        else:
            self._events.post(tr("Arreglado: {title}", title=r.title))
            if r.id == "keys":
                self._reload_keys(ctx.keys_file)
            QMessageBox.information(self, tr("Listo"), msg)
        self.run_checks()

    def _browse_dota(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Elige la carpeta de Dota 2 («dota 2 beta»)"),
                                             self._settings.dota_dir or "")
        if not d:
            return
        if not paths.is_dota_dir(d):
            QMessageBox.warning(self, tr("Carpeta equivocada"), not_dota_msg())
            return
        self._settings.dota_dir = str(Path(d))
        self._save_settings()
        self.run_checks()

    def _browse_companion(self, name: str) -> None:
        # empieza en la carpeta de imágenes de la app (_internal\assets en el .exe)
        inicio = str(paths.resource_path("assets"))
        path, _ = QFileDialog.getOpenFileName(self, tr("Imagen para «{name}»", name=name), inicio,
                                              image_filter())
        if not path:
            return
        path = str(Path(path))
        obs = self.obs
        self._run_bg(lambda: obs.set_image_path(name, path),
                     lambda ok, exc: self._companion_done(name, path, ok, exc))

    def _companion_done(self, name, path, ok, exc) -> None:
        if self._closed:
            return
        if ok and exc is None:
            self._events.post(tr("{name} ahora usa {path}", name=name, path=path))
            self.run_checks()
        else:
            QMessageBox.warning(self, tr("No se pudo cambiar la imagen"),
                                tr("No pude cambiar la imagen de «{name}». ¿OBS está abierto y "
                                   "conectado?", name=name))
