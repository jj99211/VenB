"""Nombres geográficos oficiales del IGN: Nomenclátor Geográfico Básico de España (NGBE), por WFS.

Solo cubre España. Corrige la posición de las sierras y los puertos de OpenStreetMap, que a menudo es
aproximada, y añade los que faltan. No sustituye a OSM: al NGBE le faltan sierras conocidas (la de Cabra)
y llama «alineación montañosa» a lomas y cerros pequeños. Los pueblos siguen saliendo de OSM, que distingue
pueblos de caseríos. Licencia CC BY 4.0 (© Instituto Geográfico Nacional de España).
Se consulta por celdas de medio grado, como Overpass, y cada celda se guarda en la caché.
"""
import difflib
import json
import math
import re
import sys
import time
import unicodedata

import requests

from . import CACHE as _CACHE

CACHE = _CACHE / "ngbe"
URL = "https://www.ign.es/wfs-inspire/ngbe"
AGENTE = {"User-Agent": "generador-mapas-bici/0.1 (uso personal)"}
TAM_CELDA = 0.5
TIPOS = ("Alineación montañosa", "Montaña", "Paso de montaña")
# Montañas que en realidad son sierras (el NGBE las clasifica a veces como «Montaña»)
_SIERRA = re.compile(r"^(Sierra|Sierras|Sierrecilla|Serra|Serralada|Cordillera|Macizo|Montes de|Montes del) ", re.I)
_PUERTO = re.compile(r"^(Puerto|Puertos|Collado|Port|Coll|Portillo|Alto del Puerto) ", re.I)


def _filtro(s, o):
    tipos = "".join(f"<fes:PropertyIsEqualTo><fes:ValueReference>gn:localType</fes:ValueReference>"
                    f"<fes:Literal>{t}</fes:Literal></fes:PropertyIsEqualTo>" for t in TIPOS)
    return ('<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" xmlns:gn="http://inspire.ec.europa.eu/schemas/gn/4.0" '
            'xmlns:gml="http://www.opengis.net/gml/3.2"><fes:And><fes:Or>' + tipos + '</fes:Or>'
            '<fes:BBOX><fes:ValueReference>gn:geometry</fes:ValueReference><gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">'
            f'<gml:lowerCorner>{s:.3f} {o:.3f}</gml:lowerCorner><gml:upperCorner>{s + TAM_CELDA:.3f} {o + TAM_CELDA:.3f}</gml:upperCorner>'
            '</gml:Envelope></fes:BBOX></fes:And></fes:Filter>')


def _texto(v, *ruta):
    for k in ruta:
        if not isinstance(v, dict):
            return None
        v = v.get(k)
    return v if isinstance(v, str) else None


def _celda(s, o):
    """Lugares de una celda: [{nombre, tipo, lat, lon}] (de la caché o del WFS)."""
    fichero = CACHE / f"{s:.1f}_{o:.1f}.json"
    if fichero.exists():
        return json.loads(fichero.read_text())
    ultimo = None
    for intento in range(4):
        try:
            r = requests.get(URL, params={"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                                          "TYPENAMES": "GN:NamedPlace", "OUTPUTFORMAT": "application/geo+json",
                                          "FILTER": _filtro(s, o)}, headers=AGENTE, timeout=180)
            if r.status_code == 200:
                lugares = []
                for f in r.json().get("features", []):
                    p, g = f.get("properties") or {}, f.get("geometry") or {}
                    nombre = _texto(p, "name", "GeographicalName", "spelling", "SpellingOfName", "text")
                    tipo = _texto(p, "localType", "LocalisedCharacterString", "value")
                    if nombre and tipo and g.get("type") == "Point":
                        lugares.append({"nombre": nombre, "tipo": tipo, "lon": g["coordinates"][0], "lat": g["coordinates"][1]})
                CACHE.mkdir(parents=True, exist_ok=True)
                fichero.write_text(json.dumps(lugares, ensure_ascii=False))
                return lugares
            ultimo = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            ultimo = e
        time.sleep(3 * (intento + 1))
    raise RuntimeError(f"el Nomenclátor del IGN no responde: {ultimo}")


def lugares(celdas):
    vistos, res = set(), []
    for n, (s, o) in enumerate(celdas, 1):
        print(f"\r  IGN (Nomenclátor): celda {n}/{len(celdas)}", end="", file=sys.stderr, flush=True)
        for l in _celda(s, o):
            clave = (l["nombre"], l["tipo"], round(l["lat"], 5), round(l["lon"], 5))
            if clave not in vistos:
                vistos.add(clave)
                res.append(l)
    print(file=sys.stderr)
    return res


def clasificar(lista):
    """Separa los lugares en sierras (todas las alineaciones y las montañas con nombre de sierra) y puertos."""
    sierras, puertos = [], []
    for l in lista:
        t, nombre = l["tipo"], l["nombre"]
        item = {"nombre": nombre, "lat": l["lat"], "lon": l["lon"], "ele": None}
        if t == "Alineación montañosa" or (t == "Montaña" and _SIERRA.match(nombre)):
            sierras.append(item)
        elif t == "Paso de montaña" or (t == "Montaña" and _PUERTO.match(nombre)):
            puertos.append(item)
    return sierras, puertos


def _clave(nombre):
    n = unicodedata.normalize("NFD", nombre.lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return re.sub(r"\b(de|del|la|las|los|el|o)\b|[^a-z0-9]", "", n)


def _km(a, b):
    return math.hypot((a["lat"] - b["lat"]) * 111, (a["lon"] - b["lon"]) * 111 * math.cos(math.radians(a["lat"])))


def combinar(de_osm, de_ign, todos_ign=False):
    """Une las listas de OSM y del IGN.

    Si un nombre está en las dos (igual y a menos de 15 km, o casi igual y a menos de 4 km), se queda el del IGN, con su
    nombre y su posición, y la altitud de OSM si la tiene. Del IGN se añaden además los que no están en
    OSM, solo los de nombre de sierra (o todos, con `todos_ign`: puertos junto al track).
    """
    res, usados = [], set()
    for o in de_osm:
        ko = _clave(o["nombre"])
        par = min((i for i in de_ign if id(i) not in usados and ((_clave(i["nombre"]) == ko and _km(o, i) < 15) or
                   (_km(o, i) < 4 and difflib.SequenceMatcher(None, _clave(i["nombre"]), ko).ratio() > 0.85))),
                  key=lambda i: _km(o, i), default=None)
        if par is None:
            res.append(o)
        else:
            usados.add(id(par))
            res.append({**par, "ele": o.get("ele") or par.get("ele")})
    vistos = {_clave(x["nombre"]) for x in res}
    for i in de_ign:
        if id(i) not in usados and _clave(i["nombre"]) not in vistos and (todos_ign or _SIERRA.match(i["nombre"])):
            res.append(i)
            vistos.add(_clave(i["nombre"]))
    return res
