# v2.0.2 — Mostrar por jugador y cámara asistida

Versión sobre v2.0.1. No cambia la colección de OBS; tus ajustes y jugadores se conservan.

- **Casilla «Mostrar» por jugador** (página Jugadores). Si la desmarcas, al seleccionar a ese
  jugador no sale nada al aire: ni su escena (marco, nombre, cámara o foto) ni el Borde.
  Sirve para jugadores sin cámara ni foto. Se aplica al momento: si desmarcas al que está al
  aire desaparece, y si lo vuelves a marcar mientras está seleccionado, reaparece en su tamaño.
  «Probar» nunca anima a un jugador oculto.
- **Cámara asistida de Dota** (Revisión → «Cámara asistida», opcional). La app pone en
  `autoexec.cfg` la tecla del comando `dota_toggle_assisted_camera_operator`, para no tener que
  escribirlo en la consola en cada partida. Pulsas la tecla en una ventana y te dice al momento
  si está libre o qué acción de Dota la usa: las teclas rápidas de Dota le ganan a esta tecla
  (por ejemplo «Seleccionar mensajero» en F4), así que solo deja guardar teclas libres. Usa la
  posición física de la tecla, así funciona con teclados no estadounidenses. Crea la carpeta si
  falta, hace copia de seguridad y no toca el resto del archivo. Dota lee `autoexec.cfg` al
  arrancar: no hace falta ninguna opción de lanzamiento.
- Las teclas de Dota se leen de la **cuenta de Steam con sesión abierta** (antes, de la carpeta
  modificada más recientemente, que podía ser otra cuenta).
- El arreglo de teclas de espectador también tiene en cuenta las teclas de jugador y nunca usa
  la tecla de la cámara asistida.
- El archivo GSI se escribe de forma segura y Revisión explica con claridad si falta Steam,
  Dota o sus carpetas.

## Instalación

Descarga y extrae **todo** `DotaPlayerCams-v2.0.2-windows.zip` y reemplaza la carpeta de la
versión anterior. Tus ajustes y jugadores se conservan en `%APPDATA%/OverPowerCamarasDota`.
`SHA256SUMS.txt` incluye las sumas de los archivos distribuidos.

## Compatibilidad

Igual que v2.0.0: requiere **OBS Studio 31.1 o posterior** y Move Transition 3.x (el
instalador 3.2.1 va incluido en `Camaraman/Plugins`).
