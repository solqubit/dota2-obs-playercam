"""Utilidades compartidas por los tests (sin tocar Steam/Dota/OBS reales)."""
import os
import sys

# Permite `import overpower_cams` al correr pytest desde la raíz del proyecto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from overpower_cams import i18n  # noqa: E402


@pytest.fixture(autouse=True)
def idioma_espanol():
    """Los tests comparan textos en español: cada test arranca en "es" (y se restaura al final),
    sin importar el idioma de Windows de la PC que los corre."""
    antes = i18n.get_language()
    i18n.set_language("es")
    yield
    i18n.set_language(antes)


class FakeClock:
    """Reloj controlable: `.t` es el tiempo actual, `clock()` lo devuelve."""

    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class FakeSink:
    """Destino falso de escenas: registra cada `apply` y cada `retrigger`."""

    def __init__(self):
        self.calls: list[tuple[str | None, str, int]] = []
        self.retriggers: list[tuple[str, int]] = []

    def apply(self, scene, reason, abilities=4):
        self.calls.append((scene, reason, abilities))

    def retrigger(self, scene, abilities):
        self.retriggers.append((scene, abilities))


def gsi_payload(sel, state="DOTA_GAMERULES_STATE_GAME_IN_PROGRESS", abilities=None, radiant_team=1):
    """Payload GSI de 10 jugadores. `sel` = "r3" / "d1" / None (sin héroe seleccionado).

    `abilities` (opcional) = dict escena -> cantidad; arma la sección `abilities` (solo de
    los jugadores nombrados). Las escenas del equipo 1 van en Radiant si `radiant_team == 1`.

    Radiant = team2, player0..4; Dire = team3, player5..9; team_slot 0..4.
    Como en el GSI real, `selected_unit` y `name` van en la sección `hero`
    (el script la lee de ahí); `player` lleva `team_slot` y también
    `selected_unit` por comodidad de quien lo busque en esa sección.
    """
    player = {"team2": {}, "team3": {}}
    hero = {"team2": {}, "team3": {}}
    for i in range(10):
        team_key = "team2" if i < 5 else "team3"
        prefix = "r" if i < 5 else "d"
        slot = i % 5
        selected = sel == f"{prefix}{slot + 1}"
        player[team_key][f"player{i}"] = {"team_slot": slot, "selected_unit": selected}
        hero[team_key][f"player{i}"] = {
            "name": f"npc_dota_hero_test{i}",
            "selected_unit": selected,
        }
    payload = {"map": {"game_state": state}, "player": player, "hero": hero}
    if abilities is not None:
        from overpower_cams.config import PLAYER_SCENES_TEAM1, PLAYER_SCENES_TEAM2
        radiant, dire = ((PLAYER_SCENES_TEAM1, PLAYER_SCENES_TEAM2) if radiant_team == 1
                         else (PLAYER_SCENES_TEAM2, PLAYER_SCENES_TEAM1))
        section = {"team2": {}, "team3": {}}
        for i in range(10):
            scene = (radiant if i < 5 else dire)[i % 5]
            if scene in abilities:
                section["team2" if i < 5 else "team3"][f"player{i}"] = {
                    f"ability{n}": {"name": f"test_ability_{n}", "level": 1}
                    for n in range(abilities[scene])}
        payload["abilities"] = section
    return payload


# ---------------------------------------------------------------------------
# OBS falso (obsws-python ReqClient)
# ---------------------------------------------------------------------------
from types import SimpleNamespace  # noqa: E402

from obsws_python.error import OBSSDKRequestError  # noqa: E402

_CAMS = [f"CAM_EQ1_{i}" for i in range(1, 6)] + [f"CAM_EQ2_{i}" for i in range(1, 6)]


def layout_nuevo(companions=("Borde", "Marco")):
    """Escena nueva: cada CAM_* es un grupo con su fuente VDO_* adentro."""
    layout = {cam: [f"VDO_{cam[4:]}"] for cam in _CAMS}
    for c in companions:
        layout[c] = None
    return layout


def layout_viejo(companions=("Borde",)):
    """Escena vieja: cámaras sueltas dentro de los grupos "Equipo 1" / "Equipo 2"."""
    layout = {"Equipo 1": _CAMS[:5], "Equipo 2": _CAMS[5:]}
    for c in companions:
        layout[c] = None
    return layout


class FakeObsClient:
    """Cliente OBS falso, con la misma API que `obsws_python.ReqClient` (la parte que usa la app).

    - `layout`: nombre de nivel superior -> None (fuente) o lista de nombres hijos (grupo).
    - `calls`: cada `set_scene_item_enabled` como (contenedor, id, enabled);
      `named_calls`: lo mismo con el nombre de la fuente (se resuelve al momento de la llamada).
    - `inputs`: ajustes por nombre de entrada.
    - `fail_next=True`: la siguiente llamada lanza ConnectionError (una sola vez).
    - `restart()`: renumera los IDs y las llamadas siguientes lanzan ConnectionError
      hasta que `factory()` (el "client_factory" de ObsLink) entregue un cliente nuevo.
    - `factory(**kw)`: cuenta conexiones en `connections`; lanza `connect_error` si está puesto.
    """

    def __init__(self, layout=None, scene="Escena Dota", scene_exists=True, inputs=None):
        self.scene = scene
        self.scene_exists = scene_exists
        self.layout = dict(layout if layout is not None else layout_nuevo())
        self.inputs = {k: dict(v) for k, v in (inputs or {}).items()}
        self.fail_next = False
        self.dead = False
        self.connect_error = None
        self.connections = 0
        self.connect_kwargs = []
        self.calls = []
        self.named_calls = []
        self.created = []
        self._generation = 0
        self._assign_ids()

    # --- armado de la escena -------------------------------------------------
    def _assign_ids(self):
        self._containers = {self.scene: []}
        self._names = {}          # (contenedor, id) -> nombre
        self.enabled = {}         # (contenedor, id) -> bool
        n = self._generation * 100
        for name, children in self.layout.items():
            n += 1
            is_group = children is not None
            self._containers[self.scene].append(
                {"sourceName": name, "sceneItemId": n, "isGroup": is_group})
            self._names[(self.scene, n)] = name
            if is_group:
                subs = []
                for child in children:
                    n += 1
                    subs.append({"sourceName": child, "sceneItemId": n, "isGroup": False})
                    self._names[(name, n)] = child
                self._containers[name] = subs
        self._next_id = n + 1

    def restart(self):
        """OBS se reinicia: IDs nuevos y los clientes viejos dejan de funcionar."""
        self._generation += 1
        self._assign_ids()
        self.dead = True

    def factory(self, **kwargs):
        self.connections += 1
        self.connect_kwargs.append(kwargs)
        if self.connect_error is not None:
            raise self.connect_error
        self.dead = False
        return self

    # --- ayudas para los tests ----------------------------------------------
    def id_of(self, name):
        for (container, item_id), n in self._names.items():
            if n == name:
                return item_id
        raise KeyError(name)

    def container_of(self, name):
        for (container, item_id), n in self._names.items():
            if n == name:
                return container
        raise KeyError(name)

    def is_enabled(self, name):
        return self.enabled.get((self.container_of(name), self.id_of(name)))

    # --- API de ReqClient ----------------------------------------------------
    def _check(self):
        if self.fail_next:
            self.fail_next = False
            raise ConnectionError("fallo simulado")
        if self.dead:
            raise ConnectionError("OBS se reinició")

    def get_version(self):
        self._check()
        return SimpleNamespace(obs_version="32.0.0", obs_web_socket_version="5.6.0")

    def get_scene_item_list(self, name):
        self._check()
        if name != self.scene or not self.scene_exists:
            raise OBSSDKRequestError("GetSceneItemList", 600, "No scene was found")
        return SimpleNamespace(scene_items=[dict(i) for i in self._containers[name]])

    def get_group_scene_item_list(self, name):
        self._check()
        if name not in self._containers or name == self.scene:
            raise OBSSDKRequestError("GetGroupSceneItemList", 600, "No group was found")
        return SimpleNamespace(scene_items=[dict(i) for i in self._containers[name]])

    def set_scene_item_enabled(self, scene_name, item_id, enabled):
        self._check()
        key = (scene_name, item_id)
        if key not in self._names:
            raise OBSSDKRequestError("SetSceneItemEnabled", 600, "No scene items were found")
        self.calls.append((scene_name, item_id, enabled))
        self.named_calls.append((self._names[key], enabled))
        self.enabled[key] = enabled

    def get_input_settings(self, name):
        self._check()
        if name not in self.inputs:
            raise OBSSDKRequestError("GetInputSettings", 600, "No input was found")
        return SimpleNamespace(input_settings=dict(self.inputs[name]))

    def set_input_settings(self, name, settings, overlay):
        self._check()
        if name not in self.inputs:
            raise OBSSDKRequestError("SetInputSettings", 600, "No input was found")
        if overlay:
            self.inputs[name].update(settings)
        else:
            self.inputs[name] = dict(settings)

    def create_input(self, sceneName, inputName, inputKind, inputSettings, sceneItemEnabled):
        self._check()
        item_id = self._next_id
        self._next_id += 1
        self._containers[sceneName].append(
            {"sourceName": inputName, "sceneItemId": item_id, "isGroup": False})
        self._names[(sceneName, item_id)] = inputName
        self.enabled[(sceneName, item_id)] = sceneItemEnabled
        self.inputs[inputName] = dict(inputSettings)
        self.created.append((sceneName, inputName, inputKind, dict(inputSettings), sceneItemEnabled))
        return SimpleNamespace(scene_item_id=item_id)

    def disconnect(self):
        pass
