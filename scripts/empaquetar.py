"""Genera el ZIP instalable de VenB a partir de la versión etiquetada en git, en la carpeta que contiene el repositorio.
Uso: python scripts/empaquetar.py [--con-datos] [--sin-manual]
Junto al ZIP deja el manual de usuario en ODT y PDF (scripts/manual.py), con el mismo texto que la Ayuda, y las guías
rápidas de instalación de VenB y VenB Rutas en PDF (scripts/guia.py), y borra los de versiones anteriores. Para publicarlos: scripts/publicar.py.
Solo entra lo que está en git, salvo lo marcado export-ignore. Con --con-datos añade tus datos e
informes en datos_iniciales/, nunca secretos: es un ZIP privado. El instalador los copia a VenB-datos sin sobrescribir."""
import hashlib
import io
import os
import re
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rutas  # noqa: E402
DATOS = ['datos', 'informes', 'estado', 'config']
NUNCA = ('calendario_url', 'calendario_cache', 'garmin_tokens', 'GarminConnectConfig.json', 'herramientas/')


def git(*a, binario=False):
    r = subprocess.run(['git', '-c', 'safe.directory=*', '-C', RAIZ, *a], capture_output=True, check=True)
    return r.stdout if binario else r.stdout.decode().strip()


def main():
    con_datos = '--con-datos' in sys.argv
    if git('status', '--porcelain'):
        sys.exit('Hay cambios sin confirmar: haz commit y etiqueta la versión antes de empaquetar.')
    version = git('describe', '--tags', '--always').removeprefix('v')
    if not re.fullmatch(r'\d+\.\d{2}', version):
        sys.exit(f'La versión {version} no es una etiqueta vX.YZ: etiqueta este commit antes de empaquetar.')
    pref = f'VenB-{version}/'
    nombre = f'VenB-{version}{"-con-mis-datos-PRIVADO" if con_datos else ""}.zip'
    destino = os.path.join(os.path.dirname(RAIZ), nombre)  # junto a la carpeta del repositorio
    base = zipfile.ZipFile(io.BytesIO(git('archive', '--format=zip', f'--prefix={pref}', 'HEAD', binario=True)))
    with zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED) as z:
        for i in base.infolist():
            if i.is_dir():
                continue
            i.create_system = 3  # Unix: conserva los permisos
            i.external_attr = (0o755 if i.filename.endswith('.sh') else 0o644) << 16
            z.writestr(i, base.read(i.filename))
        z.writestr(f'{pref}venb/VERSION', version + '\n')
        if con_datos:
            for carpeta in DATOS:
                for d, _, fs in os.walk(os.path.join(rutas.PERSISTE, carpeta)):
                    for f in fs:
                        ruta = os.path.join(d, f)
                        rel = os.path.relpath(ruta, rutas.PERSISTE).replace(os.sep, '/')
                        if not any(n in rel for n in NUNCA):
                            z.write(ruta, f'{pref}datos_iniciales/{rel}')
    with zipfile.ZipFile(destino) as z:
        lineas = [f'{hashlib.sha256(z.read(n)).hexdigest()}  {n[len(pref):]}' for n in z.namelist() if not n.endswith('/')]
    with zipfile.ZipFile(destino, 'a', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{pref}MANIFIESTO.txt', '\n'.join(lineas) + '\n')
    print(destino)
    if not con_datos:     # VenB Rutas (solo el Planificador), con el mismo número de versión
        import empaquetar_rutas
        print(empaquetar_rutas.empaquetar(version))
    if not con_datos and '--sin-manual' not in sys.argv:
        import guia       # guías rápidas de instalación de las dos ediciones (una página cada una)
        import manual     # manual de usuario
        for r in (*manual.generar(version, os.path.dirname(RAIZ), borrar_anteriores=True), *guia.generar(version, os.path.dirname(RAIZ))):
            print(r)


if __name__ == '__main__':
    main()
