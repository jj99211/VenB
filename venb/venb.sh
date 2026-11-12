#!/bin/bash
# Lanzador de VenB: se queda esperando en la terminal hasta que se cierre la aplicación.
# VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0.
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
for PY in "$HOME/.venb/python/venb/bin/python"; do
    if [ -x "$PY" ]; then
        cd "$DIR" && exec "$PY" lanzador.py
    fi
done
echo "VenB no está instalada. Ejecuta: bash instalar-en-linux.sh"
read -r -p "Pulsa Intro para salir." _
exit 1
