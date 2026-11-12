@echo off
rem Instalador de VenB para Windows. Doble clic en este fichero.
rem Da igual donde se haya descomprimido el ZIP: scripts\ubicar.py busca la instalacion anterior y sus datos
rem (o propone Documentos\VenB la primera vez) y copia alli el programa; el resto se hace desde esa copia.
rem Con /actualizar CARPETA_BASE lo lanza el boton "Actualizar" de VenB: no pregunta nada (lo opcional que no
rem estuviera instalado se queda sin instalar) y al terminar vuelve a abrir VenB.
rem VenB (c) Jose A. Jimenez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0.
setlocal
chcp 65001 >nul
set "ORIGEN=%~dp0"
set "INTERNO=%USERPROFILE%\.venb"
set "VENV=%INTERNO%\python\venb"
set "GDB=%INTERNO%\python\garmindb"
set "ACTUALIZAR="
if /i "%~1"=="/actualizar" set "ACTUALIZAR=s"
if defined ACTUALIZAR set "BASE=%~2"
rem La ventana de la version anterior se esta cerrando: se le deja un momento
if defined ACTUALIZAR echo Actualizando VenB...
if defined ACTUALIZAR timeout /t 3 /nobreak >nul
rem Abierto desde dentro del ZIP: Windows solo ha sacado este fichero
if not exist "%ORIGEN%venb\app.py" goto sinextraer

call :buscarpy
if not defined PY call :sinpython
if not defined PY goto finsinpython
echo Python %VER% encontrado.

set "SALIDA=%TEMP%\venb_ubicar_%RANDOM%.txt"
rem Sin bloques entre parentesis: las rutas con parentesis, como "Program Files (x86)", los rompen
set "CONBASE="
if defined ACTUALIZAR set CONBASE=--base "%BASE%"
%PY% "%ORIGEN%scripts\ubicar.py" --salida "%SALIDA%" %CONBASE% || goto fallo
set /p DESTINO=<"%SALIDA%"
del "%SALIDA%" >nul 2>nul
if not exist "%DESTINO%\venb\app.py" goto fallo
set "DIR=%DESTINO%\"
for %%P in ("%DESTINO%") do set "PERSISTE=%%~dpPVenB-datos"
set "NOMBRE=VenB"
if exist "%DIR%venb\EDICION" set "NOMBRE=VenB Rutas"

echo 1. Instalando VenB en %VENV% (requiere internet)...
if not exist "%VENV%\Scripts\python.exe" %PY% -m venv "%VENV%" || goto fallo
"%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pip || goto fallo
"%VENV%\Scripts\python.exe" -m pip install --quiet -r "%DIR%scripts\requirements.txt" || goto fallo
"%VENV%\Scripts\python.exe" "%DIR%scripts\migrar_home.py" || goto fallo

echo 2. Preparando %PERSISTE% (lo que ya exista no se toca)...
for %%C in (config datos informes estado) do if not exist "%PERSISTE%\%%C" mkdir "%PERSISTE%\%%C"
if exist "%DIR%datos_iniciales" robocopy "%DIR%datos_iniciales" "%PERSISTE%" /E /XC /XN /XO /NJH /NJS /NFL /NDL >nul
if errorlevel 8 goto fallo

echo 3. Creando el acceso directo en el escritorio...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell); $l=$s.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\%NOMBRE%.lnk'); $l.TargetPath='%DIR%venb\venb.bat'; $l.WorkingDirectory='%DIR%venb'; $l.IconLocation='%DIR%venb\static\logo.ico'; $l.Save()" || goto fallo

"%VENV%\Scripts\python.exe" "%DIR%scripts\limpiar_versiones.py"

rem VenB Rutas (solo el Planificador) no lleva la descarga de Garmin
if exist "%DIR%venb\EDICION" goto fin
set "R=n"
if exist "%INTERNO%\garmin\GarminConnectConfig.json" set "R=s"
if exist "%USERPROFILE%\.venvs\garmindb" set "R=s"
if defined ACTUALIZAR if /i not "%R%"=="s" goto fin
if /i not "%R%"=="s" set /p "R=4. Instalar tambien la descarga automatica de Garmin? [s/N] "
if /i not "%R%"=="s" goto fin
if not exist "%GDB%\Scripts\python.exe" %PY% -m venv "%GDB%" || goto fallo
"%GDB%\Scripts\python.exe" -m pip install --quiet --upgrade garmindb || goto fallo
if not exist "%INTERNO%\garmin" mkdir "%INTERNO%\garmin"
if not exist "%INTERNO%\garmin\GarminConnectConfig.json" copy "%DIR%config\GarminConnectConfig.json.plantilla" "%INTERNO%\garmin\GarminConnectConfig.json" >nul
schtasks /Create /F /SC DAILY /ST 23:30 /TN "VenB Garmin" /TR "\"%GDB%\Scripts\python.exe\" \"%DIR%scripts\garmin_diario.py\" \"%GDB%\Scripts\python.exe\" \"%INTERNO%\garmin\"" || goto fallo
findstr /R /C:"\"usar_garmin\": *false" "%PERSISTE%\config\ajustes.json" >nul 2>nul && schtasks /Change /TN "VenB Garmin" /DISABLE >nul
echo.
echo Falta tu parte de Garmin:
echo   Abre VenB y, en Ajustes, Cuenta de Garmin, escribe tu correo y tu contrasena de Garmin Connect
echo   y pulsa "Descargar todo ahora". La primera descarga puede tardar horas.

:fin
rem Entornos de Python de las versiones anteriores a la 2.11, ya sustituidos por los de %INTERNO%\python.
for %%V in (venb garmindb) do if exist "%USERPROFILE%\.venvs\%%V" if exist "%INTERNO%\python\%%V\Scripts\python.exe" rmdir /s /q "%USERPROFILE%\.venvs\%%V"
rmdir "%USERPROFILE%\.venvs" 2>nul
if defined ACTUALIZAR goto abrir
echo.
echo VenB instalada en %DESTINO%. Abrela con el icono del escritorio.
echo Tus datos y configuracion estan en %PERSISTE% y sirven para todas las versiones.
if /i not "%ORIGEN%"=="%DIR%" echo Ya puedes borrar el ZIP descargado y la carpeta donde lo descomprimiste (%ORIGEN%).
pause
exit /b 0

:abrir
echo.
echo VenB actualizada en %DESTINO%. Abriendo la version nueva...
set "VENB_SIN_NAVEGADOR=1"
start "VenB" /d "%DIR%venb" "%DIR%venb\venb.bat"
exit /b 0

:sinextraer
echo Primero hay que extraer el ZIP: cierra esta ventana, pulsa con el boton derecho sobre el ZIP,
echo elige "Extraer todo..." y, en la carpeta extraida, haz doble clic en INSTALAR-EN-WINDOWS.
pause
exit /b 1

rem Busca Python 3.10 o posterior: en el PATH y, si no, donde lo dejan sus instaladores (recien
rem instalado, esta ventana aun no ve el PATH nuevo). Deja PY y VER; PYVIEJO si solo hay uno antiguo.
:buscarpy
set "PY="
set "PYVIEJO="
where py >nul 2>nul && call :probarpy py -3
if not defined PY where python >nul 2>nul && call :probarpy python
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" call :probarpy "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" -3
if not defined PY if exist "%SystemRoot%\py.exe" call :probarpy "%SystemRoot%\py.exe" -3
if not defined PY if exist "%LOCALAPPDATA%\Python\bin\python.exe" call :probarpy "%LOCALAPPDATA%\Python\bin\python.exe"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do if not defined PY if exist "%%~D\python.exe" call :probarpy "%%~D\python.exe"
exit /b 0

rem El acceso directo de la Microsoft Store que suplanta a python no devuelve version: se ignora.
:probarpy
set "VER="
for /f "delims=" %%V in ('call %* -c "import platform; print(platform.python_version())" 2^>nul') do set "VER=%%V"
if not defined VER exit /b 0
echo %VER%| findstr /r "^3\.[0-9]" >nul || (set "VER=" & exit /b 0)
call %* -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "PY=%*"
if not defined PY if not defined PYVIEJO set "PYVIEJO=%VER%"
exit /b 0

:sinpython
echo.
if defined PYVIEJO echo Este ordenador tiene Python %PYVIEJO%, pero VenB necesita Python 3.10 o posterior.
if not defined PYVIEJO echo VenB necesita Python 3.10 o posterior y no se encuentra en este ordenador.
echo Python es libre y gratuito, y solo hay que instalarlo una vez.
where winget >nul 2>nul || goto pyweb
echo.
set "R=s"
set /p "R=Instalar ahora Python 3.13 con el instalador de Windows (winget)? [S/n] "
if /i "%R%"=="n" goto pyweb
echo Instalando Python 3.13. Puede tardar unos minutos y Windows puede pedir permiso...
winget install -e --id Python.Python.3.13 --scope user --custom "PrependPath=1" --accept-package-agreements --accept-source-agreements
call :buscarpy
if not defined PY winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
if not defined PY call :buscarpy
if defined PY echo Python %VER% instalado. Seguimos con VenB.
if defined PY exit /b 0
echo.
echo No se ha podido instalar Python automaticamente.
:pyweb
echo.
echo Se abre en el navegador la pagina oficial de descarga: https://www.python.org/downloads/
echo   1. Pulsa "Download Python" y abre el fichero descargado.
echo   2. Si es el instalador de Python, marca abajo "Add python.exe to PATH" y pulsa "Install Now".
echo      Si es el "Python install manager", acepta lo que propone.
echo   3. Despues, vuelve a hacer doble clic en INSTALAR-EN-WINDOWS.
echo Mas detalles en el capitulo "Antes de instalar: Python" del manual de VenB.
start "" https://www.python.org/downloads/
exit /b 0

:finsinpython
pause
exit /b 1

:fallo
echo La instalacion ha fallado. Revisa los mensajes anteriores.
if defined ACTUALIZAR echo Tu version anterior sigue instalada: abrela con el icono del escritorio.
pause
exit /b 1
