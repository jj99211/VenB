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
from . import guardar as _guardar
from . import ngbe
import requests

CACHE = _CACHE / "overpass"
SERVIDORES = ["https://overpass-api.de/api/interpreter",
              "https://overpass.kumi.systems/api/interpreter",
              "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
AGENTE = {"User-Agent": "generador-mapas-bici/0.1 (uso personal)"}


def _fichero(q):
    return CACHE / f"{hashlib.sha1(q.encode()).hexdigest()[:16]}.json"


# consultas que ya fallaron en esta generación (en la descarga conjunta por zonas): no se repiten
_sin_red = {}


def _consulta(q, guardar=True, intentos=6):
    fichero = _fichero(q)
    if fichero.exists():
        return json.loads(fichero.read_text())
    if q in _sin_red:
        raise RuntimeError(_sin_red[q])
    CACHE.mkdir(parents=True, exist_ok=True)
    ultimo = None
    for intento in range(intentos):
        url = SERVIDORES[intento % len(SERVIDORES)]
        try:
            r = requests.post(url, data={"data": q}, headers=AGENTE, timeout=240)
            if r.status_code == 200:
                datos = r.json()
                aviso = str(datos.get("remark", ""))
                if "error" in aviso.lower() or "timed out" in aviso.lower():
                    # el servidor cortó la consulta (tiempo o memoria): la respuesta está incompleta, no se guarda
                    raise ValueError(f"respuesta incompleta ({aviso.strip()[:80]})")
                if guardar:
                    _guardar(fichero, json.dumps(datos))
                return datos
            ultimo = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            ultimo = e
        if intento < intentos - 1:
            time.sleep(min(60, 5 * 2 ** intento))     # el servidor pide doblar la espera en cada reintento
    raise RuntimeError(f"Overpass no responde: {ultimo}")


def probar_servidor(tiempo_max=45):
    """Consulta mínima a Overpass (sin caché) para saber si el servidor está cargado antes de generar.
    Devuelve {"estado": "bien"|"lento"|"saturado", "segundos": s, "texto": explicación}."""
    q = '[out:json][timeout:25];node["place"="city"]["name"="Madrid"](40.3,-3.8,40.5,-3.6);out ids;'
    t0 = time.time()
    try:
        r = requests.post(SERVIDORES[0], data={"data": q}, headers=AGENTE, timeout=tiempo_max)
        seg = time.time() - t0
        if r.status_code != 200:
            return {"estado": "saturado", "segundos": round(seg, 1),
                    "texto": f"El servidor de OpenStreetMap no atiende ahora (HTTP {r.status_code}). Mejor genera en otro momento."}
    except requests.RequestException:
        return {"estado": "saturado", "segundos": round(time.time() - t0, 1),
                "texto": f"El servidor de OpenStreetMap no respondió en {tiempo_max} s (o no hay conexión). Mejor genera en otro momento."}
    if seg <= 6:
        return {"estado": "bien", "segundos": round(seg, 1),
                "texto": f"El servidor de OpenStreetMap responde bien ({seg:.0f} s en una consulta mínima)."}
    if seg <= 20:
        return {"estado": "lento", "segundos": round(seg, 1),
                "texto": f"El servidor de OpenStreetMap va lento ({seg:.0f} s en una consulta mínima): en una zona nueva, "
                         "la descarga puede tardar bastante más de lo normal."}
    return {"estado": "saturado", "segundos": round(seg, 1),
            "texto": f"El servidor de OpenStreetMap está saturado ({seg:.0f} s en una consulta mínima): en una zona nueva, "
                     "mejor genera en otro momento (a primera hora de la mañana suele ir mejor)."}


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


# filtros de cada parte (filtro con {caja}, salida): su texto es la clave de la caché, no cambiarlo sin motivo
F_RIOS = ('way["waterway"="river"]["name"]({caja});',
          'out geom qt;')
F_CIMAS = ('node["natural"="peak"]["name"]["ele"]({caja});',
           'out center qt;')
F_PUERTOS = ('(node["mountain_pass"="yes"]["name"]({caja});node["natural"="saddle"]["name"]({caja}););',
             'out center qt;')
F_EMBALSES = ('(way["natural"="water"]["name"]["water"~"^(reservoir|lake)$"]({caja});rel["natural"="water"]["name"]["water"~"^(reservoir|lake)$"]({caja}););',
              'out tags center bb qt;')
F_CASTILLOS = ('nwr["historic"="castle"]({caja});',
               'out center qt;')
F_PUEBLOS = ('node["place"~"^(town|village)$"]["name"]({caja});',
             'out center qt;')
F_CASCOS = ('(way["landuse"="residential"]({caja});rel["landuse"="residential"]({caja}););',
            'out center bb qt;')
F_ALDEAS = ('node["place"="hamlet"]["name"]({caja});',
            'out center qt;')
F_SERVICIOS = ('(node["amenity"~"^(drinking_water|cafe|bar|restaurant|fast_food|fuel)$"]({caja});way["amenity"="fuel"]({caja});node["shop"~"^(supermarket|convenience|bakery)$"]({caja});way["shop"="supermarket"]({caja});node["man_made"="water_tap"]({caja});node["natural"="spring"]["drinking_water"="yes"]({caja}););',
               'out center qt;')


def _caja(celda):
    s, o = celda
    return f"{s:.3f},{o:.3f},{s + TAM_CELDA:.3f},{o + TAM_CELDA:.3f}"


def _q(filtro, celda, salida="out center qt;"):
    """Consulta de una parte en una celda (su texto es la clave de la caché)."""
    return f"[out:json][timeout:180];{filtro.format(caja=_caja(celda))}{salida}"


def _minutos(seg):
    m = round(seg / 60)
    return "menos de un minuto" if m < 1 else "1 min" if m == 1 else f"{m} min" if m < 90 else f"{m / 60:.1f} h".replace(".", ",")


def _descargar_zonas(trabajos):
    """Descarga de una vez, por celdas, todas las partes que faltan en la caché.

    trabajos: lista de (celdas, [(filtro, salida), …]). Por cada celda con algo pendiente se hace UNA consulta
    a Overpass con todas sus partes, separadas por un elemento «fin» (make), y la respuesta se reparte en la
    caché como si cada parte se hubiera pedido por separado: así se aprovecha lo ya guardado y se hacen ~8 veces
    menos peticiones. Si dos zonas seguidas fallan, el servidor está saturado: no se insiste con las demás
    (sus partes quedan en _sin_red y cada parte lo anota en «fallos»). Imprime el progreso con lo que queda."""
    pendientes = defaultdict(list)
    for celdas, partes in trabajos:
        for c in celdas:
            for filtro, salida in partes:
                q = _q(filtro, c, salida)
                if not _fichero(q).exists() and (filtro, salida, q) not in pendientes[c]:
                    pendientes[c].append((filtro, salida, q))
    pendientes = {c: v for c, v in pendientes.items() if v}
    total = len(pendientes)
    if not total:
        return
    print(f"  OpenStreetMap: {total} zonas por descargar (lo demás ya está guardado)", file=sys.stderr, flush=True)
    t0, hechas, seguidos = time.time(), 0, 0
    for n, (c, lista) in enumerate(sorted(pendientes.items()), 1):
        resto = f"quedan unos {_minutos((time.time() - t0) / hechas * (total - n + 1))}" if hechas else "calculando el tiempo"
        print(f"\r  OpenStreetMap: zona {n}/{total} · {resto}", end="", file=sys.stderr, flush=True)
        if seguidos >= 2:
            for *_, q in lista:
                _sin_red[q] = "Overpass no responde: servidor saturado"
            continue
        caja = _caja(c)
        cuerpo = "".join(f"({f.format(caja=caja)})->.p{i};.p{i} {sal}make fin p={i};out;" for i, (f, sal, _) in enumerate(lista))
        try:
            datos = _consulta(f"[out:json][timeout:180];{cuerpo}", guardar=False, intentos=4)
        except RuntimeError as ex:
            seguidos += 1
            for *_, q in lista:
                _sin_red[q] = str(ex)
            continue
        partes, actual, vistas = [[] for _ in lista], [], set()
        for el in datos.get("elements", []):
            if el.get("type") == "fin":
                i = int(el.get("tags", {}).get("p", -1))
                if 0 <= i < len(lista):
                    partes[i] = actual
                    vistas.add(i)
                actual = []
            else:
                actual.append(el)
        if len(vistas) != len(lista):
            # falta alguna marca de fin: respuesta cortada; nada se guarda (cada parte se pedirá por separado)
            seguidos += 1
            for *_, q in lista:
                _sin_red.pop(q, None)
            continue
        seguidos = 0
        for (f, sal, q), els in zip(lista, partes):
            _guardar(_fichero(q), json.dumps({"elements": els}))
        hechas += 1
    print(file=sys.stderr)


# celdas que fallaron en la parte en curso: [fallidas, total, motivo] (ver _por_partes)
_cuenta = [0, 0, ""]


def _por_celdas(filtro, salida="out center qt;", celdas=()):
    """Lanza `filtro` (con {caja}) en cada celda y junta los elementos sin repetir. Una celda que no se puede
    descargar se salta (se cuenta en _cuenta): mejor el resto de la ruta que nada."""
    vistos, elementos = set(), []
    for c in celdas:
        _cuenta[1] += 1
        try:
            datos = _consulta(_q(filtro, c, salida))
        except RuntimeError as ex:
            _cuenta[0] += 1
            _cuenta[2] = str(ex)
            continue
        for el in datos.get("elements", []):
            clave = (el["type"], el["id"])
            if clave not in vistos:
                vistos.add(clave)
                elementos.append(el)
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


def _por_partes(res, que, fn):
    """Ejecuta una parte de la descarga; si Overpass falla, la anota en res["fallos"] («pueblos», o «pueblos
    (en parte)» si solo faltan algunas zonas) y sigue con las demás."""
    _cuenta[:] = [0, 0, ""]
    try:
        fn()
    except (RuntimeError, requests.RequestException) as ex:
        _cuenta[:] = [1, 1, str(ex)]
    fallidas, total, motivo = _cuenta
    if fallidas:
        nota = que if fallidas >= total else f"{que} (en parte)"
        print(f"  aviso: sin {nota}: {motivo}" + (f" ({fallidas} de {total} zonas)" if fallidas < total else ""), file=sys.stderr)
        res["fallos"].append(nota)
        res.setdefault("motivo_fallo", motivo)


# lado de la ruta (km) a partir del cual se descarga menos detalle (ver elementos)
EXTENSA_KM = 200


def extension_km(track):
    """Lado mayor (km) del recuadro que ocupa el track."""
    lat, lon = np.asarray(track.lat, float), np.asarray(track.lon, float)
    return float(max((lat.max() - lat.min()) * 111, (lon.max() - lon.min()) * 111 * np.cos(np.radians(lat.mean()))))


def elementos(track, bbox, radio_rios_km=15, radio_cimas_km=20, radio_embalses_km=15, radio_sierras_km=25, servicios=False):
    """Descarga ríos, sierras, cimas, puertos, embalses, regiones, comarcas y pueblos cercanos (con castillo o no).

    En España se cruzan las sierras y los puertos con el Nomenclátor del IGN: la posición oficial manda
    cuando el nombre está en los dos, y se añade lo que solo tiene el IGN (sierras con nombre de sierra y
    puertos junto al track). Fuera de España, o si el IGN no responde, todo sale de OpenStreetMap. bbox: (sur, oeste, norte, este) del mapa.
    Con servicios, también fuentes, bares, tiendas y gasolineras junto al track (ver servicios_cerca).
    Devuelve un diccionario con listas; "fuente_nombres" es "ign" u "osm". Cada parte se descarga por separado:
    si el servidor falla en una, las demás se conservan y "fallos" dice lo que falta (con "motivo_fallo").
    """
    s, o, n, e = bbox
    caja = f"{s:.4f},{o:.4f},{n:.4f},{e:.4f}"
    print("  consultando OpenStreetMap (Overpass)…", file=sys.stderr)
    cerca = _Cercania(track)
    # Ruta extensa: en un mapa de cientos de km no se distinguen aldeas, cascos urbanos ni servicios, y son lo
    # más pesado de descargar; ríos, cimas y embalses se piden solo en las celdas del track (no en una franja
    # de 20 km). Así se hacen muchas menos consultas, y más ligeras.
    extensa = extension_km(track) > EXTENSA_KM
    celdas_ruta = _celdas(track, 1)
    celdas_anchas = celdas_ruta if extensa else _celdas(track, max(radio_rios_km, radio_cimas_km, radio_embalses_km))
    if extensa:
        print(f"  ruta extensa (unos {extension_km(track):.0f} km de lado): sin aldeas, cascos urbanos ni servicios, "
              "que no se verían a esta escala", file=sys.stderr)
        servicios = False
    res = {"rios": {}, "sierras": [], "cimas": [], "puertos": [], "regiones": [],
           "embalses": [], "comarcas": comarcas(bbox), "pueblos": [], "aldeas": [], "cascos": [], "servicios": [],
           "fuente_nombres": "osm", "fallos": [], "extensa": extensa}
    _descargar_zonas([(celdas_anchas, [F_RIOS, F_CIMAS, F_EMBALSES]),
                      (celdas_ruta, [F_PUERTOS, F_CASTILLOS, F_PUEBLOS]
                       + ([] if extensa else [F_CASCOS, F_ALDEAS]) + ([F_SERVICIOS] if servicios else []))])

    def rios_():
        # ríos: tramos con geometría, agrupados por nombre; se quedan los que pasan cerca
        rios = defaultdict(list)
        for el in _por_celdas(*F_RIOS, celdas=celdas_anchas):
            geo = el.get("geometry")
            if not geo:
                continue
            puntos = [(p["lat"], p["lon"]) for p in geo]
            muestra = puntos[::max(1, len(puntos) // 20)] + [puntos[-1]]
            if min(cerca.km(a, b) for a, b in muestra) <= radio_rios_km:
                rios[el["tags"]["name"]].append(puntos)
        res["rios"] = dict(rios)
    _por_partes(res, "ríos", rios_)

    ign = None
    if _en_espana(track):
        try:
            ign = ngbe.clasificar(ngbe.lugares(_celdas(track, radio_sierras_km)))
            res["fuente_nombres"] = "ign"
        except RuntimeError as ex:
            print(f"  aviso: {ex}; se usan los nombres de OpenStreetMap", file=sys.stderr)

    def cimas_():
        for el in _por_celdas(*F_CIMAS, celdas=celdas_anchas):
            c = _centro(el)
            if c and cerca.km(*c) <= radio_cimas_km:
                res["cimas"].append(_item(el, c))
    _por_partes(res, "cimas", cimas_)

    def puertos_():
        for el in _por_celdas(*F_PUERTOS, celdas=celdas_ruta):
            c = _centro(el)
            if c and cerca.km(*c) <= 0.2:
                res["puertos"].append(_item(el, c))
    _por_partes(res, "puertos", puertos_)
    if ign:
        res["puertos"] = ngbe.combinar(res["puertos"], [p for p in ign[1] if cerca.km(p["lat"], p["lon"]) <= 0.2], True)

    def embalses_():
        for el in _por_celdas(*F_EMBALSES, celdas=celdas_anchas):
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
    _por_partes(res, "embalses", embalses_)

    def pueblos_():
        # pueblos cerca de la ruta (para dibujarlos) y castillos (el pueblo que tiene uno lo lleva en su dibujo)
        castillos = [_centro(el) for el in _por_celdas(*F_CASTILLOS, celdas=celdas_ruta)]
        castillos = [c for c in castillos if c]
        for el in _por_celdas(*F_PUEBLOS, celdas=celdas_ruta):
            c = _centro(el)
            d = cerca.km(*c)
            if d > 12:
                continue
            k = np.cos(np.radians(c[0]))
            castillo = any(np.hypot((a - c[0]) * 111, (b - c[1]) * 111 * k) < 1.5 for a, b in castillos)
            res["pueblos"].append({**_item(el, c), "tipo": el["tags"]["place"], "castillo": castillo, "km_ruta": d})
    _por_partes(res, "pueblos", pueblos_)

    def cascos_():
        # cascos urbanos (landuse=residential): los dibujos de pueblos van sobre ellos, no en cualquier hueco
        # sin cascos (o con zonas sin descargar), None: los pueblos se dibujan junto a su nombre, no se pierden
        res["cascos"] = None
        lista = cascos(track, celdas_ruta, cerca)
        res["cascos"] = None if _cuenta[0] else lista

    def aldeas_():
        for el in _por_celdas(*F_ALDEAS, celdas=celdas_ruta):
            c = _centro(el)
            if c and cerca.km(*c) <= 3:
                res["aldeas"].append({**_item(el, c), "km_ruta": cerca.km(*c)})
    if extensa:
        res["cascos"] = None
    else:
        _por_partes(res, "cascos urbanos", cascos_)
        _por_partes(res, "aldeas", aldeas_)

    if servicios:
        def servicios_():
            res["servicios"] = servicios_cerca(track, celdas_ruta, cerca, res["cascos"] or [])
        _por_partes(res, "servicios junto al track", servicios_)

    # sierras y regiones: pocas y repartidas, basta una consulta al encuadre
    for filtro, clave, que in (('nwr["natural"="mountain_range"]["name"]', "sierras", "sierras"),
                               ('node["place"~"^(state|province|region)$"]["name"]', "regiones", "regiones")):
        def una():
            for el in _consulta(f"[out:json][timeout:200];{filtro}({caja});out center qt;").get("elements", []):
                c = _centro(el)
                if c:
                    item = _item(el, c)
                    if clave == "regiones":
                        item["tipo"] = el["tags"]["place"]
                    res[clave].append(item)
        _por_partes(res, que, una)
    if ign:
        s_, o_, n_, e_ = bbox
        res["sierras"] = ngbe.combinar(res["sierras"], [x for x in ign[0] if s_ < x["lat"] < n_ and o_ < x["lon"] < e_])
    return res


def cascos(track, celdas, cerca, radio_km=12):
    """Zonas residenciales de OpenStreetMap a menos de radio_km del track: centro, recuadro y tamaño aproximado."""
    salida = []
    for el in _por_celdas(*F_CASCOS, celdas=celdas):
        b = el.get("bounds")
        if not b:
            continue
        c = el.get("center") or {"lat": (b["minlat"] + b["maxlat"]) / 2, "lon": (b["minlon"] + b["maxlon"]) / 2}
        if cerca.km(c["lat"], c["lon"]) > radio_km:
            continue
        k = np.cos(np.radians(c["lat"]))
        area = (b["maxlat"] - b["minlat"]) * 111 * (b["maxlon"] - b["minlon"]) * 111 * k
        salida.append({"lat": c["lat"], "lon": c["lon"], "s": b["minlat"], "o": b["minlon"], "n": b["maxlat"], "e": b["maxlon"],
                       "km2": round(area, 4)})
    return salida


def casco_de(lat, lon, cascos, radio_km=1.5):
    """Casco urbano de una localidad: une las zonas residenciales a menos de radio_km de su punto y devuelve
    (lat, lon) del centro (ponderado por tamaño) y su recuadro (s, o, n, e), o None si no hay ninguna."""
    if not cascos:
        return None
    k = np.cos(np.radians(lat))
    cerca_ = [c for c in cascos if np.hypot((c["lat"] - lat) * 111, (c["lon"] - lon) * 111 * k) <= radio_km]
    if not cerca_:
        return None
    pesos = np.array([max(c["km2"], 0.002) for c in cerca_])
    clat = float(np.average([c["lat"] for c in cerca_], weights=pesos))
    clon = float(np.average([c["lon"] for c in cerca_], weights=pesos))
    caja = (min(c["s"] for c in cerca_), min(c["o"] for c in cerca_), max(c["n"] for c in cerca_), max(c["e"] for c in cerca_))
    return clat, clon, caja


# tipos de servicio: clave de icono y etiqueta para la leyenda; separación mínima a lo largo de la ruta (km)
SERVICIOS = {"agua": ("fuente", 2.0), "gasolinera": ("gasolinera", 5.0), "tienda": ("tienda", 3.0), "bar": ("bar", 3.0)}


def _tipo_servicio(t):
    a, sh = t.get("amenity"), t.get("shop")
    if a in ("drinking_water",) or t.get("man_made") == "water_tap" or (t.get("natural") == "spring" and t.get("drinking_water") == "yes"):
        return "agua"
    if a == "fuel":
        return "gasolinera"
    if sh in ("supermarket", "convenience", "bakery"):
        return "tienda"
    if a in ("cafe", "bar", "restaurant", "fast_food"):
        return "bar"
    return None


def servicios_cerca(track, celdas, cerca, cascos_, max_km=0.4):
    """Fuentes, bares y restaurantes, tiendas y gasolineras a menos de max_km del track. Dentro de un casco urbano
    solo los supermercados con marca (en un pueblo, de lo demás siempre hay). Como mucho uno de cada tipo cada
    pocos km de ruta (SERVICIOS), el más cercano al track. Cada uno: tipo, nombre, lat, lon, km (de la ruta)."""
    paso = max(1, len(track.lat) // 6000)
    lat_t, lon_t, km_t = track.lat[::paso], track.lon[::paso], np.asarray(track.km)[::paso]
    k = np.cos(np.radians(float(lat_t.mean())))
    cajas = np.array([[c["s"], c["o"], c["n"], c["e"]] for c in cascos_]) if cascos_ else np.zeros((0, 4))
    cand = []
    for el in _por_celdas(*F_SERVICIOS, celdas=celdas):
        c, t = _centro(el), el.get("tags", {})
        tipo = _tipo_servicio(t) if c else None
        if not tipo:
            continue
        d = np.hypot((lat_t - c[0]) * 111, (lon_t - c[1]) * 111 * k)
        i = int(np.argmin(d))
        if d[i] > max_km:
            continue
        en_casco = bool(len(cajas)) and bool(((cajas[:, 0] <= c[0]) & (c[0] <= cajas[:, 2]) & (cajas[:, 1] <= c[1]) & (c[1] <= cajas[:, 3])).any())
        if en_casco and not (tipo == "tienda" and t.get("shop") == "supermarket" and t.get("brand")):
            continue
        cand.append({"tipo": tipo, "nombre": t.get("brand") or t.get("name") or "", "lat": c[0], "lon": c[1],
                     "km": round(float(km_t[i]), 2), "dist": round(float(d[i]), 3)})
    elegidos = []
    for c in sorted(cand, key=lambda x: x["dist"]):
        sep = SERVICIOS[c["tipo"]][1]
        if not any(e["tipo"] == c["tipo"] and abs(e["km"] - c["km"]) < sep for e in elegidos):
            elegidos.append(c)
    print(f"  servicios junto al track: {len(elegidos)} (de {len(cand)})", file=sys.stderr)
    return sorted(elegidos, key=lambda x: x["km"])


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
        _guardar(fichero, json.dumps(filas, ensure_ascii=False))
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
