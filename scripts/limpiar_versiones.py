"""Borra las versiones anteriores de VenB que hay junto a esta. Lo ejecuta el instalador al terminar.
Solo borra una carpeta si es una versión anterior y no contiene nada añadido ni modificado:
se compara con su MANIFIESTO.txt o, en las versiones que no lo tienen, con los ficheros de esta.
Ante cualquier duda la conserva y lo avisa. Nunca toca VenB-datos ni otras carpetas."""
import hashlib
import os
import re
import shutil
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rutas  # noqa: E402

ACTUAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATRON = re.compile(re.escape(rutas.PREFIJO_CARPETA) + r'(\d+\.\d+)$')   # solo las de esta edición
MANIFIESTO = 'MANIFIESTO.txt'
SE_IGNORA = {'venb/VERSION', MANIFIESTO}


def ficheros(raiz):
    salida = []
    for d, carpetas, fs in os.walk(raiz):
        if '__pycache__' in carpetas:
            carpetas.remove('__pycache__')
        salida += [os.path.relpath(os.path.join(d, f), raiz).replace(os.sep, '/') for f in fs]
    return salida


def leer_manifiesto(raiz):
    ruta = os.path.join(raiz, MANIFIESTO)
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding='utf-8') as f:
        return dict(reversed(linea.rstrip('\n').split('  ', 1)) for linea in f if linea.strip())


def resumen(ruta):
    with open(ruta, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def motivo_para_conservar(raiz):
    """None si se puede borrar; si no, por qué no."""
    if os.path.islink(raiz) or not os.path.exists(os.path.join(raiz, 'venb', 'VERSION')):
        return 'no parece una versión de VenB'
    presentes = [f for f in ficheros(raiz) if f not in SE_IGNORA]
    propio = leer_manifiesto(raiz)
    if propio is None:  # versiones anteriores a 1.33: se admiten solo ficheros conocidos
        conocidos = leer_manifiesto(ACTUAL) or {}
        extra = [f for f in presentes if f not in conocidos and not f.startswith('datos_iniciales/')]
        return f'tiene ficheros no reconocidos, como {extra[0]}' if extra else None
    for f in presentes:
        if f not in propio:
            return f'tiene un fichero añadido: {f}'
        if resumen(os.path.join(raiz, f)) != propio[f]:
            return f'tiene un fichero modificado: {f}'
    return None


def en_marcha():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{rutas.puerto()}/acerca", timeout=2).close()
        return True
    except OSError:
        return False


def main():
    m = PATRON.match(os.path.basename(ACTUAL))
    if not m:
        return
    padre = os.path.dirname(ACTUAL)
    viejas = sorted(n for n in os.listdir(padre) if (x := PATRON.match(n)) and float(x[1]) < float(m[1]) and os.path.isdir(os.path.join(padre, n)))
    if not viejas:
        return
    if en_marcha():
        print('VenB está abierta: las versiones anteriores no se borran ahora. Ciérrala y repite el instalador.')
        return
    for n in viejas:
        raiz = os.path.join(padre, n)
        motivo = motivo_para_conservar(raiz)
        if motivo:
            print(f'Se conserva {n}: {motivo}.')
            continue
        try:
            shutil.rmtree(raiz)
            print(f'Versión anterior borrada: {n}.')
        except OSError as e:
            print(f'No se ha podido borrar {n}: {e}.')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    main()
