"""Descarga diaria de Garmin (servicio garmindb de Linux y tarea «VenB Garmin» de Windows), con el freno de
venb/garmin_freno.py: si un inicio de sesión ha fallado hace poco, no lo intenta (para no provocar ni alargar un
bloqueo de Garmin por exceso de intentos) y anota el resultado de cada intento.
Se ejecuta con el Python de garmindb: solo biblioteca estándar.
Uso: python garmin_diario.py <python de garmindb> <carpeta de configuración de garmindb>"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'venb'))
import garmin_freno as FR  # noqa: E402


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    py, config = sys.argv[1], sys.argv[2]
    puede, motivo = FR.puede(manual=False)
    if not puede:
        print(f'Descarga diaria aplazada: {motivo}')
        return 0
    cli = os.path.join(os.path.dirname(py), 'garmindb_cli.py')
    log = os.path.join(config, 'descarga_diaria.log')
    with open(log, 'w', encoding='utf-8') as f:
        r = subprocess.run([py, cli, '-f', config, '--all', '--download', '--import', '--analyze', '--latest'],
                           stdout=f, stderr=subprocess.STDOUT, cwd=config, stdin=subprocess.DEVNULL,
                           env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    with open(log, encoding='utf-8', errors='replace') as f:
        texto = f.read()[-20000:]
    # garmindb termina con 0 aunque no pueda iniciar sesión: se mira su registro
    fallo = r.returncode != 0 or re.search(r'Failed to login|\b429\b|\b1015\b|rate.?limit|Traceback', texto, re.I)
    FR.registrar(not fallo, texto[-2000:])
    print(texto[-3000:])
    return 1 if fallo else 0


if __name__ == '__main__':
    sys.exit(main())
