@echo off
setlocal
pushd "%~dp0"
start "" "DotaPlayerCams\DotaPlayerCams.exe" --prepare-demo
popd
endlocal
