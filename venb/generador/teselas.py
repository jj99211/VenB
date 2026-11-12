"""Mapa base a partir de teselas de OpenStreetMap (con caché) y proyección Web Mercator."""
import io
import math
import sys
import time
from pathlib import Path

import numpy as np

from . import CACHE as _CACHE
import requests
from PIL import Image

CACHE = _CACHE / "teselas"
AGENTE = {"User-Agent": "generador-mapas-bici/0.1 (uso personal; infografias de rutas)"}
R = 6378137.0

ESTILOS = {
    # nombre: (url, tamaño de tesela, zoom máximo, atribución)
    "topo": ("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", 256, 17,
             "Mapa: © OpenStreetMap contributors, SRTM | Estilo: © OpenTopoMap (CC-BY-SA)"),
    "osm": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", 256, 19,
            "© OpenStreetMap contributors"),
    "hot": ("https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", 256, 19,
            "© OpenStreetMap contributors, estilo Humanitarian (HOT)"),
    # altitudes codificadas en RGB (Terrarium): altitud = R*256 + G + B/256 - 32768
    # IGN (CC BY 4.0). Teselas TMS: {ty} es la fila contada desde el sur. Solo cubren España.
    # Una lista de direcciones son capas que se superponen (ortofoto + rótulos).
    "ign_mtn": ("https://tms-mapa-raster.ign.es/1.0.0/mapa-raster/{z}/{x}/{ty}.jpeg", 256, 17,
                "Mapa: MTN, © Instituto Geográfico Nacional de España (CC BY 4.0, scne.es)"),
    "ign_base": ("https://tms-ign-base.idee.es/1.0.0/IGNBaseTodo/{z}/{x}/{ty}.jpeg", 256, 17,
                 "Mapa: IGN Base, © Instituto Geográfico Nacional de España (CC BY 4.0, scne.es)"),
    "ign_orto": (["https://tms-pnoa-ma.idee.es/1.0.0/pnoa-ma/{z}/{x}/{ty}.jpeg",
                  "https://tms-ign-base.idee.es/1.0.0/IGNBaseOrto/{z}/{x}/{ty}.png"], 256, 17,
                 "Ortofoto PNOA y rótulos: © Instituto Geográfico Nacional de España (CC BY 4.0, scne.es)"),
    "terreno": ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png", 256, 15,
                "Relieve: Terrarium (Mapzen, AWS Open Data)"),
}


def a_mercator(lon, lat):
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    x = R * np.radians(lon)
    y = R * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    return x, y


def desde_mercator(x, y):
    lon = np.degrees(np.asarray(x) / R)
    lat = np.degrees(2 * np.arctan(np.exp(np.asarray(y) / R)) - np.pi / 2)
    return lon, lat


def _descargar(url, estilo, z, x, y):
    sub = "abc"[(x + y) % 3]
    for intento in range(4):
        try:
            r = requests.get(url.format(s=sub, z=z, x=x, y=y, ty=2 ** z - 1 - y), headers=AGENTE, timeout=30)
            if r.status_code == 200:
                return Image.open(io.BytesIO(r.content)).convert("RGBA")
            if r.status_code in (400, 403, 404):
                break
        except requests.RequestException:
            pass
        time.sleep(1.5 * (intento + 1))
    raise RuntimeError(f"No se pudo descargar la tesela {estilo} {z}/{x}/{y}")


def _tesela(estilo, z, x, y):
    url, *_ = ESTILOS[estilo]
    fichero = CACHE / estilo / str(z) / str(x) / f"{y}.png"
    if fichero.exists():
        return Image.open(fichero).convert("RGB")
    fichero.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (ESTILOS[estilo][1],) * 2, "white")
    for u in (url if isinstance(url, list) else [url]):
        capa = _descargar(u, estilo, z, x, y)
        img.alpha_composite(capa.resize(img.size) if capa.size != img.size else capa)
    img = img.convert("RGB")
    img.save(fichero)
    return img


def _vacia(img):
    """Tesela sin datos (el IGN devuelve blanco fuera de España)."""
    return img.convert("L").getextrema()[0] >= 250


def cubre(estilo, z, xs, ys):
    """¿Tiene datos el estilo en todas las teselas por las que pasa el track (metros Mercator)?"""
    # La ortofoto tiene imagen de baja resolución fuera de España: manda la cobertura de los rótulos (IGN Base)
    estilo = {"ign_orto": "ign_base"}.get(estilo, estilo)
    n, mundo = 2 ** z, 2 * math.pi * R
    tx = np.floor((np.asarray(xs) + mundo / 2) / mundo * n).astype(int)
    ty = np.floor((mundo / 2 - np.asarray(ys)) / mundo * n).astype(int)
    try:
        return not any(_vacia(_tesela(estilo, z, int(a) % n, int(b))) for a, b in sorted(set(zip(tx, ty))))
    except RuntimeError:
        return False


def zoom_para(xmin, xmax, ancho_px, estilo):
    """Zoom con el que el ancho del mapa ocupa aproximadamente `ancho_px`."""
    _, tam, zmax, _ = ESTILOS[estilo]
    metros_por_px_0 = 2 * math.pi * R / tam
    z = math.log2(metros_por_px_0 * ancho_px / (xmax - xmin))
    return int(min(zmax, max(1, round(z))))


def mapa_base(xmin, ymin, xmax, ymax, z, estilo="topo"):
    """Compone las teselas que cubren el rectángulo (en metros Mercator).

    Devuelve la imagen recortada exactamente a ese rectángulo.
    """
    _, tam, _, _ = ESTILOS[estilo]
    n = 2 ** z
    mundo = 2 * math.pi * R

    def tx(x):
        return (x + mundo / 2) / mundo * n

    def ty(y):
        return (mundo / 2 - y) / mundo * n

    x0, x1 = tx(xmin), tx(xmax)
    y0, y1 = ty(ymax), ty(ymin)
    ix0, ix1, iy0, iy1 = int(math.floor(x0)), int(math.floor(x1)), int(math.floor(y0)), int(math.floor(y1))
    total = (ix1 - ix0 + 1) * (iy1 - iy0 + 1)
    lienzo = Image.new("RGB", ((ix1 - ix0 + 1) * tam, (iy1 - iy0 + 1) * tam), "white")
    hechas = 0
    for ix in range(ix0, ix1 + 1):
        for iy in range(iy0, iy1 + 1):
            lienzo.paste(_tesela(estilo, z, ix % n, iy), ((ix - ix0) * tam, (iy - iy0) * tam))
            hechas += 1
            print(f"\r  teselas {estilo} z{z}: {hechas}/{total}", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    caja = tuple(int(round(v)) for v in ((x0 - ix0) * tam, (y0 - iy0) * tam,
                                         (x1 - ix0) * tam, (y1 - iy0) * tam))
    return lienzo.crop(caja)
