"""Publica en GitHub la versión ya empaquetada (scripts/empaquetar.py): sube la rama y la etiqueta vX.YZ y crea la
versión (Release) con los dos ZIP, el manual de usuario y las guías de instalación en PDF. Las notas salen del apartado
«## X.YZ» de CAMBIOS.md. VenB y VenB Rutas buscan sus ZIP en la última versión publicada (venb/actualizaciones.py).
Uso: python scripts/publicar.py [--borrador]
Necesita gh (GitHub CLI) con sesión iniciada y el remoto «origin». Fuera del ZIP (export-ignore).
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from empaquetar import RAIZ, git  # noqa: E402


def notas(version):
    with open(os.path.join(RAIZ, 'CAMBIOS.md'), encoding='utf-8') as f:
        texto = f.read()
    m = re.search(rf'^## {re.escape(version)}\b.*?\n(.*?)(?=^## |\Z)', texto, re.M | re.S)
    if not m or not m.group(1).strip():
        sys.exit(f'Falta el apartado «## {version}» en CAMBIOS.md.')
    return m.group(1).strip() + '\n'


def main():
    if git('status', '--porcelain'):
        sys.exit('Hay cambios sin confirmar.')
    version = git('describe', '--tags', '--exact-match').removeprefix('v')
    if not re.fullmatch(r'\d+\.\d{2}', version):
        sys.exit(f'Este commit no tiene una etiqueta vX.YZ ({version}).')
    carpeta = os.path.dirname(RAIZ)
    ficheros = [f'VenB-{version}.zip', f'VenB-{version}-Rutas.zip', f'Manual_VenB-{version}.pdf',
                f'Instalar_VenB-{version}.pdf', f'Instalar_VenB_Rutas-{version}.pdf']
    faltan = [f for f in ficheros if not os.path.exists(os.path.join(carpeta, f))]
    if faltan:
        sys.exit(f'Faltan {", ".join(faltan)}: ejecuta antes scripts/empaquetar.py.')
    texto = notas(version) + (
        f'\n**Descargas:** `VenB-{version}.zip` (VenB completo) o `VenB-{version}-Rutas.zip` (solo el Planificador). '
        f'Instrucciones en `Instalar_VenB-{version}.pdf` e `Instalar_VenB_Rutas-{version}.pdf`. '
        'Si ya tienes VenB 3.40 o posterior, usa «Actualizar ahora» en la aplicación.\n')
    rama = git('rev-parse', '--abbrev-ref', 'HEAD')
    subprocess.run(['git', '-C', RAIZ, 'push', 'origin', rama, f'v{version}'], check=True)
    with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(texto)
    try:
        orden = ['gh', 'release', 'create', f'v{version}', *[os.path.join(carpeta, x) for x in ficheros],
                 '--title', f'VenB {version}', '--notes-file', f.name, '--verify-tag']
        if '--borrador' in sys.argv:
            orden.append('--draft')
        subprocess.run(orden, check=True, cwd=RAIZ)
    finally:
        os.remove(f.name)


if __name__ == '__main__':
    main()
