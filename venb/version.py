"""Versión de VenB: la etiqueta de git en desarrollo; el fichero VERSION en un ZIP instalado."""
import os
import subprocess

AQUI = os.path.dirname(os.path.abspath(__file__))


def version():
    # VERSION solo existe en los ZIP, y manda: una versión instalada no debe preguntar a git.
    try:
        with open(os.path.join(AQUI, 'VERSION'), encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        pass
    try:
        r = subprocess.run(['git', '-c', 'safe.directory=*', '-C', AQUI, 'describe', '--tags', '--dirty=-modificada', '--always'],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().removeprefix('v')
    except (OSError, subprocess.SubprocessError):
        pass
    return 'desconocida'


VERSION = version()
