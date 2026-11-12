#!/bin/bash
# Instalador de VenB para Linux. Uso: bash instalar-en-linux.sh
# Con --actualizar CARPETA_BASE lo lanza el botón «Actualizar» de VenB: no pregunta nada (lo opcional que no estuviera
# instalado se queda sin instalar) y al terminar vuelve a abrir VenB en esta misma terminal.
# Da igual dónde se haya descomprimido el ZIP: scripts/ubicar.py busca la instalación anterior y sus datos
# (o propone ~/VenB la primera vez) y copia allí el programa; el resto se hace desde esa copia.
# VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0.
set -e
ORIGEN="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
INTERNO="$HOME/.venb"  # todo lo interno de VenB, en una sola carpeta oculta
VENV="$INTERNO/python/venb"
GDB="$INTERNO/python/garmindb"
ACTUALIZAR="" BASE=""
if [ "$1" = "--actualizar" ] && [ -n "$2" ]; then ACTUALIZAR=s; BASE="$2"; fi
if [ -n "$ACTUALIZAR" ]; then
    # Si algo falla, la terminal espera para que se pueda leer el mensaje (VenB ya está cerrada)
    trap 'echo; echo "La actualización ha fallado. Tu versión anterior sigue instalada: ábrela con su icono."; read -r -p "Pulsa Intro para cerrar." _' ERR
    echo "Actualizando VenB..."
fi

sin_python() {  # $1: versión antigua encontrada (vacío si no hay ninguna)
    echo
    if [ -n "$1" ]; then
        echo "Este ordenador tiene Python $1, pero VenB necesita Python 3.10 o posterior."
    else
        echo "VenB necesita Python 3.10 o posterior y no se encuentra en este ordenador."
    fi
    local id="" orden=""
    [ -r /etc/os-release ] && id=$(. /etc/os-release; echo " $ID $ID_LIKE ")
    case "$id" in
        *" ubuntu "*|*" debian "*|*" linuxmint "*) orden="sudo apt install python3 python3-venv python3-pip curl" ;;
        *" fedora "*|*" rhel "*|*" centos "*) orden="sudo dnf install python3 python3-pip curl" ;;
        *" opensuse"*|*" suse "*) orden="sudo zypper install python3 python3-pip curl" ;;
        *" arch "*|*" manjaro "*) orden="sudo pacman -S python python-pip curl" ;;
    esac
    if [ -n "$1" ]; then
        echo "Tu distribución trae una versión antigua: lo más sencillo es actualizarla a una versión reciente."
    elif [ -n "$orden" ]; then
        echo "Instálalo con esta orden (te pedirá tu contraseña) y vuelve a ejecutar el instalador:"
        echo
        echo "    $orden"
    else
        echo "Instala con el gestor de paquetes de tu distribución los paquetes de Python 3 (con venv y pip)"
        echo "y curl, y vuelve a ejecutar el instalador."
    fi
    echo
    echo "Más detalles en el capítulo «Antes de instalar: Python» del manual de VenB."
    exit 1
}

# python3 y, si es antiguo, cualquier python3.X instalado aparte (el más reciente primero).
PY="" VIEJO=""
for c in python3 $(compgen -c python3. | grep -E '^python3\.[0-9]+$' | sort -Vru); do
    p=$(command -v "$c" 2>/dev/null) || continue
    v=$("$p" -c 'import platform; print(platform.python_version())' 2>/dev/null) || continue
    if "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then PY=$p; break; fi
    if [ -z "$VIEJO" ]; then VIEJO=$v; fi
done
[ -n "$PY" ] || sin_python "$VIEJO"
if [ ! -f "$ORIGEN/venb/app.py" ]; then
    echo "Faltan ficheros de VenB junto al instalador: descomprime el ZIP completo y repite."
    exit 1
fi

SALIDA=$(mktemp)
if [ -n "$ACTUALIZAR" ]; then
    "$PY" "$ORIGEN/scripts/ubicar.py" --salida "$SALIDA" --base "$BASE"
else
    "$PY" "$ORIGEN/scripts/ubicar.py" --salida "$SALIDA"
fi
DIR=$(cat "$SALIDA"); rm -f "$SALIDA"
[ -d "$DIR" ] || { echo "No se ha podido preparar la carpeta de VenB."; exit 1; }
PERSISTE="$(dirname "$DIR")/VenB-datos"
# VenB Rutas (solo el Planificador): su propio icono, sin aviso semanal ni descarga de Garmin
EDICION=$(cat "$DIR/venb/EDICION" 2>/dev/null || true)
NOMBRE="VenB"
ICONO="VenB"
if [ "$EDICION" = rutas ]; then NOMBRE="VenB Rutas"; ICONO="VenB-Rutas"; fi

crear_venv() {  # Si falta python3-venv, crea el entorno sin pip y lo instala aparte.
    [ -x "$1/bin/pip" ] && return 0
    mkdir -p "$(dirname "$1")"
    if ! "$PY" -m venv "$1" 2>/dev/null; then
        rm -rf "$1"
        "$PY" -m venv --without-pip "$1"
        local pz; pz=$(mktemp --suffix=.pyz)
        curl -fsSL https://bootstrap.pypa.io/pip/pip.pyz -o "$pz"
        "$1/bin/python" "$pz" install pip
        rm -f "$pz"
    fi
}

echo "1. Instalando VenB en $VENV (requiere internet)..."
crear_venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$DIR/scripts/requirements.txt"
chmod +x "$DIR/venb/venb.sh" 2>/dev/null || true
"$VENV/bin/python" "$DIR/scripts/migrar_home.py"

echo "2. Preparando $PERSISTE (lo que ya exista no se toca)..."
mkdir -p "$PERSISTE/config" "$PERSISTE/datos" "$PERSISTE/informes" "$PERSISTE/estado"
if [ -d "$DIR/datos_iniciales" ]; then
    cp -rn "$DIR/datos_iniciales/." "$PERSISTE/" 2>/dev/null || true
fi

echo "3. Creando el icono..."
ENTRADA=$(mktemp)
cat > "$ENTRADA" <<EOF
[Desktop Entry]
Type=Application
Name=$NOMBRE
Comment=Vivir en Bici: entrenamiento, rutas y brevets
Exec=/bin/bash "$DIR/venb/venb.sh"
Icon=$DIR/venb/static/logo.png
Terminal=true
Categories=Utility;
EOF
mkdir -p "$HOME/.local/share/applications"
install -m 755 "$ENTRADA" "$HOME/.local/share/applications/$ICONO.desktop"
ESCRITORIO=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
[ -d "$ESCRITORIO" ] && install -m 755 "$ENTRADA" "$ESCRITORIO/$ICONO.desktop"
rm -f "$ENTRADA"

"$VENV/bin/python" "$DIR/scripts/limpiar_versiones.py" || true

if [ "$EDICION" != rutas ]; then
# El aviso se reescribe en cada instalación para que apunte siempre a la versión instalada.
U="$HOME/.config/systemd/user"
AVISO_PREVIO=
if [ -e "$U/entreno-aviso.timer" ]; then  # nombre del aviso hasta la versión 2.10
    systemctl --user disable --now entreno-aviso.timer 2>/dev/null || true
    rm -f "$U/entreno-aviso.service" "$U/entreno-aviso.timer"
    if [ -d "$U/entreno-aviso.service.d" ] && [ ! -e "$U/venb-aviso.service.d" ]; then
        mv "$U/entreno-aviso.service.d" "$U/venb-aviso.service.d"
    fi
    systemctl --user daemon-reload 2>/dev/null || true
    AVISO_PREVIO=s
fi
if command -v systemctl >/dev/null && command -v notify-send >/dev/null; then
    if [ -e "$U/venb-aviso.timer" ] || [ -n "$AVISO_PREVIO" ]; then
        R=s
    elif [ -n "$ACTUALIZAR" ]; then
        R=n
    else
        read -r -p "4. ¿Instalar el aviso semanal en el escritorio (lunes a las 17:00)? [s/N] " R || R=n
    fi
    if [[ "$R" =~ ^[sS] ]]; then
        mkdir -p "$U"
        cat > "$U/venb-aviso.service" <<EOF
[Unit]
Description=Aviso semanal de VenB

[Service]
Type=oneshot
ExecStart="$VENV/bin/python" "$DIR/scripts/aviso_semanal.py"
EOF
        cat > "$U/venb-aviso.timer" <<'EOF'
# Lunes a las 17:00; si el ordenador estaba apagado, poco después de encenderlo.
[Unit]
Description=Aviso semanal de VenB (lunes)

[Timer]
OnCalendar=Mon 17:00
Persistent=true
AccuracySec=1min

[Install]
WantedBy=timers.target
EOF
        chmod 644 "$U/venb-aviso.service" "$U/venb-aviso.timer"
        systemctl --user daemon-reload
        systemctl --user enable --now venb-aviso.timer
        echo "Aviso semanal activo desde $DIR."
    fi
fi

if [ -e "$INTERNO/garmin/GarminConnectConfig.json" ] || [ -d "$HOME/.venvs/garmindb" ]; then
    R=s  # ya estaba instalada: se actualiza sin preguntar
elif [ -n "$ACTUALIZAR" ]; then
    R=n
else
    read -r -p "5. ¿Instalar también la descarga automática de Garmin? [s/N] " R || R=n
fi
if [[ "$R" =~ ^[sS] ]]; then
    echo "5. Instalando la descarga de Garmin en $GDB..."
    crear_venv "$GDB"
    "$GDB/bin/python" -m pip install --quiet --upgrade garmindb
    mkdir -p "$INTERNO/garmin" && chmod 700 "$INTERNO" "$INTERNO/garmin"
    if [ ! -e "$INTERNO/garmin/GarminConnectConfig.json" ]; then
        cp "$DIR/config/GarminConnectConfig.json.plantilla" "$INTERNO/garmin/GarminConnectConfig.json"
        chmod 600 "$INTERNO/garmin/GarminConnectConfig.json"
    fi
    if command -v systemctl >/dev/null; then
        U="$HOME/.config/systemd/user"; mkdir -p "$U"
        # pasa por scripts/garmin_diario.py: no inicia sesión si hace poco que falló (freno de VenB)
        cat > "$U/garmindb.service" <<EOF
[Unit]
Description=Descarga diaria de datos de Garmin Connect (garmindb)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=%h/.venb/garmin
ExecStart=%h/.venb/python/garmindb/bin/python "$DIR/scripts/garmin_diario.py" %h/.venb/python/garmindb/bin/python %h/.venb/garmin
EOF
        cat > "$U/garmindb.timer" <<'EOF'
[Unit]
Description=Descarga diaria de Garmin a las 23:30

[Timer]
OnCalendar=*-*-* 23:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
        chmod 644 "$U/garmindb.service" "$U/garmindb.timer"
        systemctl --user daemon-reload
        systemctl --user enable --now garmindb.timer
        # «Usar Garmin Connect» desmarcado en Ajustes: la descarga diaria queda detenida
        if grep -qE '"usar_garmin": *false' "$PERSISTE/config/ajustes.json" 2>/dev/null; then
            systemctl --user disable --now garmindb.timer
            echo "Garmin Connect está desactivado en Ajustes: la descarga diaria queda detenida."
        fi
    fi
    if ! grep -q '"user": "[^"]' "$INTERNO/garmin/GarminConnectConfig.json"; then cat <<EOF

Falta tu parte de Garmin:
  Abre VenB y, en Ajustes > Cuenta de Garmin, escribe tu correo y tu contraseña de Garmin Connect
  y pulsa «Descargar todo ahora». La primera descarga puede tardar horas.
EOF
    fi
fi

fi  # fin de lo que no lleva VenB Rutas

# Entornos de Python de las versiones anteriores a la 2.11, ya sustituidos por los de ~/.venb/python.
for V in venb garmindb; do
    if [ -d "$HOME/.venvs/$V" ] && [ -x "$INTERNO/python/$V/bin/python" ]; then
        rm -rf "$HOME/.venvs/$V"
    fi
done
rmdir "$HOME/.venvs" 2>/dev/null || true

cat <<EOF

VenB instalada en $DIR. Ábrela con su icono o con: bash "$DIR/venb/venb.sh"
Tus datos y configuración están en $PERSISTE y sirven para todas las versiones.
Lo interno (Python, cuenta y datos descargados de Garmin) está en $INTERNO.
EOF
if [ -n "$ACTUALIZAR" ]; then
    trap - ERR
    echo
    echo "Abriendo la versión nueva..."
    cd "$HOME"
    rm -rf "$INTERNO/actualizar"   # el ZIP descomprimido (este instalador ya está en memoria)
    VENB_SIN_NAVEGADOR=1 exec /bin/bash "$DIR/venb/venb.sh"
fi
if [ "$ORIGEN" != "$DIR" ]; then
    echo "Ya puedes borrar el ZIP descargado y la carpeta donde lo descomprimiste ($ORIGEN)."
fi
