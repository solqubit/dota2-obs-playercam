"""Sección Revisión de la ventana principal: correr las revisiones en otro hilo, dibujar
una fila por resultado y sus botones (arreglar con confirmación, instrucciones, Buscar…).

Es un mixin de MainWindow: usa `_ctx_factory`, `obs`, `_settings`, `_events`, `_closed`,
`_is_running`, `_fix_running`, `_run_bg`, `_reload_keys`, `_save_settings` y los widgets `_rows_lay` y
`recheck_button` que arma la ventana."""
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton

from .. import checks, config, paths
from ..checks import CheckResult, FixRefused
from ..i18n import tr
from .widgets import CheckRow, not_dota_msg


def image_filter() -> str:
    return (tr("Imágenes") + " (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;"
            + tr("Todos los archivos") + " (*)")


class ChecksMixin:
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
        if r.id == "companion_images":
            for name in config.COMPANIONS_V1:
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
