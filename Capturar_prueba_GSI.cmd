@echo off
setlocal
pushd "%~dp0"
title Prueba GSI - unidades e ilusiones
if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el Python del proyecto en .venv.
    pause
    popd
    exit /b 1
)
echo PRUEBA DE DIAGNOSTICO - no se conecta a OBS
echo.
echo 1. Cierra solo DotaPlayerCams si esta abierto. PUEDES DEJAR DOTA ABIERTO.
echo 2. Si estas viendo una partida, la captura empieza con el envio actual
echo    de Dota y no cambia su configuracion ni reinicia el juego.
echo 3. Como observador, manteniendo cada seleccion 5 segundos:
echo    heroe - oso - heroe - creep o torre - heroe.
echo 4. Al terminar pulsa Ctrl+C para guardar.
echo.
echo Para otra captura: Naga Siren, crea sus ilusiones y selecciona
echo heroe - una ilusion - otra ilusion - heroe, 5 segundos cada una.
echo No cambies de heroe hasta terminar la primera captura.
echo.
echo Debe aumentar el contador de POST y mostrar "formato observador".
echo En Probar heroe se guarda el heroe local, pero eso no confirma
echo si tienes seleccionado al heroe, al oso o a otra unidad.
echo El archivo gsi_captura_FECHA_HORA.jsonl se guarda en esta carpeta.
echo Si Dota estaba cerrado, el modo ampliado prepara las 16 solicitudes
echo temporalmente y muestra AHORA abre Dota. Ctrl+C restaura el cfg.
echo Algunas secciones pueden no ser publicadas por Dota aunque se soliciten.
echo El resumen final mostrara cuales llegaron y cuales no.
echo.
".venv\Scripts\python.exe" -u "tools\gsi_capture.py" --all-data %*
echo.
echo Si termino sin recibir POST, avisa antes de repetir la prueba.
pause
popd
endlocal
