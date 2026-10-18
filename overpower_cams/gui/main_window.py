"""Ventana principal (boceto B): barra de estado arriba, Revisión a la izquierda y En vivo
a la derecha.

Hilos: la ventana vive en el hilo de Qt y nunca espera a OBS ni al motor. Lo que puede
tardar (revisiones, arreglos, conectar/consultar OBS) corre en hilos aparte y vuelve por la
señal `_bg_done` (en cola). Las órdenes al motor (modo, bando, teclas) van por un único hilo
en orden, porque el motor llama a OBS con su lock tomado. Los eventos de otros hilos llegan
por `EventBus` (también en cola).
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QMainWindow,
                               QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .. import config, paths
from ..checks import CheckResult
from ..dota_keys import read_player_keys
from ..i18n import get_language, tr, tr_for
from ..storage import LiveState
from .checks_mixin import ChecksMixin
from .settings_dialog import SettingsDialog
from .widgets import CameraGrid, app_style, Segmented, detail_label, dot_html, panel

MAX_EVENTS = 50
AUTO_CHECK_MIN_S = 5.0   # al volver la ventana al frente, no revisar más seguido que esto


def input_note(mode: str) -> str:
    if mode == "auto":
        return tr("Para cambiar al instante, la app detecta las teclas y clicks mientras "
                  "Dota está activo.")
    return tr("Con «Ocultar todo» la app no escucha el teclado ni el mouse.")


def first_time_intro() -> str:
    return tr("Falta la contraseña de OBS. Ábrela en OBS (Herramientas → Ajustes del "
              "servidor WebSocket → Mostrar información de conexión), cópiala y pégala aquí.")


def _keys_signature(keys_file):
    if keys_file is None:
        return None
    try:
        return str(keys_file), Path(keys_file).stat().st_mtime_ns
    except OSError:
        return str(keys_file), None


def _hero_display(hero: str | None) -> str:
    return hero.replace("_", " ").title() if hero else ""


class MainWindow(ChecksMixin, QMainWindow):
    _bg_done = Signal(object, object, object)   # (callback, resultado, excepción)

    def __init__(self, ctx_factory, engine, obs, gsi, local_input, storage, *, events,
                 obs_factory, is_running=paths.is_running, clock=time.monotonic,
                 relaunch=paths.relaunch):
        """`ctx_factory(obs) -> checks.Context` arma el contexto de las revisiones con el OBS
        actual. `obs_factory(settings) -> ObsLink` crea un ObsLink nuevo y hace que el motor
        mande las cámaras a él. `events` es el EventBus por el que llegan los eventos."""
        super().__init__()
        self._ctx_factory = ctx_factory
        self.engine = engine
        self.obs = obs
        self.gsi = gsi
        self.local_input = local_input
        self.storage = storage
        self._events = events
        self._obs_factory = obs_factory
        self._is_running = is_running
        self._clock = clock
        self._relaunch = relaunch

        ctx = ctx_factory(obs)
        self._settings = ctx.settings          # el mismo objeto que usa ctx_factory
        self._portraits = ctx.portraits
        self._keys_sig = _keys_signature(ctx.keys_file)

        st = engine.status()
        self._radiant_team = st.radiant_team
        self._mode = st.mode

        self._engine_cmd = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ordenes-motor")
        self._threads: list[threading.Thread] = []
        self._obs_busy = False
        self._last_obs_try = float("-inf")
        self._was_connected = False
        self._checks_running = False
        self._checks_again = False
        self._last_auto_check = float("-inf")
        self._closed = False
        self._asked_password = False
        self._fix_running = False
        self.check_results: list[CheckResult] = []

        self.setWindowTitle(config.app_name())
        self.setStyleSheet(app_style(self.palette()))
        self.resize(1040, 660)
        self._build_ui()

        self._bg_done.connect(self._on_bg_done, Qt.ConnectionType.QueuedConnection)
        events.posted.connect(self._add_event, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        QTimer.singleShot(0, self.tick)

    # ------------------------------------------------------------------ interfaz
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        self.setCentralWidget(central)

        # Barra superior
        top = QWidget()
        top.setObjectName("topbar")
        top.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar = QHBoxLayout(top)
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(18)
        title = QLabel(tr("Estado"))
        title.setStyleSheet("font-weight:bold;")
        bar.addWidget(title)
        self.obs_label, self.dota_label, self.game_label = QLabel(), QLabel(), QLabel()
        for lbl in (self.obs_label, self.dota_label, self.game_label):
            lbl.setTextFormat(Qt.TextFormat.RichText)
            bar.addWidget(lbl)
        bar.addStretch(1)
        self.settings_button = QPushButton("⚙ " + tr("Ajustes"))
        self.settings_button.clicked.connect(lambda: self.open_settings())
        bar.addWidget(self.settings_button)
        root.addWidget(top)

        cols = QHBoxLayout()
        cols.setSpacing(12)
        root.addLayout(cols, 1)

        # Revisión (izquierda)
        checks_panel, checks_lay = panel(tr("Revisión"))
        self._rows_box = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_box)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.addWidget(detail_label(tr("Revisando…")))
        self._rows_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._rows_box)
        checks_lay.addWidget(scroll, 1)
        self.recheck_button = QPushButton("↻ " + tr("Revisar todo de nuevo"))
        self.recheck_button.clicked.connect(lambda: self.run_checks())
        rb = QHBoxLayout()
        rb.addStretch(1)
        rb.addWidget(self.recheck_button)
        checks_lay.addLayout(rb)
        cols.addWidget(checks_panel, 11)

        # En vivo (derecha)
        right = QVBoxLayout()
        live_panel, live = panel(tr("En vivo"))
        live.addWidget(QLabel(tr("Bando del Equipo 1")))
        self.side_selector = Segmented([("Radiant", 1), ("Dire", 2)], self._pick_side)
        self.radiant_button = self.side_selector.buttons[1]
        self.dire_button = self.side_selector.buttons[2]
        live.addWidget(self.side_selector)
        live.addWidget(detail_label(tr("Cámbialo si la moneda invirtió los lados. "
                                       "Se recuerda al reabrir.")))
        live.addSpacing(6)
        live.addWidget(QLabel(tr("Modo")))
        self.mode_selector = Segmented([(tr("Automático"), "auto"), (tr("Ocultar todo"), "hidden")],
                                       self._pick_mode)
        self.auto_button = self.mode_selector.buttons["auto"]
        self.hide_button = self.mode_selector.buttons["hidden"]
        live.addWidget(self.mode_selector)
        self.input_note = detail_label()
        live.addWidget(self.input_note)
        live.addSpacing(6)
        self.on_air_label = QLabel()
        self.on_air_label.setTextFormat(Qt.TextFormat.RichText)
        live.addWidget(self.on_air_label)
        self.team1_label, self.team2_label = QLabel(), QLabel()
        self.team1_label.setObjectName("teamLabel")
        self.team2_label.setObjectName("teamLabel")
        self.grid1 = CameraGrid(config.CAMERAS_TEAM1)
        self.grid2 = CameraGrid(config.CAMERAS_TEAM2)
        for w in (self.team1_label, self.grid1, self.team2_label, self.grid2):
            live.addWidget(w)
        right.addWidget(live_panel)

        log_panel, log = panel(tr("Últimos eventos"))
        self.event_list = QListWidget()
        self.event_list.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        log.addWidget(self.event_list)
        right.addWidget(log_panel, 1)
        cols.addLayout(right, 10)

        self.side_selector.set_value(self._radiant_team)
        self.mode_selector.set_value(self._mode)
        self._refresh_live(self.engine.status())
        self._refresh_bar(self._clock())

    # ------------------------------------------------------------------ hilos
    def _run_bg(self, fn, callback) -> None:
        """Corre `fn()` en un hilo aparte; `callback(resultado, excepción)` en el hilo de Qt."""
        def work():
            res, exc = None, None
            try:
                res = fn()
            except BaseException as e:  # noqa: BLE001 - se entrega al hilo de la interfaz
                exc = e
            try:
                self._bg_done.emit(callback, res, exc)
            except RuntimeError:
                pass   # la ventana ya no existe
        t = threading.Thread(target=work, daemon=True)
        self._threads = [x for x in self._threads if x.is_alive()] + [t]
        t.start()

    def _on_bg_done(self, callback, res, exc) -> None:
        if callback is not None:
            callback(res, exc)

    def _engine_do(self, fn, *args) -> None:
        """Orden al motor en el hilo de órdenes (en orden; el motor puede esperar a OBS)."""
        if self._closed:
            return
        fut = self._engine_cmd.submit(fn, *args)
        fut.add_done_callback(
            lambda f: f.exception() and self._events.post(
                "[ERROR] " + tr("motor: {error}", error=f.exception())))

    def wait_background(self, timeout: float = 5.0) -> None:
        """Espera a que terminen los hilos en curso y entrega sus resultados (para los tests)."""
        deadline = time.monotonic() + timeout
        while True:
            if not self._closed:
                self._engine_cmd.submit(lambda: None).result(max(0.0, deadline - time.monotonic()))
            for t in [t for t in self._threads if t.is_alive()]:
                t.join(max(0.0, deadline - time.monotonic()))
            QCoreApplication.processEvents()   # entrega resultados (pueden lanzar otros hilos)
            if not any(t.is_alive() for t in self._threads) or time.monotonic() >= deadline:
                return

    # ------------------------------------------------------------------ timer
    def tick(self) -> None:
        """Cada segundo: barra, En vivo, mantenimiento de OBS y recarga de teclas."""
        if self._closed:
            return
        now = self._clock()
        st = self.engine.status()
        self._refresh_bar(now)
        self._refresh_live(st)
        self._maybe_obs_maintenance(now)
        try:
            self._watch_keys(self._ctx_factory(self.obs).keys_file)
        except Exception as e:  # noqa: BLE001 - nunca romper el timer
            self._events.post("[ERROR] " + tr("teclas de Dota: {error}", error=e))
        if self.obs.connected != self._was_connected:
            self._was_connected = self.obs.connected
            self.run_checks()

    def _obs_state(self) -> tuple[str, str]:
        obs = self.obs
        if obs.connected:
            return "ok", tr("conectado")
        if obs.error == "auth":
            if not obs.password:
                return "error", tr("falta la contraseña (⚙ Ajustes)")
            return "error", tr("contraseña incorrecta")
        if obs.error is None:
            return "warn", tr("conectando…")
        return "error", tr("reconectando")

    def _refresh_bar(self, now: float) -> None:
        self.obs_label.setText(dot_html("OBS", *self._obs_state()))
        last = self.gsi.last_post_t
        fresh = last is not None and now - last <= config.GSI_STALE_S
        self.dota_label.setText(dot_html("Dota", *(("ok", tr("datos llegando")) if fresh
                                                   else ("warn", tr("sin datos")))))
        in_game = fresh and self.engine.status().game_state in config.LIVE_STATES
        self.game_label.setText(dot_html(tr("Partida"), *(("ok", tr("en juego")) if in_game
                                                          else ("warn", tr("fuera de partida")))))

    def _refresh_live(self, st) -> None:
        self.side_selector.set_value(self._radiant_team)
        self.mode_selector.set_value(self._mode)
        self.input_note.setText(input_note(self._mode))
        if st.camera:
            hero = _hero_display(st.hero)
            self.on_air_label.setText(tr("Al aire: <b>{camera}</b>", camera=st.camera)
                                      + (f" · {hero}" if hero else ""))
        elif self._mode == "hidden":
            self.on_air_label.setText(tr("Al aire: <b>nada</b> (Ocultar todo)"))
        else:
            self.on_air_label.setText(tr("Al aire: <b>ninguna cámara</b>"))
        rt = self._radiant_team
        self.team1_label.setText(tr("Equipo 1 ({side})", side="Radiant" if rt == 1 else "Dire"))
        self.team2_label.setText(tr("Equipo 2 ({side})", side="Dire" if rt == 1 else "Radiant"))
        self.grid1.set_live(st.camera)
        self.grid2.set_live(st.camera)

    def _maybe_obs_maintenance(self, now: float) -> None:
        """Cada OBS_RETRY_S, en otro hilo y de a uno: reconectar si no hay conexión, o
        preguntarle algo a OBS para notar si se cerró aunque no cambie la cámara."""
        if self._obs_busy or now - self._last_obs_try < config.OBS_RETRY_S:
            return
        self._last_obs_try = now
        self._obs_busy = True
        obs, engine = self.obs, self.engine

        def work():
            if obs.connected:
                obs.ping()
            else:
                obs.ensure_connected(engine.status().camera)
        self._run_bg(work, lambda _r, exc, obs=obs: self._obs_done(obs, exc))

    def _obs_done(self, obs, exc) -> None:
        self._obs_busy = False
        if exc is not None:
            self._events.post(f"[ERROR] OBS: {exc}")
        if obs is not self.obs:                    # se cambió en Ajustes mientras conectaba
            self._run_bg(obs.close, None)
            return
        if self._closed:
            return
        self._refresh_bar(self._clock())
        if obs.error == "auth" and not obs.password and not self._asked_password:
            self._asked_password = True            # una sola vez por sesión
            QTimer.singleShot(0, self.ask_password_first_time)

    def _watch_keys(self, keys_file) -> None:
        """Si la config de teclas de Dota cambió (o apareció), recargarla."""
        sig = _keys_signature(keys_file)
        if sig == self._keys_sig:
            return
        self._keys_sig = sig
        if sig is None or sig[1] is None:
            return                                 # desapareció: se quedan las teclas que había
        self._reload_keys(keys_file)

    def _reload_keys(self, keys_file) -> None:
        self._keys_sig = _keys_signature(keys_file)
        self._engine_do(self.engine.set_player_keys, read_player_keys(keys_file))
        self._events.post(tr("Teclas de Dota recargadas"))

    # ------------------------------------------------------------------ eventos
    def _add_event(self, stamp: str, text: str) -> None:
        self.event_list.insertItem(0, f"{stamp}  {text}")
        while self.event_list.count() > MAX_EVENTS:
            self.event_list.takeItem(self.event_list.count() - 1)

    def event_lines(self) -> list[str]:
        return [self.event_list.item(i).text() for i in range(self.event_list.count())]

    # ------------------------------------------------------------------ En vivo
    def _save_state(self) -> None:
        try:
            self.storage.save_state(LiveState(self._radiant_team, self._mode))
        except OSError as e:
            self._events.post("[ERROR] " + tr("no pude guardar el estado: {error}", error=e))

    def _pick_side(self, n: int) -> None:
        if n == self._radiant_team:
            return
        self._radiant_team = n
        self._engine_do(self.engine.set_radiant_team, n)
        self._save_state()
        self._events.post(tr("Bando del Equipo 1: {side}", side="Radiant" if n == 1 else "Dire"))
        self._refresh_live(self.engine.status())

    def _pick_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self._engine_do(self.engine.set_mode, mode)
        self._save_state()
        try:
            if mode == "auto":
                self.local_input.start()
            else:
                self.local_input.stop()
        except Exception as e:  # noqa: BLE001
            self._events.post("[ERROR] " + tr("teclado y mouse: {error}", error=e))
        self._events.post(tr("Modo: Automático") if mode == "auto"
                          else tr("Modo: Ocultar todo (sin escuchar teclado ni mouse)"))
        self._refresh_live(self.engine.status())

    # ------------------------------------------------------------------ ajustes
    def _save_settings(self) -> None:
        try:
            self.storage.save_settings(self._settings)
        except OSError as e:
            QMessageBox.warning(self, tr("No se pudo guardar"),
                                tr("No pude guardar los ajustes: {error}", error=e))

    def open_settings(self, intro: str | None = None) -> None:
        ctx = self._ctx_factory(self.obs)
        dlg = SettingsDialog(self._settings, self._portraits, detected_dota=ctx.dota,
                             intro=intro, parent=self)
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        if dlg.portraits_forgotten:
            try:
                self.storage.save_portraits(self._portraits.as_dict())
            except OSError as e:
                self._events.post("[ERROR] " + tr("no pude guardar los retratos: {error}", error=e))
            self._events.post(tr("Retratos olvidados: vuelven a la posición inicial"))
        if accepted:
            self.apply_settings(dlg.values())
        elif dlg.portraits_forgotten:
            self.run_checks()

    def ask_password_first_time(self) -> None:
        """OBS pide contraseña y no hay ninguna guardada: abrir Ajustes con una explicación."""
        if not self._closed and not self._settings.obs_password:
            self.open_settings(intro=first_time_intro())

    def apply_settings(self, new) -> None:
        """Guarda los ajustes nuevos; si cambió el puerto o la contraseña, crea otro ObsLink."""
        s = self._settings
        obs_changed = (new.obs_port, new.obs_password) != (s.obs_port, s.obs_password)
        s.obs_port, s.obs_password = new.obs_port, new.obs_password
        s.dota_dir, s.default_radiant_team = new.dota_dir, new.default_radiant_team
        language_changed = new.language is not None and new.language != get_language()
        s.language = new.language
        self._save_settings()
        if obs_changed:
            old = self.obs
            self.obs = self._obs_factory(s)
            self._was_connected = False
            self._last_obs_try = float("-inf")
            if not self._obs_busy:                 # si está ocupado, lo cierra `_obs_done`
                self._run_bg(old.close, None)
            self._events.post(tr("Ajustes de OBS cambiados: conectando a {host}:{port}",
                                 host=self.obs.host, port=self.obs.port))
            self.tick()
        self.run_checks()
        if language_changed and self.ask_restart(new.language):
            self.restart()

    def ask_restart(self, language: str) -> bool:
        """El idioma nuevo se aplica al reiniciar: preguntar (en el idioma NUEVO) si ahora."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(tr_for(language, "OverPower · Cámaras Dota"))
        box.setText(tr_for(language, "El idioma nuevo se aplica al reiniciar la app."))
        now = box.addButton(tr_for(language, "Reiniciar ahora"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr_for(language, "Más tarde"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(now)
        box.exec()
        return box.clickedButton() is now

    def restart(self) -> None:
        """Cierra esta ventana (libera el puerto GSI y guarda el estado), abre otra copia de
        la app y sale."""
        self.close()
        try:
            self._relaunch()
        except OSError as e:
            QMessageBox.warning(None, config.app_name(),
                                tr("No pude volver a abrir la app: {error}", error=e))
        app = QCoreApplication.instance()
        if app is not None:
            app.quit()

    # ------------------------------------------------------------------ ciclo de vida
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._auto_check()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._auto_check()

    def _auto_check(self) -> None:
        now = self._clock()
        if now - self._last_auto_check >= AUTO_CHECK_MIN_S:
            self._last_auto_check = now
            self.run_checks()

    def closeEvent(self, event) -> None:
        if not self._closed:
            self._closed = True
            self.timer.stop()
            try:
                self.local_input.stop()
            finally:
                self.gsi.stop()
                self._save_state()
                self._engine_cmd.shutdown(wait=False)
        super().closeEvent(event)
