"""Ventana principal (boceto D v2): menú lateral a la izquierda, barra de estados y barra en
vivo arriba, y las páginas Jugadores / Revisión / Escena OBS / Eventos / Ajustes.

Hilos: la ventana vive en el hilo de Qt y nunca espera a OBS ni al motor. Lo que puede
tardar (revisiones, arreglos, conectar/consultar OBS) corre en hilos aparte y vuelve por la
señal `_bg_done` (en cola). Las órdenes al motor (modo, bando, teclas) van por un único hilo
en orden, porque el motor llama a OBS con su lock tomado. Los eventos de otros hilos llegan
por `EventBus` (también en cola).

Páginas: `set_page(key, widget)` cambia una página (Task 11 pone ahí Jugadores y Escena
OBS). Si la página visible tiene `refresh_live(status)`, se llama cada segundo.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QMainWindow, QMessageBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import config, paths
from ..checks import CheckResult
from ..dota_keys import read_player_keys
from ..i18n import get_language, tr, tr_for
from ..players import TeamsConfig
from ..storage import LiveState, Settings
from .checks_mixin import ChecksMixin, pending_count
from .page_settings import SettingsPage
from .sidebar import PAGE_KEYS, Sidebar, nav_title
from .status_bar import LiveBar, StatusBar, ago_text, clock_text, on_air_text, team_names
from .widgets import app_style, dot_html, page_layout, status_colors

MAX_EVENTS = 50
AUTO_CHECK_MIN_S = 5.0   # al volver la ventana al frente, no revisar más seguido que esto


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


def _file_signature(path: Path):
    try:
        st = path.stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


class Shell(ChecksMixin, QMainWindow):
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
        self._names_sig = object()
        self.teams = TeamsConfig()
        self.players = {}

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
        self.resize(1240, 780)
        self.setMinimumSize(980, 620)
        self._build_ui(ctx)

        self._bg_done.connect(self._on_bg_done, Qt.ConnectionType.QueuedConnection)
        events.posted.connect(self._add_event, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        QTimer.singleShot(0, self.tick)

    # ------------------------------------------------------------------ interfaz
    def _build_ui(self, ctx) -> None:
        central = QWidget()
        central.setObjectName("central")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)
        self.sidebar = Sidebar(self.show_page)
        self.nav_buttons = self.sidebar.buttons
        self.checks_badge = self.sidebar.badge
        root.addWidget(self.sidebar)

        main = QVBoxLayout()
        main.setContentsMargins(8, 18, 20, 18)
        main.setSpacing(12)
        root.addLayout(main, 1)

        self.status_bar_widget = StatusBar()
        self.obs_label, self.obs_detail = self.status_bar_widget.obs.title, self.status_bar_widget.obs.detail
        self.dota_label, self.dota_detail = self.status_bar_widget.dota.title, self.status_bar_widget.dota.detail
        self.game_label, self.game_detail = self.status_bar_widget.game.title, self.status_bar_widget.game.detail
        self.on_air_label = self.status_bar_widget.on_air_label
        main.addWidget(self.status_bar_widget)

        self.live_bar = LiveBar(self._pick_side, self._pick_mode)
        self.side_selector = self.live_bar.side_selector
        self.mode_selector = self.live_bar.mode_selector
        self.auto_button = self.mode_selector.buttons["auto"]
        self.hide_button = self.mode_selector.buttons["hidden"]
        main.addWidget(self.live_bar)

        self.stack = QStackedWidget()
        main.addSpacing(6)
        main.addWidget(self.stack, 1)
        self.pages: dict[str, QWidget] = {}

        self.event_list = QListWidget()
        self.event_list.setObjectName("eventList")
        events_page, lay = page_layout(tr("Eventos"),
                                       tr("Lo que pasó en esta sesión, lo más nuevo arriba."))
        lay.addWidget(self.event_list, 1)

        self.settings_page = SettingsPage(self._settings, self._portraits, detected_dota=ctx.dota,
                                          on_save=self.apply_settings,
                                          on_forget_portraits=self._portraits_forgotten)
        built = {"players": self._placeholder("players"),   # Task 11 la cambia con set_page
                 "checks": self._build_checks_page(),
                 "scene": self._placeholder("scene"),       # Task 11 la cambia con set_page
                 "events": events_page,
                 "settings": self.settings_page}
        for key in PAGE_KEYS:
            self.stack.addWidget(built[key])
            self.pages[key] = built[key]
        self.show_page("players")

        self.refresh_names(force=True)
        self._refresh_live(self.engine.status())
        self._refresh_bar(self._clock())

    # ------------------------------------------------------------------ páginas
    @staticmethod
    def _placeholder(key: str) -> QWidget:
        page, lay = page_layout(nav_title(key))
        lay.addStretch(1)
        return page

    def set_page(self, key: str, widget: QWidget) -> None:
        """Cambia la página `key` (misma posición en el menú)."""
        old = self.pages[key]
        idx = self.stack.indexOf(old)
        was_current = self.stack.currentWidget() is old
        self.stack.insertWidget(idx, widget)
        self.stack.removeWidget(old)
        old.deleteLater()
        self.pages[key] = widget
        if was_current:
            self.stack.setCurrentWidget(widget)

    def show_page(self, key: str) -> None:
        if key == "settings":
            if self.settings_page.is_dirty():
                self.settings_page.refresh_dota()   # la carpeta pudo cambiar desde Revisión
            else:
                self._reload_settings_page()
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_buttons[key].setChecked(True)

    def current_page(self) -> str:
        w = self.stack.currentWidget()
        return next(k for k, page in self.pages.items() if page is w)

    def _on_checks_rendered(self, results) -> None:
        self.sidebar.set_pending(pending_count(results))

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
        """Cada segundo: estados, barra en vivo, mantenimiento de OBS y recarga de teclas."""
        if self._closed:
            return
        now = self._clock()
        self.refresh_names()
        st = self.engine.status()
        self._refresh_bar(now, st)
        self._refresh_live(st)
        self._maybe_obs_maintenance(now)
        try:
            self._watch_keys(self._ctx_factory(self.obs).keys_file)
        except Exception as e:  # noqa: BLE001 - nunca romper el timer
            self._events.post("[ERROR] " + tr("teclas de Dota: {error}", error=e))
        if self.obs.connected != self._was_connected:
            self._was_connected = self.obs.connected
            self.run_checks()

    def refresh_names(self, force: bool = False) -> None:
        """Relee nombres de equipos y jugadores si cambió `players.json` (o si `force`)."""
        sig = _file_signature(self.storage.base / "players.json")
        if not force and sig == self._names_sig:
            return
        self._names_sig = sig
        self.teams = self.storage.load_teams()
        self.players = self.storage.load_players()
        self.live_bar.set_team_names(self.teams)
        self.settings_page.set_team_names(self.teams)

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

    def _refresh_bar(self, now: float, st=None) -> None:
        st = st or self.engine.status()
        bar = self.status_bar_widget
        colors = status_colors(self.palette())
        bar.obs.set(dot_html("OBS", *self._obs_state(), colors), f"{self.obs.host}:{self.obs.port}")
        last = self.gsi.last_post_t
        fresh = last is not None and now - last <= config.GSI_STALE_S
        bar.dota.set(dot_html("Dota", *(("ok", tr("datos llegando")) if fresh
                                        else ("warn", tr("sin datos"))), colors),
                     ago_text(now - last) if last is not None else tr("nunca"))
        in_game = fresh and st.game_state in config.LIVE_STATES
        bar.game.set(dot_html(tr("Partida"), *(("ok", tr("en juego")) if in_game
                                               else ("warn", tr("fuera de partida"))), colors),
                     clock_text(st.clock_time if in_game else None))   # reloj solo en juego

    def _refresh_live(self, st) -> None:
        self.live_bar.set_values(self._radiant_team, self._mode)
        self.status_bar_widget.set_on_air(on_air_text(st, self.players), bool(st.camera))
        page = self.stack.currentWidget()
        refresh = getattr(page, "refresh_live", None)
        if callable(refresh):
            refresh(st)

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

    # ------------------------------------------------------------------ en vivo
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
        self._events.post(tr("Radiant es: {team}", team=team_names(self.teams)[n - 1]))
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

    def _reload_settings_page(self) -> None:
        self.settings_page.load(self._settings, self._ctx_factory(self.obs).dota)

    def open_settings(self, intro: str | None = None) -> None:
        """Va a Ajustes mostrando los valores guardados (y una explicación, si hay)."""
        self._reload_settings_page()
        self.settings_page.set_intro(intro)
        self.show_page("settings")
        if intro:
            self.settings_page.password_edit.setFocus()

    def ask_password_first_time(self) -> None:
        """OBS pide contraseña y no hay ninguna guardada: abrir Ajustes con una explicación."""
        if not self._closed and not self._settings.obs_password:
            self.open_settings(intro=first_time_intro())

    def _portraits_forgotten(self) -> None:
        try:
            self.storage.save_portraits(self._portraits.as_dict())
        except OSError as e:
            self._events.post("[ERROR] " + tr("no pude guardar los retratos: {error}", error=e))
        self._events.post(tr("Retratos olvidados: vuelven a la posición inicial"))
        self.run_checks()

    def apply_settings(self, new: Settings) -> None:
        """Guarda los ajustes nuevos; si cambió algo de OBS (dirección, puerto, contraseña o
        escena principal), crea otro ObsLink."""
        s = self._settings
        obs_changed = ((new.obs_host, new.obs_port, new.obs_password, new.main_scene)
                       != (s.obs_host, s.obs_port, s.obs_password, s.main_scene))
        language_changed = new.language is not None and new.language != get_language()
        for f in fields(Settings):
            setattr(s, f.name, getattr(new, f.name))
        self._save_settings()
        self.settings_page.set_intro(None)
        self._reload_settings_page()
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
