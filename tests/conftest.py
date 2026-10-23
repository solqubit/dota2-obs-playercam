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


def layout_camaraman(skip_scenes=(), skip_sources=(), borde=True):
    """Colección Camaraman: {escena: layout}. `Juego` lleva las 10 escenas de jugador como ítems
    (más la captura y el Borde) y cada escena de jugador sus 4 fuentes."""
    from overpower_cams.config import PLAYER_SCENES, source_name
    main = {"Captura de juego": None}
    main.update({s: None for s in PLAYER_SCENES if s not in skip_scenes})
    if borde:
        main["Borde"] = None
    scenes = {"Juego": main}
    for s in PLAYER_SCENES:
        scenes[s] = {source_name(k, s): None for k in ("Camara", "Foto", "Fondo", "Nombre")
                     if source_name(k, s) not in skip_sources}
    return scenes


def filtros_camaraman(omitir=()):
    """Filtros Move Source de `Juego` con los valores reales (claves de Move Transition)."""
    def ajustes(px, py, sx, sy):
        return {"pos": {"x": px, "x_sign": " ", "y": py, "y_sign": " "},
                "scale": {"x": sx, "x_sign": " ", "y": sy, "y_sign": " "},
                "source": "1 Hard carry"}
    reales = {"H 4 habilidades": ajustes(431.0, 1778.0, 0.199, 0.2),
              "H 5 habilidades": ajustes(456.0, 1819.0, 0.18, 0.18),
              "H 6 habilidades": ajustes(466.0, 1860.0, 0.157, 0.156)}
    return {"Juego": {n: {"enabled": False, "kind": "move_source_filter", "settings": v}
                      for n, v in reales.items() if n not in omitir}}


# Claves de GetSceneItemTransform que SetSceneItemTransform rechaza (OBS las calcula)
READONLY_TRANSFORM_KEYS = frozenset({"sourceWidth", "sourceHeight", "width", "height"})


class FakeObsClient:
    """Cliente OBS falso, con la misma API que `obsws_python.ReqClient` (la parte que usa la app).

    - `layout`: layout de la escena `scene` (la de v1): nombre de nivel superior -> None (fuente) o
      lista de nombres hijos (grupo). `scenes` agrega otras escenas {escena: layout}; las escenas
      anidadas son ítems normales de la escena que las contiene.
    - `filters`: {fuente: {filtro: {"enabled", "kind", "settings"}}}.
    - `calls`: cada `set_scene_item_enabled` como (contenedor, id, enabled);
      `named_calls`: lo mismo con el nombre de la fuente; `ops`: TODA escritura en orden
      (("enable", contenedor, nombre, bool), ("transform", ...), ("filter_settings", ...),
      ("filter_enabled", ...)).
    - `inputs`: ajustes por nombre de entrada.
    - `fail_next=True`: la siguiente llamada lanza ConnectionError (una sola vez).
    - `restart()`: renumera los IDs y las llamadas siguientes lanzan ConnectionError
      hasta que `factory()` (el "client_factory" de ObsLink) entregue un cliente nuevo.
    - `factory(**kw)`: cuenta conexiones en `connections`; lanza `connect_error` si está puesto.
    """

    def __init__(self, layout=None, scene="Escena Dota", scene_exists=True, inputs=None,
                 scenes=None, filters=None):
        self.scene = scene
        self.scenes = {} if scenes is None else {k: dict(v) for k, v in scenes.items()}
        if layout is not None or not self.scenes:
            self.scenes[scene] = dict(layout if layout is not None else layout_nuevo())
        self.removed = set() if scene_exists else {scene}
        self.inputs = {k: dict(v) for k, v in (inputs or {}).items()}
        self.filters = {k: {n: {**f, "settings": dict(f["settings"])} for n, f in v.items()}
                        for k, v in (filters or {}).items()}
        self.fail_next = False
        self.dead = False
        self.connect_error = None
        self.connections = 0
        self.connect_kwargs = []
        self.calls = []
        self.named_calls = []
        self.ops = []
        self.created = []
        self.input_kinds = {}     # entrada -> tipo (por defecto "browser_source")
        self.transforms = {}      # (contenedor, id) -> último transform pedido
        self._generation = 0
        self._assign_ids()

    @property
    def scene_exists(self):
        return self.scene not in self.removed

    @scene_exists.setter
    def scene_exists(self, value):
        (self.removed.discard if value else self.removed.add)(self.scene)

    # --- armado de la escena -------------------------------------------------
    def _assign_ids(self):
        self._containers = {}
        self._names = {}          # (contenedor, id) -> nombre
        self.enabled = {}         # (contenedor, id) -> bool
        n = self._generation * 1000
        for scene, layout in self.scenes.items():
            self._containers[scene] = []
            for name, children in layout.items():
                n += 1
                is_group = children is not None
                self._containers[scene].append(
                    {"sourceName": name, "sceneItemId": n, "isGroup": is_group})
                self._names[(scene, n)] = name
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
    def id_of(self, name, container=None):
        for (cont, item_id), n in self._names.items():
            if n == name and container in (None, cont):
                return item_id
        raise KeyError(name)

    def container_of(self, name):
        for (container, item_id), n in self._names.items():
            if n == name:
                return container
        raise KeyError(name)

    def is_enabled(self, name, container=None):
        container = container or self.container_of(name)
        return self.enabled.get((container, self.id_of(name, container)))

    def filter_settings(self, filtro, fuente="Juego"):
        return self.filters[fuente][filtro]["settings"]

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
        if name not in self.scenes or name in self.removed:
            raise OBSSDKRequestError("GetSceneItemList", 600, "No scene was found")
        return SimpleNamespace(scene_items=[
            {**i, "sceneItemEnabled": self.enabled.get((name, i["sceneItemId"]), True)}
            for i in self._containers[name]])

    def get_group_scene_item_list(self, name):
        self._check()
        if name not in self._containers or name in self.scenes:
            raise OBSSDKRequestError("GetGroupSceneItemList", 600, "No group was found")
        return SimpleNamespace(scene_items=[dict(i) for i in self._containers[name]])

    def set_scene_item_enabled(self, scene_name, item_id, enabled):
        self._check()
        key = (scene_name, item_id)
        if key not in self._names:
            raise OBSSDKRequestError("SetSceneItemEnabled", 600, "No scene items were found")
        self.calls.append((scene_name, item_id, enabled))
        self.named_calls.append((self._names[key], enabled))
        self.ops.append(("enable", scene_name, self._names[key], enabled))
        self.enabled[key] = enabled

    def set_scene_item_transform(self, scene_name, item_id, transform):
        self._check()
        key = (scene_name, item_id)
        if key not in self._names:
            raise OBSSDKRequestError("SetSceneItemTransform", 600, "No scene items were found")
        if READONLY_TRANSFORM_KEYS & set(transform):
            raise OBSSDKRequestError("SetSceneItemTransform", 400, "read-only transform key")
        for k in ("boundsWidth", "boundsHeight"):
            if k in transform and transform[k] < 1:
                raise OBSSDKRequestError("SetSceneItemTransform", 400, f"{k} must be >= 1")
        self.transforms[key] = {**self.transforms.get(key, {}), **transform}
        self.ops.append(("transform", scene_name, self._names[key], dict(transform)))

    def get_scene_item_transform(self, scene_name, item_id):
        self._check()
        key = (scene_name, item_id)
        if key not in self._names:
            raise OBSSDKRequestError("GetSceneItemTransform", 600, "No scene items were found")
        base = {"positionX": 0.0, "positionY": 0.0, "scaleX": 1.0, "scaleY": 1.0, "rotation": 0.0,
                "boundsType": "OBS_BOUNDS_NONE", "boundsWidth": 1.0, "boundsHeight": 1.0,
                "sourceWidth": 1920.0, "sourceHeight": 1080.0, "width": 1920.0, "height": 1080.0}
        return SimpleNamespace(scene_item_transform={**base, **self.transforms.get(key, {})})

    def _source_exists(self, name):
        """Escena, entrada o fuente de alguna escena: en OBS los nombres son únicos en la colección."""
        return (name in self.scenes or name in self.inputs
                or any(n == name for n in self._names.values()))

    def get_source_filter_list(self, name):
        self._check()
        if not self._source_exists(name) or name in self.removed:
            raise OBSSDKRequestError("GetSourceFilterList", 600, "No source was found")
        return SimpleNamespace(filters=[
            {"filterName": n, "filterKind": f["kind"], "filterEnabled": f["enabled"],
             "filterIndex": i, "filterSettings": dict(f["settings"])}
            for i, (n, f) in enumerate(self.filters.get(name, {}).items())])

    def create_source_filter(self, sourceName, filterName, filterKind, filterSettings=None):
        self._check()
        if not self._source_exists(sourceName):
            raise OBSSDKRequestError("CreateSourceFilter", 600, "No source was found")
        if filterName in self.filters.get(sourceName, {}):
            raise OBSSDKRequestError("CreateSourceFilter", 601, "A filter already exists")
        self.filters.setdefault(sourceName, {})[filterName] = {
            "enabled": True, "kind": filterKind, "settings": dict(filterSettings or {})}
        self.ops.append(("filter_create", sourceName, filterName))

    def get_source_filter(self, source_name, filter_name):
        self._check()
        f = self.filters.get(source_name, {}).get(filter_name)
        if f is None:
            raise OBSSDKRequestError("GetSourceFilter", 600, "No filter was found")
        return SimpleNamespace(filter_enabled=f["enabled"], filter_kind=f["kind"],
                               filter_settings=dict(f["settings"]))

    def set_source_filter_settings(self, source_name, filter_name, settings, overlay=None):
        self._check()
        f = self.filters.get(source_name, {}).get(filter_name)
        if f is None:
            raise OBSSDKRequestError("SetSourceFilterSettings", 600, "No filter was found")
        if overlay:
            f["settings"].update(settings)
        else:
            f["settings"] = dict(settings)
        self.ops.append(("filter_settings", filter_name, dict(settings)))

    def set_source_filter_enabled(self, source_name, filter_name, enabled):
        self._check()
        f = self.filters.get(source_name, {}).get(filter_name)
        if f is None:
            raise OBSSDKRequestError("SetSourceFilterEnabled", 600, "No filter was found")
        f["enabled"] = enabled
        self.ops.append(("filter_enabled", filter_name, enabled))

    def get_input_settings(self, name):
        self._check()
        if name not in self.inputs:
            raise OBSSDKRequestError("GetInputSettings", 600, "No input was found")
        return SimpleNamespace(input_settings=dict(self.inputs[name]),
                               input_kind=self.input_kinds.get(name, "browser_source"))

    def set_input_settings(self, name, settings, overlay):
        self._check()
        if name not in self.inputs:
            raise OBSSDKRequestError("SetInputSettings", 600, "No input was found")
        if overlay:
            self.inputs[name].update(settings)
        else:
            self.inputs[name] = dict(settings)

    def create_scene(self, name):
        self._check()
        if self._source_exists(name):
            raise OBSSDKRequestError("CreateScene", 601, "A source already exists by that scene name")
        self.scenes[name] = {}
        self._containers[name] = []
        self.ops.append(("scene_create", name))

    def _add_item(self, scene, name, enabled):
        item_id = self._next_id
        self._next_id += 1
        self._containers[scene].append({"sourceName": name, "sceneItemId": item_id, "isGroup": False})
        self.scenes[scene][name] = None
        self._names[(scene, item_id)] = name
        self.enabled[(scene, item_id)] = enabled
        return item_id

    def create_scene_item(self, sceneName, sourceName, sceneItemEnabled=True):
        self._check()
        if sceneName not in self.scenes or not self._source_exists(sourceName):
            raise OBSSDKRequestError("CreateSceneItem", 600, "No scene/source was found")
        item_id = self._add_item(sceneName, sourceName, sceneItemEnabled)
        self.ops.append(("item_create", sceneName, sourceName, sceneItemEnabled))
        return SimpleNamespace(scene_item_id=item_id)

    def create_input(self, sceneName, inputName, inputKind, inputSettings, sceneItemEnabled):
        self._check()
        if sceneName not in self.scenes:
            raise OBSSDKRequestError("CreateInput", 600, "No scene was found")
        if self._source_exists(inputName):
            raise OBSSDKRequestError("CreateInput", 601, "A source already exists by that input name")
        item_id = self._add_item(sceneName, inputName, sceneItemEnabled)
        self.inputs[inputName] = dict(inputSettings)
        self.input_kinds[inputName] = inputKind
        self.created.append((sceneName, inputName, inputKind, dict(inputSettings), sceneItemEnabled))
        return SimpleNamespace(scene_item_id=item_id)

    def disconnect(self):
        pass


def fake_camaraman(inputs=None, omitir_filtros=(), **kw):
    """FakeObsClient con la colección Camaraman (escena principal `Juego`) y sus 3 filtros."""
    return FakeObsClient(scenes=layout_camaraman(**kw), scene="Juego", inputs=inputs,
                         filters=filtros_camaraman(omitir_filtros))
