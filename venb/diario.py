"""Diario de VenB: notas libres y opcionales, una por entrada. Se guarda en VenB-datos/datos/diario.csv.
También se puede anotar desde la terminal:
  python venb/diario.py nuevo --texto "Cómo ha ido" [--fecha DD/MM/AAAA]
  python venb/diario.py lista
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import argparse
import csv
import os
import sys
import uuid
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import rutas  # noqa: E402

RUTA = os.path.join(rutas.DATOS, 'diario.csv')
CAMPOS = ['id', 'fecha', 'texto']


def todas():
    """Notas de la más reciente a la más antigua; dentro de un mismo día, la última escrita primero."""
    if not os.path.exists(RUTA):
        return []
    with open(RUTA, newline='', encoding='utf-8') as f:
        filas = list(csv.DictReader(f))
    return sorted(reversed(filas), key=lambda n: n['fecha'], reverse=True)


def _guardar(filas):
    os.makedirs(rutas.DATOS, exist_ok=True)
    tmp = RUTA + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        e = csv.DictWriter(f, CAMPOS)
        e.writeheader()
        e.writerows(sorted(filas, key=lambda n: n['fecha']))
    os.replace(tmp, RUTA)


def anotar(fecha_iso, texto, nid=None):
    """Crea una nota o, con nid, modifica esa."""
    filas = list(reversed(todas()))
    if nid:
        if not any(n['id'] == nid for n in filas):
            raise KeyError(nid)
        filas = [{'id': nid, 'fecha': fecha_iso, 'texto': texto} if n['id'] == nid else n for n in filas]
    else:
        filas.append({'id': uuid.uuid4().hex, 'fecha': fecha_iso, 'texto': texto})
    _guardar(filas)


def borrar(nid):
    _guardar([n for n in reversed(todas()) if n['id'] != nid])


def _cli():
    p = argparse.ArgumentParser(description='Diario de VenB')
    s = p.add_subparsers(dest='orden', required=True)
    n = s.add_parser('nuevo')
    n.add_argument('--texto', required=True)
    n.add_argument('--fecha', help='DD/MM/AAAA; hoy si no se indica')
    s.add_parser('lista')
    a = p.parse_args()
    if a.orden == 'nuevo':
        f = datetime.strptime(a.fecha, '%d/%m/%Y').date() if a.fecha else date.today()
        anotar(f.isoformat(), a.texto.strip())
        print('Anotado.')
    else:
        for x in todas():
            print(f"{datetime.strptime(x['fecha'], '%Y-%m-%d'):%d/%m/%Y}\n{x['texto']}\n")


if __name__ == '__main__':
    _cli()
