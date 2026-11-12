"""Lectura del track GPX y de la hoja de ruta, y cálculo de tiempos por tramo."""
import csv
import math
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

RADIO_TIERRA = 6371008.8


# ---------------------------------------------------------------- track GPX

@dataclass
class Track:
    lat: np.ndarray
    lon: np.ndarray
    ele: np.ndarray          # altitud suavizada (m)
    km: np.ndarray           # distancia acumulada (km)
    nombre: str = ""

    @property
    def total_km(self):
        return float(self.km[-1])

    def en_km(self, km):
        """Interpola lat, lon y altitud para una (o varias) distancias."""
        return (np.interp(km, self.km, self.lat),
                np.interp(km, self.km, self.lon),
                np.interp(km, self.km, self.ele))

    def ascenso_descenso(self, km0, km1, umbral=3.0):
        """Desnivel positivo y negativo entre dos distancias, con histéresis."""
        sel = (self.km >= km0) & (self.km <= km1)
        e = self.ele[sel]
        if len(e) < 2:
            return 0.0, 0.0
        sube = baja = 0.0
        ref = e[0]
        for v in e[1:]:
            if v - ref >= umbral:
                sube += v - ref
                ref = v
            elif ref - v >= umbral:
                baja += ref - v
                ref = v
        return sube, baja


def _haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA * np.arcsin(np.sqrt(a))


def leer_gpx(ruta, paso_m=25.0, ventana_m=150.0, altitud="mdt", paso_mdt_m=50.0):
    """Lee los puntos del track, remuestrea cada `paso_m` y suaviza la altitud.

    altitud="mdt" toma las altitudes del modelo digital del terreno (cada
    `paso_mdt_m`); "gpx" usa las del propio fichero.
    """
    raiz = ET.parse(ruta).getroot()
    ns = {"g": raiz.tag.split("}")[0].strip("{")} if raiz.tag.startswith("{") else {"g": ""}
    pre = "g:" if ns["g"] else ""
    lat, lon, ele = [], [], []
    for pt in raiz.iterfind(f".//{pre}trkpt", ns):
        lat.append(float(pt.get("lat")))
        lon.append(float(pt.get("lon")))
        e = pt.find(f"{pre}ele", ns)
        ele.append(float(e.text) if e is not None else np.nan)
    if not lat:  # rutas exportadas como <rte>
        for pt in raiz.iterfind(f".//{pre}rtept", ns):
            lat.append(float(pt.get("lat")))
            lon.append(float(pt.get("lon")))
            e = pt.find(f"{pre}ele", ns)
            ele.append(float(e.text) if e is not None else np.nan)
    nombre_el = raiz.find(f".//{pre}trk/{pre}name", ns)
    lat, lon, ele = map(np.asarray, (lat, lon, ele))
    sin_ele = np.isnan(ele).all()
    if sin_ele and altitud != "mdt":
        raise ValueError("El GPX no trae altitudes (<ele>) y se ha pedido usar las del GPX "
                         "(fuente = \"gpx\"): usa las del modelo del terreno (fuente = \"mdt\").")
    if sin_ele:
        ele = np.zeros(len(lat))       # se sustituyen por las del MDT
    ele = np.where(np.isnan(ele), np.interp(np.arange(len(ele)), np.flatnonzero(~np.isnan(ele)),
                                            ele[~np.isnan(ele)]), ele)

    d = np.concatenate([[0.0], np.cumsum(_haversine(lat[:-1], lon[:-1], lat[1:], lon[1:]))])
    # remuestreo regular por distancia para que el suavizado no dependa de la densidad del GPX
    dr = np.arange(0.0, d[-1], paso_m)
    dr = np.append(dr, d[-1])
    lat_r, lon_r, ele_r = (np.interp(dr, d, a) for a in (lat, lon, ele))
    if altitud == "mdt":
        from .elevacion import altitudes_mdt
        dm = np.append(np.arange(0.0, d[-1], paso_mdt_m), d[-1])
        em, error = None, None
        # MDT europeo de 25 m; fuera de su cobertura (casi todo sin dato), SRTM de 30 m (mundial)
        for dataset in ("eudem25m", "srtm30m"):
            try:
                em = altitudes_mdt(np.interp(dm, d, lat), np.interp(dm, d, lon), dataset=dataset)
            except Exception as e:  # sin red o servicio caído
                em, error = None, e
                continue
            if np.isnan(em).mean() < 0.5:
                break
            em = None
        if em is not None:
            ele_r = np.interp(dr, dm, em)
        elif sin_ele:
            raise ValueError("El GPX no trae altitudes (<ele>) y no se ha podido consultar el modelo digital del "
                             f"terreno ({error or 'sin datos para esta zona'}). Comprueba la conexión a Internet "
                             "y vuelve a intentarlo, o usa un GPX con altitudes.")
        else:
            print(f"  aviso: no se pudo consultar el MDT ({error or 'sin datos'}); uso las altitudes del GPX")
    n = max(1, int(round(ventana_m / paso_m)))
    if n > 1:
        k = np.ones(n) / n
        ele_r = np.convolve(np.pad(ele_r, (n // 2, n - 1 - n // 2), mode="edge"), k, mode="valid")
    return Track(lat_r, lon_r, ele_r, dr / 1000.0,
                 nombre_el.text if nombre_el is not None else Path(ruta).stem)


def leer_waypoints(ruta):
    """Waypoints del GPX: [(nombre, tipo, lat, lon)]."""
    raiz = ET.parse(ruta).getroot()
    ns = raiz.tag.split("}")[0].strip("{") if raiz.tag.startswith("{") else ""
    pre = f"{{{ns}}}" if ns else ""
    salida = []
    for w in raiz.iter(f"{pre}wpt"):
        nombre = w.findtext(f"{pre}name") or ""
        tipo = w.findtext(f"{pre}type") or ""
        salida.append((nombre.strip(), tipo.strip(), float(w.get("lat")), float(w.get("lon"))))
    return salida


RE_WPT_CONTROL = re.compile(r"^\s*(?:C|CP|PC|CONTROL)\s*[_\-. ]?\s*0*([0-9]+|[A-Z])(?:[_\-. ]+(.*))?$", re.I)
GENERICOS = {"salida", "meta", "llegada", "inicio", "final", "fin", "start", "finish", ""}


def _mismo_lugar(a, b):
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def anclar_controles(track, puntos, waypoints, radio_m=300):
    """Ajusta los km de la hoja al GPX usando los waypoints de control como anclas.

    Devuelve la lista de anclas [(km_hoja, km_gpx)] y una lista de avisos. Si el waypoint
    de un control lleva el nombre de otro punto de la hoja, el control se traslada a ese
    punto (la hoja puede ser de otra edición; el GPX manda).
    """
    avisos, anclas = [], []
    wpts = {}
    for nombre, tipo, lat, lon in waypoints:
        m = RE_WPT_CONTROL.match(nombre)
        if m:
            wpts.setdefault("C" + m.group(1).upper(), (m.group(2) or "", lat, lon))
    if not wpts:
        return anclas, avisos
    ultimo_km = -1.0
    vistos = set()
    for p in list(puntos):
        if not p.control or p.control in vistos or p.control not in wpts:
            continue
        vistos.add(p.control)
        nombre_w, lat, lon = wpts[p.control]
        destino = p
        if _norm(nombre_w) not in GENERICOS and not _mismo_lugar(nombre_w, p.nombre):
            otro = next((q for q in puntos if q is not p and not q.control and _mismo_lugar(nombre_w, q.nombre)), None)
            if otro:
                avisos.append(f"{p.control}: el GPX lo sitúa en {otro.nombre} (km {otro.km_hoja:g} de la hoja), "
                              f"no en {p.nombre}; se traslada el control y sus horas")
                otro.control, p.control = p.control, ""
                otro.cierre_hoja, p.cierre_hoja = p.cierre_hoja, None
                otro.apertura_hoja, p.apertura_hoja = p.apertura_hoja, None
                destino = otro
            else:
                avisos.append(f"{p.control}: el waypoint del GPX se llama '{nombre_w}' y la hoja dice "
                              f"'{p.nombre}'; se usa la posición del GPX")
        d = _haversine(lat, lon, track.lat, track.lon)
        cerca = np.flatnonzero(d < radio_m)
        if not len(cerca):
            avisos.append(f"{destino.control}: el waypoint está a {d.min():.0f} m del track; no se usa")
            continue
        grupos = np.split(cerca, np.flatnonzero(np.diff(track.km[cerca]) > 2) + 1)
        candidatos = [float(track.km[g[np.argmin(d[g])]]) for g in grupos]
        km = next((k for k in candidatos if k > ultimo_km), None)
        if km is None:
            continue
        anclas.append((destino.km_hoja, km))
        ultimo_km = km
    return sorted(anclas), avisos


# ------------------------------------------------------------- hoja de ruta

def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@dataclass
class Punto:
    nombre: str
    km_hoja: float
    control: str = ""           # "C1", "C2", "CF"… vacío si es un punto accesorio
    cierre_hoja: datetime | None = None
    apertura_hoja: datetime | None = None
    # calculados
    km: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0
    km_tramo: float = 0.0
    asc_tramo: float = 0.0
    desc_tramo: float = 0.0
    asc_total: float = 0.0
    pendiente: float = 0.0      # ascenso del tramo / distancia del tramo (como en la hoja original)
    fraccion: float = 0.0
    velocidad: float = 0.0
    parada_min: float = 0.0
    tipo_parada: str = ""
    llegada: datetime | None = None
    salida: datetime | None = None
    cierre: datetime | None = None
    destacado: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def es_control(self):
        return bool(self.control)

    @property
    def antes_de_apertura(self):
        """Llega antes de que abra el control (en los BRM no se puede sellar)."""
        return bool(self.apertura_hoja and self.llegada and self.llegada < self.apertura_hoja)

    @property
    def margen(self):
        """Tiempo que queda hasta el cierre al reanudar la marcha (llegada + parada)."""
        fin = self.salida or self.llegada
        return self.cierre - fin if self.cierre and fin else None


def _id_control(texto):
    t = _norm(texto)
    if not t:
        return ""
    m = re.search(r"(?:control|c|cp|pc)\s*([0-9]+|[a-z])\b", t)
    if m:
        return "C" + m.group(1).upper()
    return "C" + t.replace(" ", "").upper()


def puntos_de_lista(lista):
    """Puntos desde una lista de diccionarios (nombre, km_hoja, control y, opcionales, cierre_hoja y apertura_hoja en
    ISO y localidad): la de un plan de VenB, ya leída o editada a mano."""
    puntos = []
    for x in lista:
        p = Punto(str(x["nombre"]), float(x["km_hoja"]), x.get("control") or "",
                  _a_datetime(x.get("cierre_hoja")), _a_datetime(x.get("apertura_hoja")))
        p.extra["localidad"] = x.get("localidad", True)
        puntos.append(p)
    return puntos


def _a_datetime(v):
    if isinstance(v, datetime):
        return v
    if isinstance(v, (int, float)):
        return datetime(1899, 12, 30) + timedelta(days=float(v))
    if isinstance(v, str) and v.strip():
        for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(v.strip(), fmt)
            except ValueError:
                pass
    return None


def leer_hoja(ruta):
    """Lee la hoja de ruta (xlsx, csv o pdf). Devuelve (puntos, metadatos).

    Los PDF (formato BRM) los lee `hoja_pdf.leer_pdf`, que además saca la fecha y hora de
    salida, el tiempo límite y las horas de apertura y cierre de cada control.

    Columnas reconocidas por su cabecera (en cualquier orden):
      Control (opcional: "Control 1", "C1", "Control F"…; vacía en puntos accesorios),
      Ubicación / Nombre / Lugar, km / km totales / PK,
      Cierre (opcional: hora límite oficial; las celdas con fórmula se ignoran).
    """
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext == ".pdf":
        from .hoja_pdf import leer_pdf
        return leer_pdf(ruta)
    if ext in (".odt", ".ods"):
        from .hoja_pdf import leer_documento
        tablas, texto = leer_odf(ruta)
        for filas in sorted(tablas, key=len, reverse=True):
            try:
                return _leer_filas(filas, ruta)
            except ValueError:
                pass
        return leer_documento([f for t in tablas for f in t], texto, ruta.name)
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        hoja = openpyxl.load_workbook(ruta, data_only=False).worksheets[0]
        filas = [[c.value for c in fila] for fila in hoja.iter_rows()]
    else:
        with open(ruta, newline="", encoding="utf-8-sig") as f:
            muestra = f.read(2048)
            f.seek(0)
            dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t")
            filas = list(csv.reader(f, dialecto))
    filas = [f for f in filas if any(c not in (None, "") for c in f)]
    try:
        return _leer_filas(filas, ruta)
    except ValueError:
        # hoja de organizador (títulos LOCALIDADES, KM TOTAL… no en la primera fila)
        from .hoja_pdf import leer_documento
        texto = "\n".join(" ".join(str(c) for c in f if c not in (None, "")) for f in filas)
        return leer_documento([["" if c is None else str(c).strip() for c in f] for f in filas], texto, ruta.name)


def leer_odf(ruta):
    """Tablas (lista de filas de texto) y texto de un documento ODT u ODS, sin dependencias externas."""
    import zipfile
    t = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
    tx = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
    with zipfile.ZipFile(ruta) as z:
        raiz = ET.fromstring(z.read("content.xml"))

    def texto_de(el):
        partes = []
        for p in el.iter():
            if p.tag in (f"{tx}p", f"{tx}h"):
                partes.append("".join(_texto_odf(p, tx)))
        return "\n".join(partes)

    tablas = []
    for tabla in raiz.iter(f"{t}table"):
        filas = []
        for fila in tabla.iter(f"{t}table-row"):
            celdas = []
            for c in fila:
                if c.tag not in (f"{t}table-cell", f"{t}covered-table-cell"):
                    continue
                v = c.get("{urn:oasis:names:tc:opendocument:xmlns:office:1.0}value")
                txt = texto_de(c).strip()
                rep = min(int(c.get(f"{t}number-columns-repeated", "1")), 50)
                celdas += [txt if txt else (v or "")] * rep
            while celdas and celdas[-1] == "":
                celdas.pop()
            rep = int(fila.get(f"{t}number-rows-repeated", "1"))
            if celdas:
                filas += [celdas] * min(rep, 50)
        if filas:
            tablas.append(filas)
    # texto del documento en orden: párrafos fuera de tablas y filas de tabla como líneas
    lineas = []
    cuerpo = raiz.find("{urn:oasis:names:tc:opendocument:xmlns:office:1.0}body")
    for el in (cuerpo.iter() if cuerpo is not None else []):
        if el.tag == f"{t}table-row":
            celdas = [texto_de(c).replace("\n", " ").strip() for c in el]
            lineas.append(" ".join(c for c in celdas if c))
        elif el.tag in (f"{tx}p", f"{tx}h") and not _dentro_de_tabla(el, cuerpo, t):
            lineas.append("".join(_texto_odf(el, tx)))
    return tablas, "\n".join(l for l in lineas if l.strip())


def _texto_odf(el, tx):
    """Texto de un párrafo ODF con sus espacios (text:s) y tabuladores."""
    partes = [el.text or ""]
    for h in el:
        if h.tag == f"{tx}s":
            partes.append(" " * int(h.get(f"{tx}c", "1")))
        elif h.tag in (f"{tx}tab", f"{tx}line-break"):
            partes.append(" ")
        else:
            partes += _texto_odf(h, tx)
        partes.append(h.tail or "")
    return partes


_PADRES = {}


def _dentro_de_tabla(el, cuerpo, t):
    if id(cuerpo) not in _PADRES:
        _PADRES.clear()
        _PADRES[id(cuerpo)] = {c: p for p in cuerpo.iter() for c in p}
    padres = _PADRES[id(cuerpo)]
    while el in padres:
        el = padres[el]
        if el.tag == f"{t}table-cell":
            return True
    return False


SI_CONTROL = {"si", "s", "x", "1", "yes", "y", "true", "verdadero", "control", "c"}


def _leer_filas(filas, ruta):
    """Hoja sencilla: Control, Ubicación y km (y Cierre, opcional). Los títulos pueden ir tras unas filas de cabecera.
    En la columna Control vale «Sí» o «X» (se numeran C1, C2…) o el identificador («C3», «Control 3», «CF»)."""
    if not filas:
        raise ValueError(f"La hoja {Path(ruta).name} está vacía")
    for n, fila in enumerate(filas[:10]):
        normas = [_norm(c) for c in fila]
        if any(c.startswith(("ubicacion", "nombre", "lugar", "localidad", "punto")) for c in normas) and \
                any(c.startswith(("km", "pk", "kilometro")) for c in normas):
            if n and any(c.startswith(("abiert", "cerrad", "apertura", "open", "ouverture", "fermeture")) for c in normas):
                break          # hoja de organizador con horas de control: la lee hoja_pdf.leer_documento
            filas = filas[n:]
            break
    cab = [_norm(c) for c in filas[0]]

    def col(*claves, exacta=False):
        for clave in claves:
            for i, c in enumerate(cab):
                if (c == clave) if exacta else c.startswith(clave):
                    return i
        return None

    i_ctrl = col("control", "cp")
    i_nom = col("ubicacion", "nombre", "lugar", "localidad", "punto")
    i_km = col("km totales", "km total", "pk", "km", "kilometro")
    i_cierre = col("cierre")
    if i_nom is None or i_km is None:
        raise ValueError(f"La hoja {Path(ruta).name} necesita columnas de nombre y de km (cabeceras: {filas[0]})")

    puntos = []
    for fila in filas[1:]:
        if i_km >= len(fila) or fila[i_km] in (None, ""):
            continue
        try:
            km = float(str(fila[i_km]).replace(",", "."))
        except ValueError:
            continue
        cierre = None
        if i_cierre is not None and i_cierre < len(fila):
            v = fila[i_cierre]
            if not (isinstance(v, str) and v.startswith("=")):
                cierre = _a_datetime(v)
        bruto = fila[i_ctrl] if i_ctrl is not None and i_ctrl < len(fila) else ""
        ctrl = "?" if _norm(bruto) in SI_CONTROL else _id_control(bruto)
        if _norm(bruto) in ("no", "n", "0", "false", "falso"):
            ctrl = ""
        if fila[i_nom] in (None, ""):
            continue
        puntos.append(Punto(str(fila[i_nom]).strip(), km, ctrl, cierre))
    if not puntos:
        raise ValueError(f"No se han encontrado puntos en {Path(ruta).name}")
    n = 0
    for p in puntos:               # «Sí» en la columna Control: C1, C2… por orden
        if p.control == "?":
            n += 1
            p.control = f"C{n}"
    return puntos, {}


# ---------------------------------------------------------------- reglas de Randonneurs Mondiaux

# Tiempo límite de cada BRM (h). Las Super Randonnées de 600 km tienen 60 h (categoría randonneur).
LIMITES_BRM = {200: 13.5, 300: 20, 400: 27, 600: 40, 1000: 75, 1200: 90}
LIMITE_SR600 = 60
# Velocidades de la tabla de controles: (hasta km, km/h). Apertura, a la máxima; cierre, a la mínima.
APERTURA_BRM = [(200, 34), (400, 32), (600, 30), (1000, 28), (1300, 26)]
# 13,333 sube a propósito (un 1200 cierra en 90 h). Más allá de 1300 km, RM fija medias para toda la prueba
# (12, 10 km/h, 200 km/día): esas pruebas no están en LIMITES_BRM; se planifican como «libre».
CIERRE_BRM = [(600, 15), (1000, 11.428), (1300, 13.333)]


def _horas_tramos(km, tramos):
    h, desde = 0.0, 0.0
    for hasta, v in tramos:
        tramo = min(km, hasta) - desde
        if tramo <= 0:
            break
        h += tramo / v
        desde = hasta
    if km > desde:
        h += (km - desde) / tramos[-1][1]
    return h


def horas_brm(km, distancia, final=False):
    """(apertura, cierre) de un control en horas desde la salida, redondeadas al minuto, según la tabla de
    Randonneurs Mondiaux. Hasta el km 60 el cierre es a 20 km/h más una hora (la salida cierra a la hora).
    La meta (y cualquier control a partir de la distancia nominal) cierra en el tiempo límite del BRM."""
    limite = LIMITES_BRM[distancia]
    ap = _horas_tramos(min(km, distancia), APERTURA_BRM)
    if final or km >= distancia:
        ci = limite
    elif km <= 60:
        ci = km / 20 + 1
    else:
        ci = min(_horas_tramos(km, CIERRE_BRM), limite)
    return round(ap * 60) / 60, round(ci * 60) / 60


def distancia_nominal(km):
    """Distancia de BRM a la que corresponde una ruta (la mayor que no supera la ruta en más de un 5 %), o None."""
    candidatas = [d for d in LIMITES_BRM if d <= km * 1.05]
    return max(candidatas) if candidatas else None


# ---------------------------------------------------------------- cálculos

# Tabla de la hoja original: [pendiente límite (fracción), km/h]. Se compara con «<», salvo la
# última fila con límite, que incluye el propio límite (≤ 6 %); por encima, la velocidad «resto».
VELOCIDADES = {
    "tramos": [[-0.02, 27], [0.0, 24], [0.01, 22], [0.02, 20], [0.03, 16], [0.04, 14], [0.05, 12], [0.06, 10]],
    "resto": 8,
    "fatiga_pct": 1.0,       # se pierde este % de velocidad…
    "fatiga_cada": 0.2,      # …por cada fracción de ruta recorrida…
    "fatiga_max_pct": 5.0,   # …hasta este máximo
    "factor": 1.0,           # escala la tabla entera (velocidad media elegida / la que da la tabla)
}


def velocidades(cfg=None):
    """Tabla por defecto con los cambios de `cfg` encima."""
    v = {k: (list(x) if isinstance(x, list) else x) for k, x in VELOCIDADES.items()}
    v.update({k: x for k, x in (cfg or {}).items() if x is not None and k in VELOCIDADES})
    v["tramos"] = sorted(([float(a), float(b)] for a, b in v["tramos"]), key=lambda t: t[0])
    return v


def velocidad_base(pendiente, cfg=None):
    """Velocidad media (km/h) según la pendiente media del tramo, sin fatiga ni factor."""
    v = cfg or VELOCIDADES
    tramos = v["tramos"]
    for i, (limite, vel) in enumerate(tramos):
        if pendiente < limite or (i == len(tramos) - 1 and pendiente <= limite):
            return vel
    return v["resto"]


def factor_fatiga(fraccion, cfg=None):
    """Por defecto, −1 % por cada 20 % de ruta completado, hasta un máximo del 5 %."""
    v = cfg or VELOCIDADES
    cada = v["fatiga_cada"] or 1.0
    return 1 - min(math.floor(fraccion / cada + 1e-6) * v["fatiga_pct"], v["fatiga_max_pct"]) / 100


def velocidad(pendiente, fraccion, cfg=None):
    v = cfg or VELOCIDADES
    return velocidad_base(pendiente, v) * factor_fatiga(fraccion, v) * v.get("factor", 1.0)


@dataclass
class Plan:
    track: Track
    puntos: list
    salida: datetime
    limite_h: float
    nombre: str

    @property
    def controles(self):
        return [p for p in self.puntos if p.es_control]

    @property
    def total_km(self):
        return self.puntos[-1].km

    @property
    def total_asc(self):
        return self.puntos[-1].asc_total

    @property
    def llegada_final(self):
        return self.puntos[-1].llegada


def calcular(track, puntos, salida, limite_h, paradas_defecto=0, paradas=None,
             tipos=None, destacados=(), ajuste_km="auto", umbral_desnivel=3.0, nombre="",
             waypoints=(), vel=None, regla=None):
    """Rellena posición, altitud, desnivel, velocidad y horarios de cada punto.

    regla: {"distancia": 200…} para un BRM: apertura y cierre de los controles según Randonneurs Mondiaux
    (las horas que trae la hoja mandan). Sin regla, el cierre se reparte en proporción a la distancia.

    paradas: {clave: minutos}; tipos: {clave: "cafe"|"comida"|"dormir"…}. La clave
    puede ser el id del control ("C6"), el nombre del punto o "nombre@km".
    """
    vel = velocidades(vel)
    paradas = {k.upper(): v for k, v in (paradas or {}).items()}
    tipos = {k.upper(): v for k, v in (tipos or {}).items()}
    destacados = {d.upper() for d in destacados}

    km_hoja_final = puntos[-1].km_hoja or 1.0
    avisos = []
    anclas = []
    if ajuste_km in ("auto", "waypoints") and waypoints:
        anclas, avisos = anclar_controles(track, puntos, waypoints)
    if anclas:
        # salida y meta fijas en los extremos del track; anclas en orden creciente
        h, g = [0.0], [0.0]
        for kh, kg in anclas:
            if h[-1] < kh < km_hoja_final and g[-1] < kg < track.total_km:
                h.append(kh)
                g.append(kg)
        h.append(km_hoja_final)
        g.append(track.total_km)

        def a_gpx(km):
            return float(np.interp(km, h, g))
    else:
        escala = track.total_km / km_hoja_final if ajuste_km != "ninguno" else 1.0

        def a_gpx(km):
            return km * escala

    def busca(dic, p):
        for clave in (f"{p.nombre}@{p.km_hoja:g}".upper(), p.control.upper() if p.control else None,
                      p.nombre.upper()):
            if clave and clave in dic:
                return dic[clave]
        return None

    asc_total = 0.0
    anterior = None
    for i, p in enumerate(puntos):
        p.km = min(a_gpx(p.km_hoja), track.total_km)
        p.lat, p.lon, p.alt = (float(x) for x in track.en_km(p.km))
        p.fraccion = p.km / track.total_km
        p.destacado = p.es_control or busca({k: True for k in destacados}, p) is not None
        if anterior is None:
            p.llegada = p.salida = salida
            p.parada_min = 0
        else:
            p.km_tramo = p.km - anterior.km
            p.asc_tramo, p.desc_tramo = track.ascenso_descenso(anterior.km, p.km, umbral_desnivel)
            asc_total += p.asc_tramo
            p.pendiente = p.asc_tramo / (1000 * p.km_tramo) if p.km_tramo > 0 else 0.0
            p.velocidad = velocidad(p.pendiente, p.fraccion, vel)
            p.llegada = anterior.salida + timedelta(hours=p.km_tramo / p.velocidad)
            minutos = busca(paradas, p)
            es_ultimo = i == len(puntos) - 1
            if minutos is None:
                minutos = paradas_defecto if p.es_control and not es_ultimo else 0
            p.parada_min = float(minutos)
            p.salida = p.llegada + timedelta(minutes=p.parada_min)
        p.asc_total = asc_total
        p.tipo_parada = busca(tipos, p) or ""
        if regla:
            final = i == len(puntos) - 1
            ap, ci = horas_brm(p.km_hoja, regla["distancia"], final=final)
            # la meta cierra siempre en el tiempo límite oficial, aunque la hoja diga otra cosa
            p.cierre = salida + timedelta(hours=ci) if final or not p.cierre_hoja else p.cierre_hoja
            if final or not p.cierre_hoja:
                p.extra["cierre_rm_h"] = ci          # horas desde la salida (la página interactiva la deja cambiar)
            if p.es_control and i and not p.apertura_hoja:
                p.apertura_hoja = salida + timedelta(hours=ap)
                p.extra["apertura_rm_h"] = ap
        else:
            p.cierre = p.cierre_hoja or (salida + timedelta(hours=p.fraccion * limite_h))
        anterior = p
    plan = Plan(track, puntos, salida, limite_h, nombre or track.nombre)
    plan.avisos = avisos
    plan.anclas = len(anclas)
    plan.velocidades = vel
    return plan


def hora_en_km(plan, km):
    """Hora prevista de paso por una distancia cualquiera (para colorear por días)."""
    km = np.atleast_1d(np.asarray(km, dtype=float))
    t0 = plan.salida
    pts = plan.puntos
    kms = np.array([p.km for p in pts])
    sal = np.array([(p.salida - t0).total_seconds() for p in pts])
    lle = np.array([(p.llegada - t0).total_seconds() for p in pts])
    i = np.clip(np.searchsorted(kms, km, side="right"), 1, len(pts) - 1)
    largo = np.maximum(kms[i] - kms[i - 1], 1e-9)
    f = np.clip((km - kms[i - 1]) / largo, 0, 1)
    seg = sal[i - 1] + f * (lle[i] - sal[i - 1])
    return [t0 + timedelta(seconds=float(s)) for s in seg]
