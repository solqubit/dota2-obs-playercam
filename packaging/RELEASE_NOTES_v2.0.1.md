# v2.0.1 — Correcciones de Camaraman

Versión de mantenimiento sobre v2.0.0. No cambia la colección de OBS ni los ajustes.

- Revisión detecta cuando falta el plugin **Move Transition**: OBS conserva los filtros
  H 4/5/6 de un plugin que no está instalado y antes salían en verde. También avisa si un
  filtro H tiene el nombre correcto pero no es «Mover fuente» (Move Source).
  Si OBS no permite comprobar el plugin, muestra un aviso en lugar de confirmarlo en verde.
- Corregido: editar un jugador podía perderse en Windows. Al cambiar de escena la app ya no
  lee `players.json` del disco (usa lo último guardado, en memoria) y, si guardar falla, el
  campo vuelve a lo guardado y se avisa en Eventos para reintentar. Guardar reintenta unas
  veces si Windows tiene el archivo ocupado.
  Si no puede leer los datos existentes, cancela el guardado y conserva el archivo para no
  borrar jugadores al editar equipos ni borrar equipos al editar jugadores.
- Nueva revisión «Fuentes de los jugadores»: avisa qué jugadores tienen elegida una fuente
  (Cámara o Foto) sin URL, porque al aire no se ve ninguna de las dos.
- Corregido: cambiar la escena principal en Ajustes dejaba encendidos la escena del jugador y
  el Borde en la escena anterior.
- La columna Habilidades muestra «—» y la barra «Al aire» no dice «4 habilidades» mientras
  Dota no informe las habilidades del jugador (OBS sigue usando el filtro de 4).
- «Crear las que faltan» queda desactivado mientras corre otro arreglo, y Revisión ya no
  ofrece crear escenas cuando falta o está incompleta la plantilla «1 Hard carry».

## Instalación

Descarga y extrae **todo** `DotaPlayerCams-v2.0.1-windows.zip` y reemplaza la carpeta de la
versión anterior. Tus ajustes y jugadores se conservan en `%APPDATA%/OverPowerCamarasDota`.
`SHA256SUMS.txt` incluye las sumas de los archivos distribuidos.

## Compatibilidad

Igual que v2.0.0: requiere **OBS Studio 31.1 o posterior** y Move Transition 3.x (el
instalador 3.2.1 va incluido en `Camaraman/Plugins`).
