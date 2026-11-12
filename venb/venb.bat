@echo off
rem Lanzador de VenB: se queda esperando en la terminal hasta que se cierre la aplicacion.
rem VenB (c) Jose A. Jimenez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0.
chcp 65001 >nul
set "PY=%USERPROFILE%\.venb\python\venb\Scripts\python.exe"
if not exist "%PY%" (
    echo VenB no esta instalada. Ejecuta INSTALAR-EN-WINDOWS
    pause
    exit /b 1
)
cd /d "%~dp0"
"%PY%" lanzador.py
