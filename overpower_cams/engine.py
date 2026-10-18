"""Motor de selección: qué héroe está seleccionado en Dota -> qué cámara de OBS al aire.

Sin variables globales, sin prints y sin E/S: el destino de las cámaras es un `sink` con
`apply(cam, reason)` y las novedades salen por `on_event`.

Hilos: `process` (hilos HTTP de GSI) y `handle_input` (hilo de entrada local) comparten
un solo lock, igual que el `state_lock` del script (primero el estado, luego OBS).
Los callbacks (`sink.apply`, `on_event`, `on_learned`) se llaman con ese lock tomado,
así que NO deben volver a llamar al motor. `status()` no toma el lock: así la
interfaz nunca se congela esperando a un OBS lento.
"""
import threading
import time
from dataclasses import dataclass, field

from . import dota_keys
from .config import (CAMERAS_TEAM1, CAMERAS_TEAM2, HIDE_DELAY, LEARN_LOOKBACK,
                     LIVE_STATES, LOCAL_HOLD, PORTRAIT_PITCH, TOPBAR_MAX_Y)
from .i18n import tr
from .portraits import PortraitModel

HERO_PREFIX = "npc_dota_hero_"


# ---------- utilidades GSI (puras) ----------

def safe_dict(v):
    return v if isinstance(v, dict) else {}


def is_true(v):
    return v is True or str(v).lower() in ["true", "1", "yes"]


def iter_players(section):
    """Recorre una sección GSI ('player' o 'hero') y produce
    (team_key, player_key, datos_dict) por cada jugador válido."""
    for team_key, team_data in safe_dict(section).items():
        if not str(team_key).startswith("team"):
            continue
        for player_key, pd in safe_dict(team_data).items():
            if str(player_key).startswith("player"):
                yield team_key, player_key, safe_dict(pd)


def player_side(team_key, pd):
    """Bando GSI del jugador: 'r' (Radiant) o 'd' (Dire). team2=Radiant, team3=Dire."""
    if team_key == "team2":
        return "r"
    if team_key == "team3":
        return "d"
    tn = str(pd.get("team_name", "")).lower()   # respaldo por si cambian las claves
    if "radiant" in tn:
        return "r"
    if "dire" in tn:
        return "d"
    return None


def cameras_on_side(side, radiant_team):
    """Cámaras del equipo que está en ese bando AHORA (según radiant_team)."""
    if side == "r":
        return CAMERAS_TEAM1 if radiant_team == 1 else CAMERAS_TEAM2
    return CAMERAS_TEAM2 if radiant_team == 1 else CAMERAS_TEAM1


def build_roster(data, radiant_team):
    """-> (jugador 'team2.player0' -> cámara, slot 'r1' -> 'team2.player0', snapshot)."""
    new_map, slot_keys = {}, {}
    for team_key, player_key, pd in iter_players(data.get("player")):
        side = player_side(team_key, pd)
        if side is None:
            continue
        try:
            slot = int(pd.get("team_slot"))
        except (TypeError, ValueError):
            continue
        cams = cameras_on_side(side, radiant_team)
        if 0 <= slot < len(cams):
            new_map[f"{team_key}.{player_key}"] = cams[slot]
            slot_keys[f"{side}{slot + 1}"] = f"{team_key}.{player_key}"
    # el bando entra en el snapshot para que un swap regenere el roster
    snapshot = f"rt{radiant_team}|" + "|".join(f"{k}={v}" for k, v in sorted(new_map.items()))
    return new_map, slot_keys, snapshot


def get_selected_hero(data):
    """-> (clave del jugador, nombre del héroe) de la unidad seleccionada, o (None, None)."""
    for team_key, player_key, pd in iter_players(data.get("hero")):
        if not is_true(pd.get("selected_unit")):
            continue
        hero_name = pd.get("name", "")
        if str(hero_name).startswith(HERO_PREFIX):
            return f"{team_key}.{player_key}", hero_name
    return None, None


def _nombre_corto(hero):
    return hero[len(HERO_PREFIX):] if hero and hero.startswith(HERO_PREFIX) else hero


@dataclass
class EngineStatus:
    mode: str
    radiant_team: int
    camera: str | None
    hero: str | None
    game_state: str | None
    roster: dict[str, str] = field(default_factory=dict)


class Engine:
    def __init__(self, sink, portraits: PortraitModel, player_keys: dict[int, str], *,
                 radiant_team: int = 1, mode: str = "auto", clock=time.monotonic,
                 on_event=lambda text: None, on_learned=lambda: None):
        self._sink = sink
        self._portraits = portraits
        self._clock = clock
        self._on_event = on_event
        self._on_learned = on_learned
        self._lock = threading.Lock()

        self._player_keys = dict(player_keys)   # vk -> slot
        self._radiant_team = radiant_team
        self._mode = mode

        self._camera = None                  # cámara al aire (la que se aplicó al sink)
        self._resolved_map = {}              # 'team2.player0' -> cámara (se reasigna)
        self._slot_keys = {}                 # 'r1'..'d5' -> 'team2.player0' (se reasigna, no se muta)
        self._hero_names = {}                # 'team2.player0' -> nombre corto (se reasigna)
        self._snapshot = None
        self._current_key = None             # héroe al aire según el motor (incluye predicciones locales)
        self._no_hero_since = None
        self._game_state = None
        self._last_gsi_key = None            # la selección según GSI (sin predicciones locales)
        self._last_change_t = 0.0            # cuándo GSI reportó el último cambio de selección
        self._recent_inputs = []             # [(t, kind, value)] de los últimos LEARN_LOOKBACK s
        self._pending = None                 # último cambio local a confirmar con GSI

    # ---------- API pública ----------

    def process(self, data: dict) -> None:
        """Un POST de GSI."""
        if not isinstance(data, dict):
            return
        with self._lock:
            self._process(data)

    def handle_input(self, t: float, kind: str, value) -> None:
        """Entrada local: kind "key" (value = vk int) o "click" (value = (rx, ry))."""
        with self._lock:
            self._handle_input(t, kind, value)

    def set_radiant_team(self, n: int) -> None:
        with self._lock:
            self._radiant_team = n
            self._snapshot = None          # fuerza reconstruir el roster con el nuevo bando
            self._current_key = None       # fuerza re-aplicar la cámara en modo auto

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode
            self._current_key = None
            self._no_hero_since = None
            self._pending = None
            if mode == "hidden":
                self._apply(None, "hide", tr("oculto"))

    def set_player_keys(self, keys: dict[int, str]) -> None:
        with self._lock:
            self._player_keys = dict(keys)

    def status(self) -> EngineStatus:
        """Foto del estado actual. Sin lock a propósito (ver docstring del módulo): lee
        solo atributos simples y diccionarios que se reasignan enteros, nunca se mutan."""
        rt = self._radiant_team
        roster = {}
        for slot in self._slot_keys:
            roster[slot] = cameras_on_side(slot[0], rt)[int(slot[1:]) - 1]
        key = self._current_key
        return EngineStatus(
            mode=self._mode, radiant_team=rt, camera=self._camera,
            hero=self._hero_names.get(key, key) if key else None,
            game_state=self._game_state, roster=roster)

    # ---------- internos (con el lock tomado) ----------

    def _apply(self, cam, reason, event):
        """Llama al sink solo si la cámara cambia."""
        if cam == self._camera:
            return
        self._sink.apply(cam, reason)
        self._camera = cam
        self._on_event(event)

    def _process(self, data):
        new_map, slot_keys, snapshot = build_roster(data, self._radiant_team)
        if new_map and snapshot != self._snapshot:
            self._snapshot = snapshot
            self._resolved_map = new_map
            self._slot_keys = slot_keys

        names = {}
        for team_key, player_key, pd in iter_players(data.get("hero")):
            name = pd.get("name", "")
            if str(name).startswith(HERO_PREFIX):
                names[f"{team_key}.{player_key}"] = _nombre_corto(name)
        if names:
            self._hero_names = names

        # El estado de la partida se anota siempre (también oculto) para que la ventana no
        # muestre datos viejos.
        state = safe_dict(data.get("map")).get("game_state")
        self._game_state = state

        if self._mode == "hidden":
            return

        # Fin de partida o fuera del juego -> apagar YA (sin esperar HIDE_DELAY).
        if state not in LIVE_STATES:
            estado = state or tr("sin partida")
            self._apply(None, tr("fuera de juego ({state})", state=estado),
                        tr("fuera de juego ({state}) → oculto", state=estado))
            self._current_key = None
            self._no_hero_since = None
            return

        key, hero = get_selected_hero(data)

        # Un click/tecla local acaba de cambiar la cámara y este POST aún es la foto vieja.
        if not self._learn_from_gsi(key):
            return

        if not key:   # la unidad seleccionada no es un héroe
            now = self._clock()
            if self._no_hero_since is None:
                self._no_hero_since = now
            if now - self._no_hero_since >= HIDE_DELAY:
                self._apply(None, tr("sin héroe"), tr("sin héroe → oculto"))
                self._current_key = None
            return

        self._no_hero_since = None

        if key == self._current_key:
            return

        self._current_key = key
        camera = self._resolved_map.get(key)
        if camera:
            self._apply(camera, "GSI", f"{_nombre_corto(hero)} → {camera}")

    def _learn_portrait(self, slot):
        """GSI reportó que se seleccionó `slot`: si lo único que pasó desde el cambio
        anterior fueron clicks en un mismo punto de la barra superior, ese es su retrato."""
        window = [(k, v) for t, k, v in self._recent_inputs if t > self._last_change_t]
        if any(k == "key" and v in self._player_keys for k, v in window):
            return False                       # lo explica una tecla de jugador
        clicks = [v for k, v in window if k == "click"]
        if not clicks or any(ry > TOPBAR_MAX_Y for _, ry in clicks):
            return False                       # sin clicks, o hubo click en el mapa: ambiguo
        rx, ry = clicks[-1]
        if any(abs(x - rx) > PORTRAIT_PITCH / 2 for x, _ in clicks):
            return False                       # clicks en retratos distintos: ambiguo
        self._portraits.learn(slot, rx, ry)
        return True

    def _learn_from_gsi(self, key):
        """Con cada POST. Aprende retratos y confirma el último cambio local. Devuelve
        False si este POST hay que ignorarlo porque todavía no refleja ese cambio
        (GSI llega con ~1 s de retraso)."""
        now = self._clock()
        slot = next((s for s, k in self._slot_keys.items() if k == key), None) if key else None

        if slot and key != self._last_gsi_key:
            if self._learn_portrait(slot):
                self._on_learned()
            self._last_change_t = now
        self._last_gsi_key = key
        self._recent_inputs[:] = [i for i in self._recent_inputs if i[0] > now - LEARN_LOOKBACK]

        p = self._pending
        if not p:
            return True
        if slot == p["slot"]:
            self._pending = None               # GSI ya lo confirmó
            return True
        if key not in p["stale"]:
            self._pending = None               # selección NUEVA (otra tecla, click en el mapa...): GSI manda ya
            return True
        if now < p["deadline"]:
            return False                       # foto vieja: GSI todavía no se enteró
        self._pending = None                   # nunca se confirmó: GSI manda
        if p["kind"] == "click" and self._portraits.forget(p["slot"]):
            self._on_learned()
            self._on_event(tr("retrato {slot} mal aprendido: se vuelve a aprender", slot=p["slot"]))
        elif p["kind"] == "key":
            self._on_event(tr("la tecla {key} no seleccionó a {slot} en Dota",
                              key=dota_keys.key_name(p["value"]), slot=p["slot"]))
        return True

    def _local_select(self, slot, t, kind, value):
        """Cambia la cámara YA por una tecla/click, sin esperar el siguiente POST de GSI."""
        if self._mode == "hidden" or self._game_state not in LIVE_STATES:
            return
        target = self._slot_keys.get(slot)
        # Lo que GSI puede seguir mandando por su retraso: la selección de antes y las
        # de cambios locales anteriores aún sin confirmar (teclas rápidas seguidas).
        stale = (self._pending["stale"] if self._pending else set()) | \
            {self._last_gsi_key, self._current_key}
        stale.discard(target)
        self._pending = {"t": t, "kind": kind, "value": value, "slot": slot,
                         "deadline": self._clock() + LOCAL_HOLD, "stale": stale}
        self._current_key = target
        self._no_hero_since = None
        cam = cameras_on_side(slot[0], self._radiant_team)[int(slot[1:]) - 1]
        if kind == "click":
            self._apply(cam, f"click {slot}", tr("click retrato {slot} → {cam}", slot=slot, cam=cam))
        else:
            self._apply(cam, tr("tecla {slot}", slot=slot),
                        tr("tecla {key} → {cam}", key=dota_keys.key_name(value), cam=cam))

    def _handle_input(self, t, kind, value):
        self._recent_inputs.append((t, kind, value))
        if kind == "key":
            slot = self._player_keys.get(value)
        else:
            slot = self._portraits.portrait_at(*value)
        if slot:
            self._local_select(slot, t, kind, value)
        elif kind == "click":
            self._pending = None   # click en el mapa o en un retrato aún no aprendido: que decida GSI
            if value[1] <= TOPBAR_MAX_Y:
                self._on_event(tr("click en la barra superior (x={x}): esperando a GSI para "
                                  "aprenderlo", x=f"{value[0]:+.3f}"))
