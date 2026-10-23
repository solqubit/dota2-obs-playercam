"""Crea las escenas de jugador que faltan copiando en vivo la plantilla (`1 Hard carry`) por obs-websocket.

Cada escena nueva lleva sus 4 fuentes (`Camara · X`, `Foto · X`, `Fondo · X`, `Nombre · X`) con los
settings, transform, visibilidad y filtros de las de la plantilla (URL vacía, nombre = la escena), y se
agrega apagada a la escena principal con la transform del ítem de la plantilla. Nunca modifica escenas
que ya existen. La GUI pide confirmación al usuario antes de llamar a `clone_player_scenes`.
"""
from obsws_python.error import OBSSDKRequestError

from .config import source_name
from .i18n import tr

KINDS = ("Camara", "Foto", "Fondo", "Nombre")
_RESOURCE_NOT_FOUND = 600
# OBS calcula estas claves: SetSceneItemTransform las rechaza
_READONLY = ("sourceWidth", "sourceHeight", "width", "height")


class SceneBuildError(Exception):
    """Falló la creación de `target`. `created` = escenas ya completas antes del fallo (la escena que
    falló puede haber quedado a medias en OBS: el usuario decide si la borra; nada existente se toca)."""

    def __init__(self, target: str, created: list[str], cause: BaseException):
        self.target = target
        self.created = list(created)
        self.cause = cause
        super().__init__(tr("No se pudo crear la escena '{scene}': {error}", scene=target, error=cause))


def clean_transform(transform: dict) -> dict:
    """Transform de GetSceneItemTransform lista para SetSceneItemTransform: sin claves de solo lectura
    y sin tamaño de bounds cuando no aplica (tipo NONE o tamaño < 1, que OBS rechaza)."""
    out = {k: v for k, v in transform.items() if k not in _READONLY}
    sizes = [out.get("boundsWidth"), out.get("boundsHeight")]
    if (out.get("boundsType") == "OBS_BOUNDS_NONE"
            or any(v is not None and v < 1 for v in sizes)):
        out.pop("boundsWidth", None)
        out.pop("boundsHeight", None)
    return out


def _items(client, scene: str) -> dict[str, dict]:
    return {it["sourceName"]: it for it in client.get_scene_item_list(scene).scene_items}


def _scene_exists(client, scene: str) -> bool:
    try:
        client.get_scene_item_list(scene)
        return True
    except OBSSDKRequestError as e:
        if e.code != _RESOURCE_NOT_FOUND:
            raise
        return False


def _clone_one(client, main_scene: str, template: str, target: str, main_items: dict, tpl_items: dict):
    client.create_scene(target)
    for kind in KINDS:
        src = source_name(kind, template)
        item = tpl_items[src]
        info = client.get_input_settings(src)
        settings = dict(info.input_settings)
        if kind in ("Camara", "Foto"):
            settings["url"] = ""
        elif kind == "Nombre":
            settings["text"] = target
        new = source_name(kind, target)
        res = client.create_input(target, new, info.input_kind, settings,
                                  item.get("sceneItemEnabled", True))
        tf = client.get_scene_item_transform(template, item["sceneItemId"]).scene_item_transform
        client.set_scene_item_transform(target, res.scene_item_id, clean_transform(tf))
        for f in client.get_source_filter_list(src).filters:
            client.create_source_filter(new, f["filterName"], f["filterKind"], f["filterSettings"])
            if not f.get("filterEnabled", True):
                client.set_source_filter_enabled(new, f["filterName"], False)
    res = client.create_scene_item(main_scene, target, False)
    tpl_main = main_items.get(template)
    if tpl_main is not None:
        tf = client.get_scene_item_transform(main_scene, tpl_main["sceneItemId"]).scene_item_transform
        client.set_scene_item_transform(main_scene, res.scene_item_id, clean_transform(tf))


def clone_player_scenes(client, main_scene: str, template: str = "1 Hard carry",
                        targets: list[str] | None = None) -> list[str]:
    """Crea en OBS cada escena de `targets` que no exista, copiando `template`. Devuelve las creadas.

    Los destinos que ya existen (o son la plantilla) se saltan sin tocarlos. Ante el primer fallo se
    detiene todo y lanza `SceneBuildError` (con `target` y `created`); no se deshace nada."""
    created: list[str] = []
    try:
        tpl_items = _items(client, template)
        main_items = _items(client, main_scene)
        missing = [source_name(k, template) for k in KINDS if source_name(k, template) not in tpl_items]
        if missing:
            raise OBSSDKRequestError("GetSceneItemList", _RESOURCE_NOT_FOUND, f"faltan {missing}")
    except OBSSDKRequestError as e:
        raise SceneBuildError(template, created, e) from e
    for target in targets or []:
        if target == template:
            continue
        try:
            if _scene_exists(client, target):
                continue
            _clone_one(client, main_scene, template, target, main_items, tpl_items)
        except OBSSDKRequestError as e:
            raise SceneBuildError(target, created, e) from e
        created.append(target)
    return created
