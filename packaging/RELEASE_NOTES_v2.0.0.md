# v2.0.0 — Camaraman: app y demo completa

Camaraman cambia automáticamente la escena del jugador observado en Dota 2 y adapta
la cámara al HUD de 4, 5 o 6 habilidades usando los filtros Move Source de OBS.

- Interfaz en español e inglés, nombres y enlaces por jugador, selección Cámara/Foto,
  asignación Radiant/Dire más visible y colores sobrios.
- Cuenta espacios del HUD, incluidas innatas que ocupan un espacio y habilidades nuevas
  de Shard/Cetro cuando llegan por GSI. Mantiene el ajuste actualizado mientras está al aire.
- Corregido: elegir Foto con URL vacía ya no muestra la cámara como alternativa. Las dos
  fuentes quedan ocultas y se sigue aplicando la posición/escala de la escena.
- Demo completa: colección de OBS, borde, máscara y fondo, capturas, guía bilingüe y
  `PREPARAR_DEMO.cmd`. Elige la carpeta Camaraman y se genera una escena con rutas locales.
- Incluye el instalador oficial de Move Transition 3.2.1, su código fuente y licencia.
  Instalación manual con OBS cerrado; requiere **OBS Studio 31.1 o posterior**.
- Lienzo base **3840×2160**, con los parámetros originales H 4/5/6. La salida puede ser
  1080p o QHD sin cambiar filtros. La guía explica la conversión si cambias el lienzo base.
- Corregido el empaquetado de DLL de Qt para evitar el error de importación de QtWidgets.

## Instalación

Descarga y extrae **todo** `DotaPlayerCams-v2.0.0-windows.zip`. Sigue
`GUIA_PRIMERA_VEZ.txt` y `Camaraman/LEEME-DEMO.md`. `SHA256SUMS.txt` incluye las sumas
de los archivos distribuidos.

## Compatibilidad

Las escenas de v1 no sirven para v2: importa la demo o migra tu colección. v1.0.1
continúa disponible. Tus ajustes se conservan en `%APPDATA%/OverPowerCamarasDota`.

GSI no distingue de forma fiable la selección del oso y otras invocaciones/ilusiones
en las pruebas realizadas; no se promete ajuste automático de su HUD.
