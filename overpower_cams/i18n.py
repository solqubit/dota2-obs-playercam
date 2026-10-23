"""Idioma de la interfaz (español / inglés).

Los textos se escriben en español en el código y pasan por `tr("texto", nombre=valor)`:
el texto en español es también la clave del catálogo `EN`. Con el idioma "en" se devuelve
la traducción (si falta, el español: nunca falla) y luego se aplica `.format(**kw)`.

El idioma se elige UNA vez al arrancar (`set_language`), antes de crear cualquier texto;
cambiarlo en Ajustes se aplica al reiniciar la app.
"""
from __future__ import annotations

LANGUAGES = {"es": "Español", "en": "English"}
DEFAULT_LANGUAGE = "es"

_language = DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    """Fija el idioma ("es" o "en"); cualquier otro valor deja el español."""
    global _language
    _language = code if code in LANGUAGES else DEFAULT_LANGUAGE


def get_language() -> str:
    return _language


def tr_for(code: str, text: str, **kw) -> str:
    """Como `tr`, pero en el idioma `code` (p. ej. para avisar en el idioma recién elegido)."""
    out = EN.get(text, text) if code == "en" else text
    if not kw:
        return out
    try:
        return out.format(**kw)
    except (KeyError, IndexError, ValueError):
        return text.format(**kw)   # traducción con marcadores distintos: mejor el español


def tr(text: str, **kw) -> str:
    """`text` (español, también la clave) en el idioma actual, con `.format(**kw)` si hay kw."""
    return tr_for(_language, text, **kw)


def detect_default() -> str:
    """"es" si Windows está en español (cualquier variante); si no, o ante cualquier error, "en"."""
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "es" if (lang_id & 0x3FF) == 0x0A else "en"
    except Exception:  # noqa: BLE001 - sin Windows o sin ctypes: inglés
        return "en"


# Catálogo español -> inglés. Lo revisa tests/test_i18n.py: cada tr("…") del código tiene
# su entrada, no sobran entradas y los marcadores {nombre} coinciden.
EN: dict[str, str] = {
    "No pude confirmar que Move Transition esté cargado; OBS no informa los tipos de filtro disponibles.":
        "Could not confirm that Move Transition is loaded; OBS does not report the available filter kinds.",
    "No pude leer los datos de jugadores; se conserva el archivo existente. Vuelve a intentar guardar.":
        "Could not read player data; the existing file is preserved. Try saving again.",
    # ---- app / config ----
    "OverPower · Cámaras Dota": "OverPower · Dota Player Cams",
    "Los detalles están en:\n{path}": "Details were saved to:\n{path}",
    "No pude guardar los detalles.": "Couldn't save the details.",
    "Ocurrió un error inesperado y la app puede no funcionar bien.":
        "An unexpected error occurred and the app may not work properly.",
    "Cierra lo que lo esté usando y vuelve a abrir la app.":
        "Close whatever is using it and open the app again.",
    "no pude guardar los retratos: {error}": "couldn't save the portraits: {error}",
    "no pude escuchar teclado y mouse: {error}": "couldn't listen to keyboard and mouse: {error}",

    # ---- checks: instrucciones ----
    "1. Abre OBS Studio.\n"
    "2. Ve a Herramientas → Ajustes del servidor WebSocket.\n"
    "3. Marca «Habilitar servidor WebSocket».\n"
    "4. Revisa que el puerto sea el mismo que está en Ajustes de esta app (por defecto 4455).\n"
    "5. Pulsa «Mostrar información de conexión», copia la contraseña y pégala en Ajustes de esta app.":
        "1. Open OBS Studio.\n"
        "2. Go to Tools → WebSocket Server Settings.\n"
        "3. Check \"Enable WebSocket server\".\n"
        "4. Make sure the port matches the one in this app's Settings (4455 by default).\n"
        "5. Click \"Show Connect Info\", copy the password and paste it in this app's Settings.",
    "OBS está abierto, pero rechazó la contraseña.\n"
    "1. En OBS ve a Herramientas → Ajustes del servidor WebSocket.\n"
    "2. Pulsa «Mostrar información de conexión» y copia la contraseña.\n"
    "3. Pégala en Ajustes de esta app.":
        "OBS is open, but it rejected the password.\n"
        "1. In OBS, go to Tools → WebSocket Server Settings.\n"
        "2. Click \"Show Connect Info\" and copy the password.\n"
        "3. Paste it in this app's Settings.",
    "Dota está abierto pero no está mandando datos a la app.\n"
    "1. Entra a una partida o a ver una repetición: en el menú principal Dota no manda nada.\n"
    "2. Revisa que la revisión «Archivo GSI» esté en verde y reinicia Dota si la acabas de arreglar.\n"
    "3. Si sigue sin llegar nada: en Steam, clic derecho en Dota 2 → Propiedades → Opciones de "
    "lanzamiento y agrega  -gamestateintegration  (Valve lo documenta como necesario; en algunos "
    "equipos funciona sin esa opción).\n"
    "4. Cierra Dota por completo y ábrelo de nuevo.":
        "Dota is open but isn't sending data to the app.\n"
        "1. Join a match or watch a replay: Dota sends nothing from the main menu.\n"
        "2. Make sure the \"GSI file\" check is green, and restart Dota if you just fixed it.\n"
        "3. If still nothing arrives: in Steam, right-click Dota 2 → Properties → Launch Options "
        "and add  -gamestateintegration  (Valve documents it as required; on some PCs it works "
        "without it).\n"
        "4. Close Dota completely and open it again.",

    # ---- checks: títulos y botones ----
    "Dota instalado": "Dota installed",
    "Archivo GSI": "GSI file",
    "Datos de Dota llegando": "Dota data arriving",
    "Teclas de espectador": "Spectator hotkeys",
    "OBS y WebSocket": "OBS and WebSocket",
    "Escena de OBS": "OBS scene",
    "Agrega en OBS las fuentes que faltan (se llaman «Camara · escena», «Foto · escena», «Fondo · escena» y «Nombre · escena»), o copia otra escena de jugador.": "Add the missing sources in OBS (they are named \"Camara · scene\", \"Foto · scene\", \"Fondo · scene\" and \"Nombre · scene\"), or copy another player scene.",
    "Crear escenas": "Create scenes",
    "Esas escenas ya existen en OBS pero no están dentro de «{scene}»: agrégalas ahí a mano ({names})": "Those scenes already exist in OBS but are not inside \"{scene}\": add them there by hand ({names})",
    "Escenas creadas: {names}": "Scenes created: {names}",
    "Escenas de jugador": "Player scenes",
    "Falta el plugin Move Transition o los filtros H 4/5/6 habilidades en «{scene}»: {names}": "The Move Transition plugin or the H 4/5/6 habilidades filters are missing in \"{scene}\": {names}",
    "OBS no tiene el plugin Move Transition: los filtros H 4/5/6 habilidades no mueven nada":
        "OBS doesn't have the Move Transition plugin: the H 4/5/6 habilidades filters don't move anything",
    "Estos filtros no son «Mover fuente» (Move Source) de Move Transition: {names}":
        "These filters aren't Move Transition's \"Move Source\" filters: {names}",
    "Fuentes de los jugadores": "Player sources",
    "Los 10 jugadores tienen URL en la fuente elegida": "All 10 players have a URL in their chosen source",
    "{scene}: {source} sin URL": "{scene}: {source} has no URL",
    "Sin URL en la fuente elegida, ese jugador sale al aire sin cámara ni foto.\n"
    "1. Abre la página Jugadores.\n"
    "2. Escribe la URL de cámara o de foto que falta, o cambia «Usar» a la fuente que sí tiene URL.":
        "Without a URL in the chosen source, that player goes on air with neither camera nor photo.\n"
        "1. Open the Players page.\n"
        "2. Type the missing camera or photo URL, or switch \"Use\" to the source that has a URL.",
    "Para crear las escenas que faltan la app copia «{template}», pero esa escena falta o está "
    "incompleta. Arréglala en OBS (con sus fuentes «Camara · {template}», «Foto · {template}», "
    "«Fondo · {template}» y «Nombre · {template}») o importa de nuevo la colección Camaraman, y "
    "pulsa «Revisar todo de nuevo».":
        "To create the missing scenes the app copies \"{template}\", but that scene is missing or "
        "incomplete. Fix it in OBS (with its sources \"Camara · {template}\", \"Foto · {template}\", "
        "\"Fondo · {template}\" and \"Nombre · {template}\") or import the Camaraman collection again, "
        "and press \"Re-check everything\".",
    "cambió la escena principal": "main scene changed",
    "Falta {file} en la carpeta de la app ({folder}): cópiala ahí y pulsa «Arreglar», o ponla a mano en OBS.": "{file} is missing from the app folder ({folder}): copy it there and press \"Fix\", or set it by hand in OBS.",
    "Falta {name} en la escena «{scene}» (las escenas de jugador funcionan igual)": "{name} is missing from the \"{scene}\" scene (the player scenes work anyway)",
    "Faltan escenas: {names}": "Missing scenes: {names}",
    "Faltan fuentes: {names}": "Missing sources: {names}",
    "Filtros de habilidades": "Ability filters",
    "Imágenes de las escenas": "Scene images",
    "Imágenes que están vacías o no existen en esta PC: {names}": "Images that are empty or don't exist on this PC: {names}",
    "Las 10 escenas de jugador tienen sus 4 fuentes": "All 10 player scenes have their 4 sources",
    "Las imágenes del Borde, las máscaras y los fondos existen": "The Borde image, the masks and the backgrounds exist",
    "Listo: cambié la imagen de {names}.": "Done: I changed the image of {names}.",
    "Listo: creé {names}, apagadas y copiadas de «{template}».": "Done: I created {names}, turned off and copied from \"{template}\".",
    "Listo: creé {name} en la escena «{scene}», vacío y oculto. Ponle su imagen en OBS si hace falta.": "Done: I created {name} in the \"{scene}\" scene, empty and hidden. Set its image in OBS if needed.",
    "Los filtros H 4/5/6 habilidades están en «{scene}»": "The H 4/5/6 habilidades filters are in \"{scene}\"",
    "Los filtros mueven la caja de habilidades según cuántas tenga el jugador.\n"
    "1. Instala el plugin Move Transition (move-transition 3.x) y reinicia OBS.\n"
    "2. En la escena «{scene}», clic derecho → Filtros, y agrega tres filtros «Mover fuente» (Move Source) llamados exactamente H 4 habilidades, H 5 habilidades y H 6 habilidades.\n"
    "3. En cada uno pon la posición y la escala que quieres para esa cantidad de habilidades.\n"
    "4. Pulsa «Revisar todo de nuevo».":
        "The filters move the abilities box according to how many abilities the player has.\n"
        "1. Install the Move Transition plugin (move-transition 3.x) and restart OBS.\n"
        "2. In the \"{scene}\" scene, right-click → Filters, and add three \"Move Source\" filters named exactly H 4 habilidades, H 5 habilidades and H 6 habilidades.\n"
        "3. In each one set the position and scale you want for that number of abilities.\n"
        "4. Press \"Check everything again\".",
    "No encuentro {files} en la carpeta de la app ({folder}). Cópialo ahí y vuelve a pulsar «Arreglar», o ponlo a mano en OBS.": "I can't find {files} in the app folder ({folder}). Copy it there and press \"Fix\" again, or set it by hand in OBS.",
    "No falta nada en la escena": "Nothing is missing from the scene",
    "No falta ninguna escena de jugador": "No player scene is missing",
    "No puedo arreglar las imágenes: OBS no está conectado o falta la escena «{scene}»": "Can't fix the images: OBS is not connected or the \"{scene}\" scene is missing",
    "No puedo crear las escenas porque falta la plantilla «{template}» o está incompleta. Arréglala en OBS y vuelve a intentar.": "I can't create the scenes because the template \"{template}\" is missing or incomplete. Fix it in OBS and try again.",
    "No puedo crear las escenas: OBS no está conectado o falta la escena «{scene}»": "Can't create the scenes: OBS is not connected or the \"{scene}\" scene is missing",
    "OBS no me dejó crear la escena «{scene}» ({error}). Ya creé: {done}. «{scene}» pudo quedar a medias en OBS: revísala o bórrala.": "OBS wouldn't let me create the scene \"{scene}\" ({error}). Already created: {done}. \"{scene}\" may have been left half-built in OBS: check it or delete it.",
    "Para usar la colección Camaraman en OBS:\n"
    "1. En OBS ve a Colección de escenas → Importar.\n"
    "2. Agrega el archivo .json de la colección Camaraman y confirma.\n"
    "3. Luego Colección de escenas → elige la colección importada.\n"
    "Si ya la tenías, revisa que la escena principal se llame como está en Ajustes (por defecto «Juego»).":
        "To use the Camaraman collection in OBS:\n"
        "1. In OBS, go to Scene Collection → Import.\n"
        "2. Add the Camaraman collection .json file and confirm.\n"
        "3. Then open Scene Collection → choose the imported collection.\n"
        "If you already had it, check that the main scene is named as in Settings (default \"Juego\").",
    "Se perdió la conexión con OBS: {error}": "Lost the connection with OBS: {error}",
    "Sin revisar: no existe la escena «{scene}»": "Not checked: the \"{scene}\" scene doesn't exist",
    "Todas las imágenes ya existen; no cambié nada": "All the images already exist; I changed nothing",
    "{names} y {n} más": "{names} and {n} more",
    "«Arreglar» apunta esas imágenes a las de la carpeta de la app ({folder}); el cambio se hace en vivo, con OBS abierto. Las rutas que sí existen no se tocan.": "\"Fix\" points those images to the ones in the app folder ({folder}); the change is made live, with OBS open. Paths that do exist are left alone.",
    "«Arreglar» crea {name} vacío y oculto en la escena «{scene}». No cambia nada más de la escena.": "\"Fix\" creates {name}, empty and hidden, in the \"{scene}\" scene. It changes nothing else in the scene.",
    "«Crear escenas» copia la escena «{template}» (con sus 4 fuentes, filtros y posición) para cada escena que falta y la agrega apagada a «{scene}». No toca las escenas que ya existen. Las fuentes que faltan en escenas existentes se agregan a mano en OBS.": "\"Create scenes\" copies the \"{template}\" scene (with its 4 sources, filters and position) for each missing scene and adds it, turned off, to \"{scene}\". It doesn't touch scenes that already exist. Sources missing from existing scenes are added by hand in OBS.",
    "«{scene}» existe y tiene el {name}": "\"{scene}\" exists and has the {name}",
    "Retratos": "Portraits",
    "Buscar…": "Browse…",
    "Arreglar": "Fix",

    # ---- checks: detalles ----
    "No encontré Dota": "Dota not found",
    "Esa carpeta no parece ser Dota 2 (falta game\\dota): {path}":
        "That folder doesn't look like Dota 2 (game\\dota is missing): {path}",
    "No encontré Dota: la carpeta {path} no existe": "Dota not found: the folder {path} doesn't exist",
    "Elige la carpeta donde está instalado Dota 2 (la que se llama «dota 2 beta» "
    "y contiene la carpeta «game»). Suele estar en <tu biblioteca de Steam>\\steamapps\\common.":
        "Choose the folder where Dota 2 is installed (the one named \"dota 2 beta\" that contains "
        "the \"game\" folder). It is usually in <your Steam library>\\steamapps\\common.",
    "No se puede revisar sin la carpeta de Dota": "Can't check without the Dota folder",
    "El archivo que le dice a Dota dónde mandar los datos está bien":
        "The file that tells Dota where to send data is OK",
    "Falta el archivo que le dice a Dota que mande los datos a esta app":
        "The file that tells Dota to send data to this app is missing",
    "El archivo de Dota para esta app tiene un contenido distinto al esperado":
        "Dota's file for this app has unexpected content",
    "«Arreglar» crea la carpeta gamestate_integration si no existe y escribe el archivo "
    "{file}. Dota lo lee al arrancar: si está abierto, hay que reiniciarlo.":
        "\"Fix\" creates the gamestate_integration folder if needed and writes the file {file}. "
        "Dota reads it at startup: if it's open, restart it.",
    "Llegan datos de Dota": "Data is arriving from Dota",
    "Sin datos: Abre Dota y entra a una partida": "No data: open Dota and join a match",
    "Dota está abierto pero no llegan datos": "Dota is open but no data is arriving",
    "No encontré el archivo de teclas de Dota (dotakeys_personal.lst). "
    "Las teclas rápidas no se van a poder usar; los clicks en retratos y GSI sí.":
        "Dota's hotkey file (dotakeys_personal.lst) was not found. Hotkeys won't work; "
        "portrait clicks and GSI will.",
    "Abre Dota con la misma cuenta de Steam, entra a Ajustes → Teclas rápidas y "
    "cierra la ventana para que Dota cree el archivo. Luego pulsa «Revisar todo de nuevo».":
        "Open Dota with the same Steam account, go to Settings → Hotkeys and close the window so "
        "Dota creates the file. Then click \"Re-check everything\".",
    "Faltan teclas de espectador para: {slots}": "Missing spectator hotkeys for: {slots}",
    "«Arreglar» (con Dota cerrado) hace una copia de seguridad del archivo y asigna "
    "las teclas 1 a 9 y 0 a los jugadores 1 a 10. Si otra acción de espectador usa "
    "esa tecla, la pasa a una libre (F9).":
        "\"Fix\" (with Dota closed) backs up the file and assigns keys 1 to 9 and 0 to players "
        "1 to 10. If another spectator action uses one of those keys, it moves that action to a "
        "free key (F9).",
    "Está activada la opción «Copiar las teclas rápidas del espectador desde la "
    "sección Teclas rápidas»; puede pisar las teclas de espectador":
        "The option that copies spectator hotkeys from the Hotkeys section is on; it can "
        "overwrite the spectator hotkeys",
    "«Arreglar» (con Dota cerrado) desactiva esa opción, con copia de seguridad.":
        "\"Fix\" (with Dota closed) turns that option off, with a backup.",
    "Los 10 jugadores tienen su tecla de espectador": "All 10 players have a spectator hotkey",
    "Se perdió la conexión con OBS — reintentando ({error})": "Lost connection to OBS — retrying ({error})",
    "Conectado a OBS en {host}:{port}": "Connected to OBS at {host}:{port}",
    "Falta la contraseña de OBS: escríbela en Ajustes": "OBS password missing: enter it in Settings",
    "Contraseña incorrecta: cámbiala en Ajustes": "Wrong password: change it in Settings",
    "Se perdió la conexión con OBS — reintentando": "Lost connection to OBS — retrying",
    "No pude conectar con OBS en {host}:{port}. ¿Está abierto y con el "
    "servidor WebSocket activado?":
        "Couldn't connect to OBS at {host}:{port}. Is it open with the WebSocket server enabled?",
    "No pude conectar con OBS: {error}": "Couldn't connect to OBS: {error}",
    "No se puede revisar la escena: OBS no está conectado": "Can't check the scene: OBS is not connected",
    "No existe la escena «{scene}» en OBS": "The \"{scene}\" scene doesn't exist in OBS",
    "Sin revisar: OBS no está conectado": "Not checked: OBS is not connected",
    "Sin revisar: se perdió la conexión con OBS": "Not checked: lost connection to OBS",
    "Los 10 ubicados ({n} afinados con tus clicks)": "All 10 located ({n} refined by your clicks)",

    # ---- checks: arreglos ----
    "Primero hay que elegir la carpeta de Dota": "Choose the Dota folder first",
    "Esa carpeta no parece ser Dota 2 (falta game\\dota): "
    "elige la carpeta correcta con «Buscar…»":
        "That folder doesn't look like Dota 2 (game\\dota is missing): choose the right folder "
        "with \"Browse…\"",
    "No pude escribir el archivo GSI: {error}": "Couldn't write the GSI file: {error}",
    "Listo: escribí {path}.": "Done: wrote {path}.",
    "Reinicia Dota para que lo lea.": "Restart Dota so it reads it.",
    "No encontré el archivo de teclas de Dota (dotakeys_personal.lst)":
        "Dota's hotkey file (dotakeys_personal.lst) was not found",
    "Cierra Dota por completo y vuelve a intentar": "Close Dota completely and try again",
    "No pude arreglar el archivo de teclas: {error}": "Couldn't fix the hotkey file: {error}",
    "Las teclas de espectador ya estaban bien; no cambié nada":
        "The spectator hotkeys were already fine; nothing was changed",
    "No pude asignar todas las teclas de espectador; no cambié nada":
        "Couldn't assign all spectator hotkeys; nothing was changed",
    "No pude guardar el archivo de teclas: {error}": "Couldn't save the hotkey file: {error}",
    "Listo: arreglé las teclas de espectador. Copia de seguridad: {backup}. "
    "Si al abrir Steam aparece un conflicto de sincronización (Steam Cloud), "
    "elige la versión local.":
        "Done: fixed the spectator hotkeys. Backup: {backup}. If Steam shows a sync conflict "
        "(Steam Cloud) when it opens, choose the local version.",
    "No puedo arreglar la escena: OBS no está conectado o falta la escena «{scene}»":
        "Can't fix the scene: OBS is not connected or the \"{scene}\" scene is missing",
    "OBS no me dejó crear «{name}»": "OBS refused to create \"{name}\"",
    "OBS no me dejó cambiar la imagen de {name} (ya cambié: {done})":
        "OBS refused to change the image of {name} (already changed: {done})",
    "OBS no me dejó cambiar la imagen de {name}": "OBS refused to change the image of {name}",
    "{name} ahora usa {path}": "{name} now uses {path}",
    "La revisión «{id}» no tiene un arreglo automático": "The \"{id}\" check has no automatic fix",

    # ---- dota_keys ----
    "el archivo no tiene la sección \"Keys\"": "the file has no \"Keys\" section",

    # ---- engine (eventos y motivos) ----
    "oculto": "hidden",
    "sin partida": "no match",
    "fuera de juego ({state})": "out of game ({state})",
    "fuera de juego ({state}) → oculto": "out of game ({state}) → hidden",
    "sin héroe": "no hero",
    "sin héroe → oculto": "no hero → hidden",
    "retrato {slot} mal aprendido: se vuelve a aprender": "portrait {slot} was learned wrong: learning it again",
    "la tecla {key} no seleccionó a {slot} en Dota": "pressed {key} but Dota did not select {slot}",
    "click retrato {slot} → {cam}": "click on portrait {slot} → {cam}",
    "tecla {slot}": "key {slot}",
    "{n}/10 escenas de jugador encontradas": "{n}/10 player scenes found",
    "tecla {key} → {cam}": "key {key} → {cam}",
    "click en la barra superior (x={x}): esperando a GSI para aprenderlo":
        "click on the top bar (x={x}): waiting for GSI to learn it",

    # ---- gsi_server / local_input ----
    "El puerto {port} está en uso por otra copia de la app, la consola u otro programa ({error})":
        "Port {port} is in use by another copy of the app, the console or another program ({error})",
    "entrada local: {error}": "local input: {error}",

    # ---- obs_link ----
    "Se perdió la conexión con OBS ({error})": "Lost connection to OBS ({error})",
    "La escena '{scene}' no existe en OBS": "The '{scene}' scene doesn't exist in OBS",
    "Fuentes de OBS cargadas": "OBS sources loaded",
    "{scene} no está en la escena de OBS: se apaga la escena anterior":
        "{scene} isn't in the OBS scene: turning off the previous scene",
    "{scene}: la fuente elegida no tiene URL; cámara y foto quedan ocultas":
        "{scene}: the selected source has no URL; camera and photo are hidden",
    "OBS rechazó un cambio en {name} ({error})": "OBS refused a change to {name} ({error})",
    "ninguna": "none",
    "Reconectado a OBS en {host}:{port}": "Reconnected to OBS at {host}:{port}",
    "reconexión": "reconnect",
    "OBS rechazó cambiar la imagen de {name} ({error})": "OBS refused to change the image of {name} ({error})",
    "OBS rechazó crear {name} ({error})": "OBS refused to create {name} ({error})",
    "Creado {name} en la escena '{scene}'": "Created {name} in the '{scene}' scene",
    "No se pudo crear la escena '{scene}': {error}": "Could not create the '{scene}' scene: {error}",

    # ---- ventana: Revisión ----
    "Imágenes": "Images",
    "Todos los archivos": "All files",
    "Revisando…": "Checking…",
    "Revisar todo de nuevo": "Re-check everything",
    "Revisiones": "Checks",
    "Falló la revisión: {error}": "The checks failed: {error}",
    "Ver instrucciones": "Show instructions",
    "Buscar… {name}": "Browse… {name}",
    "¿Quieres que haga este cambio ahora?": "Make this change now?",
    "Confirmar cambio": "Confirm change",
    "No se pudo arreglar": "Couldn't fix",
    "Error al arreglar": "Error while fixing",
    "Arreglado: {title}": "Fixed: {title}",
    "Listo": "Done",
    "Elige la carpeta de Dota 2 («dota 2 beta»)": "Choose the Dota 2 folder (\"dota 2 beta\")",
    "Carpeta equivocada": "Wrong folder",
    "Imagen para «{name}»": "Image for \"{name}\"",
    "No se pudo cambiar la imagen": "Couldn't change the image",
    "No pude cambiar la imagen de «{name}». ¿OBS está abierto y conectado?":
        "Couldn't change the image of \"{name}\". Is OBS open and connected?",
    "Esa carpeta no parece ser Dota 2 (falta game\\dota). Elige la carpeta "
    "«dota 2 beta», la que contiene la carpeta «game».":
        "That folder doesn't look like Dota 2 (game\\dota is missing). Choose the \"dota 2 beta\" "
        "folder, the one that contains the \"game\" folder.",

    # ---- ventana principal ----
    "Para cambiar al instante, la app detecta las teclas y clicks mientras "
    "Dota está activo.":
        "To switch instantly, the app detects keys and clicks while Dota is the active window.",
    "Con «Ocultar todo» la app no escucha el teclado ni el mouse.":
        "With \"Hide all\" the app doesn't listen to the keyboard or mouse.",
    "Falta la contraseña de OBS. Ábrela en OBS (Herramientas → Ajustes del "
    "servidor WebSocket → Mostrar información de conexión), cópiala y pégala aquí.":
        "The OBS password is missing. Find it in OBS (Tools → WebSocket Server Settings → "
        "Show Connect Info), copy it and paste it here.",
    "Ajustes": "Settings",
    "Jugadores": "Players",
    "Escena OBS": "OBS scene",
    "Eventos": "Events",
    "Lo que la app necesita para funcionar. Nada se cambia sin preguntarte.":
        "What the app needs to work. Nothing is changed without asking you.",
    "Lo que pasó en esta sesión, lo más nuevo arriba.": "What happened in this session, newest first.",
    "Radiant es": "Radiant is",
    "Radiant es: {team}": "Radiant is: {team}",
    "Equipo 1": "Team 1",
    "Equipo 2": "Team 2",
    "nunca": "never",
    "hace {n} s": "{n} s ago",
    "hace {n} min": "{n} min ago",
    "Al aire: {details}": "On air: {details}",
    "Al aire: nada (Ocultar todo)": "On air: nothing (Hide all)",
    "Al aire: ninguna cámara": "On air: no camera",
    "{n} habilidades": "{n} abilities",
    "Revisión": "Checks",
    "Modo": "Mode",
    "Automático": "Automatic",
    "Ocultar todo": "Hide all",
    "motor: {error}": "engine: {error}",
    "teclas de Dota: {error}": "Dota hotkeys: {error}",
    "conectado": "connected",
    "falta la contraseña (⚙ Ajustes)": "password missing (⚙ Settings)",
    "contraseña incorrecta": "wrong password",
    "conectando…": "connecting…",
    "reconectando": "reconnecting",
    "datos llegando": "data arriving",
    "sin datos": "no data",
    "Partida": "Match",
    "en juego": "in game",
    "fuera de partida": "not in a match",
    "Teclas de Dota recargadas": "Dota hotkeys reloaded",
    "no pude guardar el estado: {error}": "couldn't save the state: {error}",
    "teclado y mouse: {error}": "keyboard and mouse: {error}",
    "Modo: Automático": "Mode: Automatic",
    "Modo: Ocultar todo (sin escuchar teclado ni mouse)": "Mode: Hide all (not listening to keyboard or mouse)",
    "No se pudo guardar": "Couldn't save",
    "No pude guardar los ajustes: {error}": "Couldn't save the settings: {error}",
    "Retratos olvidados: vuelven a la posición inicial": "Portraits forgotten: back to the default positions",
    "Ajustes de OBS cambiados: conectando a {host}:{port}": "OBS settings changed: connecting to {host}:{port}",
    "El idioma nuevo se aplica al reiniciar la app.": "The new language applies after restarting the app.",
    "Reiniciar ahora": "Restart now",
    "Más tarde": "Later",
    "No pude volver a abrir la app: {error}": "Couldn't reopen the app: {error}",

    # ---- Jugadores ----
    "Los cambios se guardan y se aplican en OBS al momento.":
        "Changes are saved and applied in OBS right away.",
    "Nombre del equipo": "Team name",
    "Nombre del jugador": "Player name",
    "Rol": "Role",
    "Nombre": "Name",
    "URL de cámara": "Camera URL",
    "URL de foto": "Photo URL",
    "Usar": "Use",
    "Habilidades": "Abilities",
    "Cámara": "Camera",
    "Foto": "Photo",
    "no pude guardar los jugadores: {error}": "couldn't save the players: {error}",
    "OBS no está conectado: el cambio de {scene} se guardó y se aplica al reconectar":
        "OBS isn't connected: the change to {scene} was saved and is applied on reconnect",
    "No pude aplicar en OBS el cambio de {scene}: ¿existe la escena con sus fuentes?":
        "Couldn't apply the change to {scene} in OBS: does the scene exist with its sources?",

    # ---- Escena OBS ----
    "Volver a leer": "Read again",
    "Lo que la app usa de OBS. Nada se cambia sin preguntarte.":
        "What the app uses from OBS. Nothing is changed without asking you.",
    "Existe en OBS": "Exists in OBS",
    "{n} de 10 dentro de «{scene}»": "{n} of 10 inside \"{scene}\"",
    "Está en «{scene}»": "It's in \"{scene}\"",
    "Falta en «{scene}»": "Missing from \"{scene}\"",
    "Falta {name} en «{scene}»": "{name} is missing from \"{scene}\"",
    "No está en «{scene}»": "Not in \"{scene}\"",
    "Posición {x}, {y} · escala {sx} / {sy}": "Position {x}, {y} · scale {sx} / {sy}",
    "Probar": "Test",
    "Probar activa el filtro sobre la escena al aire, o sobre «{template}» si no hay ninguna.":
        "Test runs the filter on the scene on air, or on \"{template}\" if there is none.",
    "Probando {name}": "Testing {name}",
    "No se pudo probar": "Couldn't test",
    "No pude activar «{name}». ¿OBS está abierto y conectado?":
        "Couldn't run \"{name}\". Is OBS open and connected?",
    "falta": "missing",
    "faltan: {names}": "missing: {names}",
    "lista": "ready",
    "Crear las que faltan copiando «{template}»": "Create the missing ones by copying \"{template}\"",
    "Voy a crear en OBS estas escenas copiando «{template}» (con sus 4 fuentes, filtros y posición) "
    "y agregarlas apagadas a «{scene}»:\n\n{names}\n\nNo toco las escenas que ya existen. ¿Sigo?":
        "I'll create these scenes in OBS by copying \"{template}\" (with its 4 sources, filters and "
        "position) and add them, hidden, to \"{scene}\":\n\n{names}\n\nScenes that already exist "
        "aren't touched. Go ahead?",
    "No se pudieron crear las escenas": "Couldn't create the scenes",
    "OBS no me dejó terminar la escena «{scene}» ({error}). Ya creé: {done}.\n\n«{scene}» pudo "
    "quedar a medias: bórrala en OBS antes de volver a intentar.":
        "OBS didn't let me finish the scene \"{scene}\" ({error}). Already created: {done}.\n\n"
        "\"{scene}\" may be half-built: delete it in OBS before trying again.",
    "Imagen del Borde": "Border image",
    "Leyendo…": "Reading…",
    "No pude leer la imagen": "Couldn't read the image",
    "Sin imagen": "No image",
    "No existe en esta PC: {path}": "Doesn't exist on this PC: {path}",
    "El Borde se ve solo cuando hay una cámara al aire. Es fijo: no se mueve ni cambia de tamaño "
    "con la cámara.":
        "The border shows only while a camera is on air. It's fixed: it doesn't move or resize "
        "with the camera.",

    # ---- Ajustes ----
    "Se guardan solo en esta PC.": "Stored only on this PC.",
    "Dirección de OBS": "OBS address",
    "Normalmente {host} (esta misma PC)": "Usually {host} (this same PC)",
    "Escena principal": "Main scene",
    "La escena que tiene las 10 escenas de jugador. Por defecto «{scene}».":
        "The scene that holds the 10 player scenes. Default: \"{scene}\".",
    "Idioma": "Language",
    "Al arrancar": "At startup",
    "Radiant al arrancar": "Radiant at startup",
    "Qué equipo es Radiant si no hay uno guardado de la vez anterior":
        "Which team is Radiant when none was saved last time",
    "Modo inicial": "Initial mode",
    "El modo si no hay uno guardado de la vez anterior": "The mode when none was saved last time",
    "Descartar cambios": "Discard changes",
    "Pega aquí la contraseña de OBS": "Paste the OBS password here",
    "Mostrar": "Show",
    "Ocultar": "Hide",
    "Contraseña de OBS WebSocket": "OBS WebSocket password",
    "Se guarda solo en esta PC. En OBS: Herramientas → Ajustes del servidor "
    "WebSocket → Mostrar información de conexión.":
        "Stored only on this PC. In OBS: Tools → WebSocket Server Settings → Show Connect Info.",
    "Puerto de OBS": "OBS port",
    "Por defecto {port}": "Default: {port}",
    "Carpeta de Dota": "Dota folder",
    "Elegida a mano": "Chosen manually",
    "Encontrada automáticamente": "Found automatically",
    "(no encontrada)": "(not found)",
    "Pulsa «Buscar…» y elige la carpeta «dota 2 beta»": "Click \"Browse…\" and choose the \"dota 2 beta\" folder",
    "Idioma / Language": "Language / Idioma",
    "Se aplica al reiniciar la app": "Applies after restarting the app",
    "Olvidar": "Forget",
    "Retratos aprendidos": "Learned portraits",
    "{n} afinados con tus clicks. «Olvidar» vuelve a la posición inicial.":
        "{n} refined by your clicks. \"Forget\" resets them to the default positions.",
    "Olvidar retratos": "Forget portraits",
    "Se borra lo que la app aprendió de tus clicks en los retratos y vuelve a la "
    "posición inicial (los 10 siguen ubicados). ¿Continuar?":
        "This erases what the app learned from your clicks on the portraits and goes back to the "
        "default positions (all 10 stay located). Continue?",
    "Guardar": "Save",

    # ---- consola ----
    "Teclas de Dota: {keys}": "Dota hotkeys: {keys}",
    "Sin tecla en Dota: {slots}  (asígnalas en Dota > Teclas > Espectador)":
        "No key in Dota for: {slots}  (assign them in Dota: Settings → Hotkeys → Spectator)",
    "Radiant = Equipo {radiant}   |   Dire = Equipo {dire}": "Radiant = Team {radiant}   |   Dire = Team {dire}",
    "Modo: Ocultar todo — escribe 'auto' para reanudar": "Mode: Hide all — type 'auto' to resume",
    "Modo: Automático — siguiendo el héroe seleccionado": "Mode: Automatic — following the selected hero",
    "{name} no está en la escena": "{name} isn't in the scene",
    "Roster ({n}/10)  [Radiant = Equipo {team}]:": "Roster ({n}/10)  [Radiant = Team {team}]:",
    "Contraseña de OBS: ": "OBS password: ",
    "No pude cargar las fuentes ({error}): se reintenta solo.":
        "Couldn't load the sources ({error}): retrying automatically.",
    "No pude conectar ({error}): se reintenta solo cada {seconds} s.":
        "Couldn't connect ({error}): retrying automatically every {seconds} s.",
    "Retratos: {n}/10 afinados con tus clicks": "Portraits: {n}/10 refined by your clicks",
    "No pude escuchar teclado y mouse ({error}): solo GSI, con ~1 s de retraso.":
        "Couldn't listen to keyboard and mouse ({error}): GSI only, with ~1 s delay.",
    "olvidar": "forget",
    "Comandos:": "Commands:",
    "Equipo 1 cambia de bando (úsalo si la moneda invirtió los lados)":
        "Team 1 switches sides (use it if the coin toss swapped the sides)",
    "ocultar todo   (bloqueado hasta 'auto')": "hide all   (locked until 'auto')",
    "seguir héroe seleccionado": "follow the selected hero",
    "modo, bando y cámara actual": "mode, side and current camera",
    "borrar los retratos aprendidos (se vuelven a aprender solos)":
        "erase the learned portraits (they're relearned automatically)",
    "Bloqueado. Escribe 'auto' para reanudar.": "Locked. Type 'auto' to resume.",
    "Siguiendo héroe seleccionado.": "Following the selected hero.",
    "Modo:    {mode}": "Mode:    {mode}",
    "Radiant: Equipo {radiant}   (Dire = Equipo {dire})": "Radiant: Team {radiant}   (Dire = Team {dire})",
    "OBS:     {state}": "OBS:     {state}",
    "sin conexión": "disconnected",
    "Cámara:  {camera}": "Camera:  {camera}",
    "Héroe:   {hero}": "Hero:    {hero}",
    "ninguno": "none",
    "Retratos: {n}/10 aprendidos": "Portraits: {n}/10 learned",
    "Retratos olvidados. Se vuelven a aprender al hacerles click.":
        "Portraits forgotten. They're relearned when you click them.",
}
