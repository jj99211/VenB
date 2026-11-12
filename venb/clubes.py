"""Perfiles de club u organizador (solo VenB Rutas): nombre, web, texto de la marca y uno o varios logotipos.

Al generar los documentos de una ruta se elige el club, y su marca va en mapas, infografías y página interactiva.
La marca de VenB (logotipo pequeño y vivirenbici.es) va siempre al lado: no se puede quitar.
Cada perfil vive en VenB-datos/planificador/clubes/<id>/ (club.json y los logotipos).
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0.
"""
import json
import os
import re
import secrets
import shutil
import unicodedata

import rutas

DIR = os.path.join(rutas.PERSISTE, 'planificador', 'clubes')
AQUI = os.path.dirname(os.path.abspath(__file__))
LOGO_VENB = os.path.join(AQUI, 'generador', 'recursos', 'logo_marca.png')
MARCA_VENB = 'VenB: vivirenbici.es'
EXT_LOGO = ('.png', '.jpg', '.jpeg', '.webp')
MAX_LOGOS = 4


class ErrorClub(Exception):
    pass


def _carpeta(cid):
    if not re.fullmatch(r'[a-z0-9-]{1,40}', cid or ''):
        raise KeyError(cid)
    return os.path.join(DIR, cid)


def club(cid):
    try:
        with open(os.path.join(_carpeta(cid), 'club.json'), encoding='utf-8') as f:
            c = json.load(f)
    except (OSError, ValueError, KeyError):
        return None
    c['id'] = cid
    c['logos'] = [n for n in c.get('logos', []) if os.path.exists(os.path.join(_carpeta(cid), n))]
    return c


def lista():
    if not os.path.isdir(DIR):
        return []
    return sorted((c for c in (club(n) for n in os.listdir(DIR)) if c), key=lambda c: c['nombre'].lower())


def ruta_logo(cid, nombre):
    if nombre != os.path.basename(nombre):
        raise KeyError(nombre)
    ruta = os.path.join(_carpeta(cid), nombre)
    if not os.path.exists(ruta):
        raise KeyError(nombre)
    return ruta


def _id_nuevo(nombre):
    base = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode().lower()
    base = re.sub(r'[^a-z0-9]+', '-', base).strip('-')[:30] or 'club'
    return f'{base}-{secrets.token_hex(2)}'


def guardar(cid, nombre, web, texto, logos_nuevos=(), quitar=()):
    """Crea (cid None) o cambia un perfil. logos_nuevos: ficheros subidos (werkzeug); quitar: nombres de logos.
    Devuelve el id."""
    from PIL import Image
    nombre = (nombre or '').strip()[:80]
    if not nombre:
        raise ErrorClub('Escribe el nombre del club u organizador.')
    web = (web or '').strip()[:200]
    if web and not re.match(r'https?://', web):
        web = 'https://' + web
    c = club(cid) if cid else None
    if cid and not c:
        raise KeyError(cid)
    cid = cid or _id_nuevo(nombre)
    d = _carpeta(cid)
    os.makedirs(d, exist_ok=True)
    logos = [n for n in (c['logos'] if c else []) if n not in quitar]
    for n in quitar:
        if n == os.path.basename(n) and os.path.exists(os.path.join(d, n)):
            os.remove(os.path.join(d, n))
    for f in logos_nuevos:
        if not f or not f.filename:
            continue
        if os.path.splitext(f.filename)[1].lower() not in EXT_LOGO:
            raise ErrorClub('Los logotipos deben ser PNG, JPG o WEBP (mejor PNG con fondo transparente).')
        if len(logos) >= MAX_LOGOS:
            raise ErrorClub(f'Como mucho {MAX_LOGOS} logotipos por club.')
        try:
            im = Image.open(f.stream)
            im.load()
        except Exception:
            raise ErrorClub(f'No se puede leer la imagen {f.filename}.')
        n = f'logo_{secrets.token_hex(3)}.png'
        im.convert('RGBA').save(os.path.join(d, n), 'PNG', optimize=True)
        logos.append(n)
    datos = {'nombre': nombre, 'web': web, 'texto': (texto or '').strip()[:120], 'logos': logos}
    with open(os.path.join(d, 'club.json.tmp'), 'w', encoding='utf-8') as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=1)
    os.replace(os.path.join(d, 'club.json.tmp'), os.path.join(d, 'club.json'))
    return cid


def borrar(cid):
    d = _carpeta(cid)
    if os.path.isdir(d):
        shutil.rmtree(d)


def _recortar(im):
    caja = im.getchannel('A').point(lambda a: 255 if a > 20 else 0).getbbox()
    return im.crop(caja) if caja else im


def marca(cid):
    """Sección [marca] del generador para un club: logotipos del club seguidos, siempre, del de VenB (más pequeño),
    en una sola imagen, y el texto «Club - web · VenB: vivirenbici.es». None si el club no existe."""
    from PIL import Image, ImageDraw
    c = club(cid)
    if not c:
        return None
    alto = 400
    piezas = []
    for n in c['logos']:
        im = _recortar(Image.open(os.path.join(_carpeta(cid), n)).convert('RGBA'))
        piezas.append(im.resize((max(1, round(im.width * alto / im.height)), alto), Image.LANCZOS))
    venb = _recortar(Image.open(LOGO_VENB).convert('RGBA'))
    alto_v = alto // 2 if piezas else alto
    venb = venb.resize((max(1, round(venb.width * alto_v / venb.height)), alto_v), Image.LANCZOS)
    hueco = 50
    ancho = sum(p.width for p in piezas) + hueco * len(piezas) + (6 + hueco if piezas else 0) + venb.width
    lienzo = Image.new('RGBA', (ancho, alto), (0, 0, 0, 0))
    x = 0
    for p in piezas:
        lienzo.alpha_composite(p, (x, 0))
        x += p.width + hueco
    if piezas:      # línea fina entre la marca del club y la de VenB
        ImageDraw.Draw(lienzo).rectangle([x, alto // 4, x + 5, alto - 1], fill=(150, 150, 150, 200))
        x += 6 + hueco
    lienzo.alpha_composite(venb, (x, alto - alto_v))
    ruta = os.path.join(_carpeta(cid), 'marca_compuesta.png')
    lienzo.save(ruta, 'PNG', optimize=True)
    propio = c['texto'] or ' - '.join(t for t in (c['nombre'], c['web'].removeprefix('https://').removeprefix('http://')) if t)
    return {'texto': f'{propio} · {MARCA_VENB}', 'logo': ruta}
