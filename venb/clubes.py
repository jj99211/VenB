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


def guardar(cid, nombre, web, texto, logos_nuevos=(), quitar=(), fondo_nuevos=False, fondo_quitar=(), fondo_restaurar=()):
    """Crea (cid None) o cambia un perfil. logos_nuevos: ficheros subidos (werkzeug); quitar: nombres de logos;
    fondo_nuevos: quitar el fondo liso a los que se suben ahora; fondo_quitar / fondo_restaurar: logos ya guardados
    a los que quitar el fondo o devolver el original. Devuelve (id, avisos)."""
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
    originales = {k: v for k, v in (c.get('originales') or {}).items() if k in logos} if c else {}
    for n in quitar:
        for x in (n, (c.get('originales') or {}).get(n) if c else None):
            if x and x == os.path.basename(x) and os.path.exists(os.path.join(d, x)):
                os.remove(os.path.join(d, x))
    avisos = []
    for n in fondo_quitar:
        if n in logos and n not in originales:
            if not _fondo_fuera(d, n, originales):
                avisos.append('Uno de los logotipos no tiene un fondo de color liso (o ya es transparente): se queda como estaba.')
    for n in fondo_restaurar:
        o = originales.pop(n, None)
        if o and os.path.exists(os.path.join(d, o)):
            os.replace(os.path.join(d, o), os.path.join(d, n))
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
        if fondo_nuevos and not _fondo_fuera(d, n, originales):
            avisos.append(f'{f.filename}: no tiene un fondo de color liso (o ya es transparente); se ha guardado tal cual.')
    datos = {'nombre': nombre, 'web': web, 'texto': (texto or '').strip()[:120], 'logos': logos, 'originales': originales}
    with open(os.path.join(d, 'club.json.tmp'), 'w', encoding='utf-8') as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=1)
    os.replace(os.path.join(d, 'club.json.tmp'), os.path.join(d, 'club.json'))
    for x in os.listdir(d):     # originales que ya no corresponden a ningún logo
        if x.startswith('original_') and x not in originales.values():
            os.remove(os.path.join(d, x))
    return cid, avisos


def _fondo_fuera(d, n, originales):
    """Quita el fondo liso del logo n (en la carpeta d) y guarda antes el original. False si no se puede."""
    from PIL import Image
    ruta = os.path.join(d, n)
    nuevo = quitar_fondo(Image.open(ruta).convert('RGBA'))
    if nuevo is None:
        return False
    o = 'original_' + n
    os.replace(ruta, os.path.join(d, o))
    nuevo.save(ruta, 'PNG', optimize=True)
    originales[n] = o
    return True


def quitar_fondo(im, tolerancia=28, suave=22):
    """Vuelve transparente el fondo de color uniforme de una imagen RGBA: el color de las esquinas, solo en la zona
    unida a los bordes (no borra el interior del mismo color), con el borde suavizado y sin halo de ese color.
    None si las esquinas no comparten color o la imagen ya tiene fondo transparente."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    a = np.asarray(im, dtype=np.float32)
    rgb, alfa = a[..., :3], a[..., 3]
    h, w = alfa.shape
    k = max(2, min(h, w) // 40)
    esquinas = [a[:k, :k], a[:k, -k:], a[-k:, :k], a[-k:, -k:]]
    if min(e[..., 3].mean() for e in esquinas) < 250:
        return None                                     # ya transparente (o casi)
    colores = np.array([np.median(e[..., :3].reshape(-1, 3), axis=0) for e in esquinas])
    fondo = np.median(colores, axis=0)
    if sum(np.linalg.norm(colores - fondo, axis=1) <= tolerancia) < 3:
        return None                                     # el fondo no es liso
    dist = np.linalg.norm(rgb - fondo, axis=2)
    cerca = dist <= tolerancia + suave
    etiquetas, _ = ndimage.label(cerca)
    borde = np.unique(np.concatenate([etiquetas[0], etiquetas[-1], etiquetas[:, 0], etiquetas[:, -1]]))
    zona = np.isin(etiquetas, borde[borde > 0])
    if not zona.any():
        return None
    # opacidad: 0 en el color del fondo, 1 a partir de tolerancia + suave
    op = np.clip((dist - tolerancia) / suave, 0, 1)
    nuevo_a = np.where(zona, op * alfa, alfa)
    # quita el tinte del fondo en los píxeles semitransparentes del borde: c = (c' - (1 - a)·fondo) / a
    p = np.where(zona, op, 1)[..., None]
    limpio = np.where(p > 0.02, (rgb - (1 - p) * fondo) / np.maximum(p, 0.02), rgb)
    sal = np.dstack([np.clip(limpio, 0, 255), nuevo_a]).astype(np.uint8)
    return Image.fromarray(sal, 'RGBA')


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
    # «club»: lo mismo por separado, para la cabecera de la página interactiva (club destacado; VenB, al pie)
    return {'texto': f'{propio} · {MARCA_VENB}', 'logo': ruta,
            'club': {'nombre': c['nombre'], 'web': c['web'],
                     'logos': [os.path.join(_carpeta(cid), n) for n in c['logos']]}}
