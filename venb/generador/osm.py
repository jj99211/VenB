"""Elementos geográficos de OpenStreetMap (vía Overpass) alrededor del track, con caché."""
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import CACHE as _CACHE
from . import ngbe
import requests

CACHE = _CACHE / "overpass"
SERVIDORES = ["https://overpass-api.de/api/interpreter",
              "https://overpass.kumi.systems/api/interpreter",
              "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
AGENTE = {"User-Agent": "generador-mapas-bici/0.1 (uso personal)"}


def _consulta(q):
    clave = hashlib.sha1(q.encode()).hexdigest()[:16]
    fichero = CACHE / f"{clave}.json"
    if fichero.exists():
        return json.loads(fichero.read_text())
    CACHE.mkdir(parents=True, exist_ok=True)
    ultimo = None
    for intento in range(6):
        url = SERVIDORES[intento % len(SERVIDORES)]
        try:
            r = requests.post(url, data={"data": q}, headers=AGENTE, timeout=240)
            if r.status_code == 200:
                datos = r.json()
                fichero.write_text(json.dumps(datos))
                return datos
            ultimo = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            ultimo = e
        time.sleep(5 * (intento + 1))
    raise RuntimeError(f"Overpass no responde: {ultimo}")


# --------------------------------------------------------------- consultas por celdas
# El filtro `around` con una polilínea larga devuelve a veces vacío sin dar error (según el
# servidor). Por eso se consulta por rectángulos: la zona del track se divide en celdas de
# TAM_CELDA grados y la distancia al track se filtra después, en local.

TAM_CELDA = 0.5


def _celdas(track, radio_km):
    """Celdas (sur, oeste) que quedan a menos de `radio_km` del track."""
    paso = max(1, len(track.lat) // 4000)
    lat, lon = track.lat[::paso], track.lon[::paso]
    margen_lat = radio_km / 111
    margen_lon = radio_km / (111 * np.cos(np.radians(lat.mean())))
    celdas = set()
    for dla in (-margen_lat, 0, margen_lat):
        for dlo in (-margen_lon, 0, margen_lon):
            for a, b in zip(np.floor((lat + dla) / TAM_CELDA), np.floor((lon + dlo) / TAM_CELDA)):
                celdas.add((a * TAM_CELDA, b * TAM_CELDA))
    return sorted(celdas)


def _por_celdas(filtro, celdas, salida="out center qt;"):
    """Lanza `filtro` (con {caja}) en cada celda y junta los elementos sin repetir."""
    vistos, elementos = set(), []
    for n, (s, o) in enumerate(celdas, 1):
        caja = f"{s:.3f},{o:.3f},{s + TAM_CELDA:.3f},{o + TAM_CELDA:.3f}"
        print(f"\r  OpenStreetMap: celda {n}/{len(celdas)}", end="", file=sys.stderr, flush=True)
        for el in _consulta(f"[out:json][timeout:180];{filtro.format(caja=caja)}{salida}").get("elements", []):
            clave = (el["type"], el["id"])
            if clave not in vistos:
                vistos.add(clave)
                elementos.append(el)
    print(file=sys.stderr)
    return elementos


class _Cercania:
    """Distancia (km) de un punto al track, en una rejilla local aproximada."""

    def __init__(self, track):
        paso = max(1, len(track.lat) // 6000)
        self.lat0 = float(track.lat.mean())
        self.k = np.cos(np.radians(self.lat0))
        self.x = track.lon[::paso] * 111 * self.k
        self.y = track.lat[::paso] * 111

    def km(self, lat, lon):
        return float(np.min(np.hypot(self.x - lon * 111 * self.k, self.y - lat * 111)))


def _centro(el):
    if "lat" in el:
        return el["lat"], el["lon"]
    if "center" in el:
        return el["center"]["lat"], el["center"]["lon"]
    return None


def _en_espana(track):
    """¿Pasa todo el track por España? (las teselas del IGN salen en blanco fuera)."""
    try:
        from .teselas import a_mercator, cubre
        return cubre("ign_mtn", 11, *a_mercator(track.lon, track.lat))
    except Exception:
        return False


def elementos(track, bbox, radio_rios_km=15, radio_cimas_km=20, radio_embalses_km=15, radio_sierras_km=25):
    """Descarga ríos, sierras, cimas, puertos, embalses, regiones, comarcas y pueblos cercanos (con castillo o no).

    En España se cruzan las sierras y los puertos con el Nomenclátor del IGN: la posición oficial manda
    cuando el nombre está en los dos, y se añade lo que solo tiene el IGN (sierras con nombre de sierra y
    puertos junto al track). Fuera de España, o si el IGN no responde, todo sale de OpenStreetMap. bbox: (sur, oeste, norte, este) del mapa.
    Devuelve un diccionario con listas; "fuente_nombres" es "ign" u "osm".
    """
    s, o, n, e = bbox
    caja = f"{s:.4f},{o:.4f},{n:.4f},{e:.4f}"
    print("  consultando OpenStreetMap (Overpass)…", file=sys.stderr)
    cerca = _Cercania(track)
    celdas_anchas = _celdas(track, max(radio_rios_km, radio_cimas_km, radio_embalses_km))
    celdas_ruta = _celdas(track, 1)

    # ríos: tramos con geometría, agrupados por nombre; se quedan los que pasan cerca
    rios = defaultdict(list)
    for el in _por_celdas('way["waterway"="river"]["name"]({caja});', celdas_anchas, "out geom qt;"):
        geo = el.get("geometry")
        if not geo:
            continue
        puntos = [(p["lat"], p["lon"]) for p in geo]
        muestra = puntos[::max(1, len(puntos) // 20)] + [puntos[-1]]
        if min(cerca.km(a, b) for a, b in muestra) <= radio_rios_km:
            rios[el["tags"]["name"]].append(puntos)

    res = {"rios": dict(rios), "sierras": [], "cimas": [], "puertos": [], "regiones": [],
           "embalses": [], "comarcas": comarcas(bbox), "pueblos": [], "fuente_nombres": "osm"}
    ign = None
    if _en_espana(track):
        try:
            ign = ngbe.clasificar(ngbe.lugares(_celdas(track, radio_sierras_km)))
            res["fuente_nombres"] = "ign"
        except RuntimeError as ex:
            print(f"  aviso: {ex}; se usan los nombres de OpenStreetMap", file=sys.stderr)

    for el in _por_celdas('node["natural"="peak"]["name"]["ele"]({caja});', celdas_anchas):
        c = _centro(el)
        if c and cerca.km(*c) <= radio_cimas_km:
            res["cimas"].append(_item(el, c))
    for el in _por_celdas('(node["mountain_pass"="yes"]["name"]({caja});'
                          'node["natural"="saddle"]["name"]({caja}););', celdas_ruta):
        c = _centro(el)
        if c and cerca.km(*c) <= 0.2:
            res["puertos"].append(_item(el, c))
    if ign:
        res["puertos"] = ngbe.combinar(res["puertos"], [p for p in ign[1] if cerca.km(p["lat"], p["lon"]) <= 0.2], True)
    for el in _por_celdas('(way["natural"="water"]["name"]["water"~"^(reservoir|lake)$"]({caja});'
                          'rel["natural"="water"]["name"]["water"~"^(reservoir|lake)$"]({caja}););',
                          celdas_anchas, "out tags center bb qt;"):
        b = el.get("bounds")
        if not b:
            continue
        # con «bb» Overpass da el recuadro pero no el centro: se calcula de él
        c = el.get("center") or {"lat": (b["minlat"] + b["maxlat"]) / 2,
                                 "lon": (b["minlon"] + b["maxlon"]) / 2}
        if cerca.km(c["lat"], c["lon"]) > radio_embalses_km:
            continue
        alto = (b["maxlat"] - b["minlat"]) * 111
        ancho = (b["maxlon"] - b["minlon"]) * 111 * np.cos(np.radians(c["lat"]))
        res["embalses"].append({"nombre": el["tags"]["name"], "lat": c["lat"], "lon": c["lon"],
                                "tam_km": float(np.hypot(alto, ancho))})

    # pueblos cerca de la ruta (para dibujarlos) y castillos (el pueblo que tiene uno lo lleva en su dibujo)
    castillos = [_centro(el) for el in _por_celdas('nwr["historic"="castle"]({caja});', celdas_ruta)]
    castillos = [c for c in castillos if c]
    for el in _por_celdas('node["place"~"^(town|village)$"]["name"]({caja});', celdas_ruta):
        c = _centro(el)
        d = cerca.km(*c)
        if d > 12:
            continue
        k = np.cos(np.radians(c[0]))
        castillo = any(np.hypot((a - c[0]) * 111, (b - c[1]) * 111 * k) < 1.5 for a, b in castillos)
        res["pueblos"].append({**_item(el, c), "tipo": el["tags"]["place"], "castillo": castillo, "km_ruta": d})

    # sierras y regiones: pocas y repartidas, basta una consulta al encuadre
    for filtro, clave in (('nwr["natural"="mountain_range"]["name"]', "sierras"),
                          ('node["place"~"^(state|province|region)$"]["name"]', "regiones")):
        for el in _consulta(f"[out:json][timeout:200];{filtro}({caja});out center qt;").get("elements", []):
            c = _centro(el)
            if c:
                item = _item(el, c)
                if clave == "regiones":
                    item["tipo"] = el["tags"]["place"]
                res[clave].append(item)
    if ign:
        s_, o_, n_, e_ = bbox
        res["sierras"] = ngbe.combinar(res["sierras"], [x for x in ign[0] if s_ < x["lat"] < n_ and o_ < x["lon"] < e_])
    return res


def _item(el, centro):
    t = el.get("tags", {})
    return {"nombre": t.get("name:es") or t["name"], "lat": centro[0], "lon": centro[1],
            "ele": _num(t.get("ele"))}


def comarcas(bbox):
    """Comarcas de España con coordenadas (Wikidata, Q1345234) dentro del encuadre.

    En OpenStreetMap apenas están cartografiadas; Wikidata tiene un punto por comarca.
    """
    fichero = CACHE / "comarcas_wikidata.json"
    if fichero.exists():
        filas = json.loads(fichero.read_text())
    else:
        q = """SELECT ?c ?cLabel ?coord WHERE { ?c wdt:P31 wd:Q1345234 ; wdt:P625 ?coord .
               SERVICE wikibase:label { bd:serviceParam wikibase:language "es". } }"""
        try:
            r = requests.post("https://query.wikidata.org/sparql", data={"query": q},
                              headers={**AGENTE, "Accept": "application/sparql-results+json"},
                              timeout=120)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  aviso: sin comarcas de Wikidata ({e})", file=sys.stderr)
            return []
        filas = []
        for b in r.json()["results"]["bindings"]:
            m = re.findall(r"[-\d.]+", b["coord"]["value"])
            if len(m) >= 2:
                filas.append({"nombre": b["cLabel"]["value"], "lon": float(m[0]), "lat": float(m[1])})
        CACHE.mkdir(parents=True, exist_ok=True)
        fichero.write_text(json.dumps(filas, ensure_ascii=False))
    s, o, n, e = bbox
    salida = []
    for f in filas:
        if s < f["lat"] < n and o < f["lon"] < e:
            nombre = re.sub(r"^[Cc]omarca (de la |del |de los |de las |de )", "", f["nombre"])
            if not nombre.lower().startswith(("área metropolitana", "q")):
                salida.append({**f, "nombre": nombre})
    return salida


def _num(v):
    try:
        return float(str(v).replace(",", ".").split()[0])
    except (TypeError, ValueError, IndexError):
        return None
