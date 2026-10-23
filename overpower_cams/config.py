"""Constantes de la app (nombres de la escena de OBS, tiempos y geometría de la
barra superior de Dota), compartidas por la app de escritorio y la consola."""
from .i18n import tr

APP_NAME = "OverPower · Cámaras Dota"   # nombre en español; en la interfaz usar app_name()
APP_DIR_NAME = "OverPowerCamarasDota"   # carpeta en %APPDATA%


def app_name() -> str:
    """Nombre de la app en el idioma de la interfaz (título de la ventana y de los avisos)."""
    return tr("OverPower · Cámaras Dota")


SCENE_NAME = "Escena Dota"   # Nombre de la escena principal en OBS

# Cámaras de cada EQUIPO, en orden de slot (team_slot 0..4). Son fuentes o grupos,
# buscados en cualquier lugar de SCENE_NAME.
CAMERAS_TEAM1 = ["CAM_EQ1_1", "CAM_EQ1_2", "CAM_EQ1_3", "CAM_EQ1_4", "CAM_EQ1_5"]
CAMERAS_TEAM2 = ["CAM_EQ2_1", "CAM_EQ2_2", "CAM_EQ2_3", "CAM_EQ2_4", "CAM_EQ2_5"]

# Acompañantes: visibles ÚNICAMENTE mientras hay una cámara al aire. Opcionales.
COMPANIONS = ["Borde", "Marco"]

# Estados de partida (map.game_state) en los que SÍ se muestran cámaras.
LIVE_STATES = {
    "DOTA_GAMERULES_STATE_PRE_GAME",
    "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
}

# Segundos sin héroe seleccionado antes de apagar la cámara (0 = en el primer POST).
HIDE_DELAY = 0.0

# Tras un cambio local se ignora lo que diga GSI hasta que lo confirme, o hasta
# LOCAL_HOLD segundos.
LOCAL_HOLD = 3.0
# Ventana (s) hacia atrás para asociar un click con lo que GSI confirma después.
LEARN_LOOKBACK = 2.5

# Geometría de la barra superior, en fracciones del ALTO de la ventana de Dota.
TOPBAR_MAX_Y = 0.08           # clicks más abajo son en el mapa, no en los retratos
PORTRAIT_PITCH = 62 / 1080    # separación fija entre retratos
# Distancia del centro de la pantalla al retrato más cercano de cada fila (r5 / d1).
DEFAULT_ROW_OFFSET = {"r": 128 / 1080, "d": 139 / 1080}
DEFAULT_WEIGHT = 3            # cuántos clicks "vale" el punto de partida

GSI_HOST = "127.0.0.1"
GSI_PORT = 3000
OBS_HOST = "127.0.0.1"
DEFAULT_OBS_PORT = 4455
OBS_RETRY_S = 3.0             # segundos entre reintentos de conexión a OBS
GSI_STALE_S = 5.0             # sin POST de GSI durante tanto tiempo = sin señal

GSI_CFG_NAME = "gamestate_integration_obs.cfg"
# Texto exacto de la sección 8 del spec (idéntico al .cfg que funciona hoy).
GSI_CFG_TEXT = (
    '"OBS Dota Integration"\n'
    '{\n'
    '    "uri"           "http://127.0.0.1:3000/"\n'
    '    "timeout"       "5.0"\n'
    '    "buffer"        "0.0"\n'
    '    "throttle"      "0.01"\n'
    '    "heartbeat"     "2.0"\n'
    '    "data"\n'
    '    {\n'
    '        "provider"      "1"\n'
    '        "map"           "1"\n'
    '        "player"        "1"\n'
    '        "hero"          "1"\n'
    '        "abilities"     "1"\n'
    '        "items"         "0"\n'
    '        "draft"         "0"\n'
    '        "wearables"     "0"\n'
    '        "buildings"     "0"\n'
    '    }\n'
    '    "auth"\n'
    '    {\n'
    '        "token"         "overpower_dota_obs"\n'
    '    }\n'
    '}'
)

# Slots de jugador: Radiant r1..r5, Dire d1..d5.
SLOTS = [f"r{i}" for i in range(1, 6)] + [f"d{i}" for i in range(1, 6)]
