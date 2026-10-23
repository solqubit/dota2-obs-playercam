# Demo completa Camaraman / Complete demo

## Español

Esta demo incluye la app, la colección de OBS, los tres gráficos originales de
OverPower y el instalador oficial **Move Transition 3.2.1**, de Exeldro. Incluye también
su licencia GPL y su código fuente. No hace falta instalar Python.
Necesitas **OBS Studio 31.1 o posterior**, requerido por Move 3.2.x.

![Interfaz con datos de ejemplo / Interface with sample data](img/app.png)

![Ejemplo de cámara junto al HUD / Camera next to the HUD](img/in-game.png)

1. Extrae todo el ZIP en una ubicación permanente. Mantén juntas las carpetas
   `DotaPlayerCams` y `Camaraman`, junto a `PREPARAR_DEMO.cmd`.
2. Con OBS cerrado, instala `Camaraman/Plugins/move-transition-3.2.1-windows-installer.exe`.
   Abre OBS después de instalar. El preparador no instala plugins automáticamente.
3. Abre `PREPARAR_DEMO.cmd` y elige la carpeta **Camaraman** que acabas de extraer.
   Se genera `Camaraman/Ecenas/Camaraman-lista.json`, con las rutas locales de los gráficos.
   No se modifica tu colección actual de OBS. Si mueves la carpeta, vuelve a prepararla.
4. En OBS: **Colección de escenas → Importar**, importa el archivo `Camaraman-lista.json`
   y selecciona la colección **Camaraman Demo**. No importes la plantilla `Camaraman.json`
   directamente: sus imágenes están sin enlazar para distribuirla sin rutas personales.
5. En **Ajustes → Vídeo**, establece el **lienzo base en 3840×2160**.
   La salida escalada puede ser 1920×1080, 2560×1440 o 3840×2160.
6. Activa **Herramientas → Ajustes del servidor WebSocket → Habilitar servidor WebSocket**.
   Copia el puerto y la contraseña a Ajustes de la app.
7. Abre `DotaPlayerCams/DotaPlayerCams.exe`, ejecuta las revisiones y configura nombres,
   enlaces y el equipo que ocupa Radiant. La captura de juego está configurada para Dota 2;
   si no aparece, revisa sus propiedades en OBS con Dota abierto.

### Qué hace la app

Selecciona la cámara o foto del jugador observado a partir de las teclas de espectador,
clics en retratos y GSI. Lee los filtros **H 4 habilidades**, **H 5 habilidades** y
**H 6 habilidades**, cambia la posición/escala según las habilidades que recibe de Dota y
anima los cambios con Move Source. Controla también el nombre, los enlaces, el borde y
la asignación Radiant/Dire. Guarda tus datos en `%APPDATA%/OverPowerCamarasDota`.

**Cámara/Foto respeta tu selección:** si la URL elegida está vacía, ambas fuentes quedan
ocultas, sin usar automáticamente la alternativa. El ajuste de la escena se sigue aplicando;
el nombre, fondo y borde conservan su comportamiento habitual.

Las invocaciones e ilusiones tienen una limitación: GSI no siempre distingue su selección
de la del héroe. En las pruebas del oso, el inventario y el minimapa lo identifican, pero
`selected_unit` sigue indicando al Druida. La demo no promete ajuste automático para esas unidades.

### Lienzo base, salida y parámetros de transformación

**Los valores actuales proceden de un lienzo base 3840×2160 (4K UHD).** La configuración
original emite a 2560×1440 (QHD, frecuentemente llamado «2K»). La salida no determina las
coordenadas: las transformaciones se calculan en el lienzo base.

**Recomendado:** conserva el lienzo 4K de la demo y cambia solamente la salida.
Así no tienes que convertir posiciones, escalas ni gráficos para emitir a 1080p o QHD.

Estos son los valores originales, conservados en los tres filtros:

| Filtro | Posición X | Posición Y | Escala X | Escala Y |
|---|---:|---:|---:|---:|
| H 4 habilidades | 431 | 1778 | 0.199000001 | 0.200000003 |
| H 5 habilidades | 456 | 1819 | 0.180000007 | 0.180000007 |
| H 6 habilidades | 466 | 1860 | 0.156510413 | 0.156481475 |

La escala horizontal y vertical de H 6 no es exactamente igual; se conserva así.
Rotación: 0. Recortes: 0. La app lee los valores numéricos guardados por Move Source,
no solo el texto redondeado de su campo «Transformación».

Si decides **cambiar el lienzo base**, el factor respecto a esta demo es:

| Nuevo lienzo base | Factor desde 3840×2160 |
|---|---:|
| 1920×1080 | 0.5 |
| 2560×1440 (QHD) | 2/3 |
| 3840×2160 (4K UHD) | 1 |

Para una fuente que conserva sus dimensiones originales, multiplica **posición y escala**
por ese factor. Ejemplo H 4 a 1080p: X=215.5, Y=889, escala X=0.0995, Y=0.1.
Desde QHD a 1080p el factor es **0.75**, y desde QHD a 4K es **1.5**; 1080p no es la mitad de QHD.

Cambiar el lienzo también afecta al borde, captura de juego, escenas anidadas y sus límites.
Si redimensionas además la propia fuente/escena interna, no vuelvas a multiplicar su escala
sin comprobar el resultado: podrías escalar dos veces. Por eso esta demo mantiene su lienzo
original y recomienda reducir únicamente la salida. Verifica H 4/5/6 con «Probar» antes de emitir.

El archivo antiguo `PARAMETROS DE TRANSFORMACION 1080p.txt` de la carpeta original corresponde
a otra composición: no es la mitad de estos valores y no se utiliza en esta demo.

## English

The ZIP includes the app, OBS collection, all three OverPower graphics, and the official
Move Transition **3.2.1** installer, license and source archive. Python is not required.
Use **OBS Studio 31.1 or later**, required by Move 3.2.x.

1. Extract the whole ZIP. Keep `DotaPlayerCams`, `Camaraman` and `PREPARAR_DEMO.cmd` together.
2. Close OBS, run the installer inside `Camaraman/Plugins`, then restart OBS.
3. Run `PREPARAR_DEMO.cmd`, select the extracted **Camaraman** folder, and import the generated
   `Ecenas/Camaraman-lista.json` through OBS **Scene Collection → Import**. Select **Camaraman Demo**.
   The original template is preserved. Prepare again if you move the folder.
4. Set OBS **base canvas to 3840×2160**. Output may be 1080p, QHD or 4K without changing filters.
5. Enable OBS WebSocket, enter its connection details in the app, run Checks and fill Players.

The app switches player scenes, names, camera/photo URLs and the border; it reads the H 4/5/6
Move Source presets to fit the reported ability count. An empty selected URL hides both media
sources instead of showing the alternative. The scene transform still applies.
Summon/illusion selection is not reliably exposed in the tested GSI data.

The original presets in the table above are **4K canvas** values; **2560×1440 is the output**.
For a different base canvas, factors from 4K are 0.5 (1080p), 2/3 (QHD), or 1 (4K).
Multiply position and scale only while source dimensions stay unchanged. Nested scenes and
other graphics also need checking. Keeping the 4K base and changing output only avoids this work.

## Plugin: upstream and verification

- Project: https://github.com/exeldro/obs-move-transition
- Version: https://github.com/exeldro/obs-move-transition/releases/tag/3.2.1
- Installer SHA-256: `a3777ac68c0e7c86dbab8ea94146dbf4a48223e128696c32defd99ddaa56f8c8`
- The original unmodified installer, matching release source archive and GPL license are
  together in `Plugins/`. `SHA256SUMS.txt` at the ZIP root lists every bundled file.
