"""Mapas ilustrados (estilo dibujado a mano) a partir del track y de datos OSM/Wikidata.

Dos estilos que comparten la base:
  - "alballut": el mapa simplificado de la versión 2 (tierra teñida, ríos, sierras, título).
  - "personal": relieve dibujado a partir del modelo del terreno, paleta y papel propios,
    controles numerados, cartucho con la marca y los datos de la ruta, y perfil al pie.
"""
import re
import unicodedata
from datetime import timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patheffects as pe
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle, FancyBboxPatch, Polygon
from PIL import Image, ImageFilter
from shapely.geometry import LineString

from . import estilo as E
from .proyecto import fmt_dur
from .teselas import a_mercator, mapa_base, zoom_para

PT = 100 / 72
CONECTORES = {"de", "del", "la", "las", "los", "el", "y", "e", "d"}
BOCETO = (1.0, 90, 2.5)
REDUCCIONES = (1.0, 0.8, 0.65)  # tamaños que se prueban para un rótulo que no cabe        # (escala, longitud, aleatoriedad) del trazo "a mano"

PALETAS = {
    "alballut": dict(papel="#faf6ea", tinta="#1f1f1f", agua="#d3e8ee", agua_borde="#7fb6c9",
                     rio="#5ea7c3", rio_texto="#3b88a6", tierra=["#efe5bd", "#e7dca8"],
                     manchas="#d5e2a6", relieve="#6b5a3e", acento="#1f1f1f", comarca="#9c8f6a"),
    "verde": dict(papel="#eef3e3", tinta="#1f2a20", agua="#cfe5e8", agua_borde="#5f9cab",
                  rio="#4a90a8", rio_texto="#2a6e84", tierra=["#dfeac8", "#cddfad"],
                  manchas="#bcd396", relieve="#4d6340", acento="#b8322a", comarca="#5b7150",
                  grano=(0.18, 0.30, 0.16)),
    "acuarela": dict(papel="#f7f1e3", tinta="#2a2420", agua="#cfe4ec", agua_borde="#6aa5bd",
                     rio="#4f9dbd", rio_texto="#2f7896", tierra=["#f0e3bf", "#e6d4a5"],
                     manchas="#cfdea6", relieve="#7a6347", acento="#b8322a", comarca="#9a7f55"),
    "bosque": dict(papel="#f2f0e4", tinta="#1e2a22", agua="#cfe2e6", agua_borde="#5f9aa8",
                   rio="#4a8fa0", rio_texto="#2c6f80", tierra=["#e1e7c6", "#cfdcae"],
                   manchas="#b9cf93", relieve="#4f5e3c", acento="#b5542d", comarca="#66744d"),
    # mapa antiguo de fantasía: llanura verde pálida, roca gris, bosque oscuro, agua petróleo y rótulos granate
    "tronos": dict(papel="#e6dfc3", tinta="#3b2c20", agua="#557f88", agua_borde="#2c4e57",
                   rio="#4f7d8c", rio_texto="#2c5563", tierra=["#d8d4a6", "#c3c08a"],
                   manchas="#a9b27a", relieve="#5b5446", acento="#8e1b18", comarca="#6b5a3e",
                   lugar="#6e1a16", bosque="#5d7d40", grano=(0.32, 0.26, 0.14),
                   arbol="#5e7a3c", tejado="#a4483a"),
    "pizarra": dict(papel="#ebe8e1", tinta="#22262b", agua="#cad7e0", agua_borde="#6f8796",
                    rio="#5c7f95", rio_texto="#3e6177", tierra=["#ddd7c9", "#cec6b3"],
                    manchas="#c6cbb0", relieve="#5d5548", acento="#d35400", comarca="#7c7466"),
}


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _limpia(nombre):
    return nombre.split(" / ")[0].split(";")[0].strip()


# papel de cada texto -> (familia, estilo, peso, factor de tamaño)
FUENTES = {
    "alballut": {r: (E.MANO, "normal", "bold", 1.0) for r in
                 ("titulo", "sierra", "comarca", "region", "rio", "lugar", "marca", "perfil",
                  "perfil_titulo")},
    # personal: sans geométrica de trazo uniforme (Poppins, del estilo de Brooklyn)
    "personal": {
        "titulo": ("Poppins", "normal", "semibold", 0.7),
        "sierra": ("Poppins", "normal", "medium", 0.6),
        "comarca": ("Poppins", "normal", "regular", 0.58),
        "region": ("Poppins", "normal", "medium", 0.62),
        "rio": ("Poppins", "italic", "regular", 0.64),
        "lugar": ("Poppins", "normal", "medium", 0.66),
        "marca": ("Poppins", "normal", "medium", 0.7),
        "perfil": ("Poppins", "normal", "regular", 0.66),
        "perfil_titulo": ("Poppins", "normal", "semibold", 0.66),
    },
}
FUENTES["tronos"] = {
    "titulo": ("IM FELL English SC", "normal", "normal", 0.9),
    "sierra": ("IM FELL English SC", "normal", "normal", 0.4),
    "comarca": ("IM FELL English SC", "normal", "normal", 0.5),
    "region": ("IM FELL English SC", "normal", "normal", 0.7),
    "rio": ("IM FELL English", "italic", "normal", 0.66),
    "lugar": ("IM FELL English", "normal", "normal", 0.72),
    "marca": ("IM FELL English", "normal", "normal", 0.72),
    "perfil": ("IM FELL English", "normal", "normal", 0.7),
    "perfil_titulo": ("IM FELL English SC", "normal", "normal", 0.72),
}
# nombres geográficos: se agrandan con [mapa] escala_toponimos
TOPONIMOS = {"sierra", "comarca", "region", "rio", "lugar"}


class Lienzo:
    """Mapa en coordenadas de píxel con registro de zonas ocupadas por rótulos.

    `alto_pie` añade una franja bajo el mapa (para el perfil) sin cambiar sus coordenadas.
    """

    def __init__(self, W, H, xmin, ymin, xmax, ymax, colores, F, alto_pie=0, estilo="alballut",
                 escala_toponimos=1.0):
        self.W, self.H, self.F, self.c = W, H, F, colores
        self.top = escala_toponimos
        self.fuentes = FUENTES.get(estilo, FUENTES["alballut"])
        self.caja = (xmin, ymin, xmax, ymax)
        self.alto_pie = alto_pie
        self.fig = plt.figure(figsize=(W / 100, (H + alto_pie) / 100), dpi=100)
        self.ax = self.fig.add_axes([0, alto_pie / (H + alto_pie), 1, H / (H + alto_pie)])
        self.ax.set_xlim(0, W)
        self.ax.set_ylim(0, H)
        self.ax.axis("off")
        self.fig.patch.set_facecolor(colores["papel"])
        self.ocupado = []                       # rectángulos (x0, y0, x1, y1)
        self.res = 6                            # resolución de la máscara del track
        self.mascara = np.zeros((H // self.res + 1, W // self.res + 1), bool)
        self.render = self.fig.canvas.get_renderer()
        self.agua = None

    def px(self, lon, lat):
        xmin, ymin, xmax, ymax = self.caja
        x, y = a_mercator(lon, lat)
        return (x - xmin) / (xmax - xmin) * self.W, (y - ymin) / (ymax - ymin) * self.H

    def marcar_track(self, x, y, grosor=14):
        r = max(1, grosor // self.res)
        ix = np.clip((np.asarray(x) / self.res).astype(int), 0, self.mascara.shape[1] - 1)
        iy = np.clip((np.asarray(y) / self.res).astype(int), 0, self.mascara.shape[0] - 1)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                self.mascara[np.clip(iy + dy, 0, self.mascara.shape[0] - 1),
                             np.clip(ix + dx, 0, self.mascara.shape[1] - 1)] = True

    def pisa_track(self, r):
        x0, y0, x1, y1 = (int(v / self.res) for v in r)
        x0, y0 = max(x0, 0), max(y0, 0)
        return self.mascara[y0:y1 + 1, x0:x1 + 1].mean() if x1 > x0 and y1 > y0 else 0

    def libre(self, r, margen=4, track_max=0.0):
        x0, y0, x1, y1 = r
        if x0 < 8 or y0 < 8 or x1 > self.W - 8 or y1 > self.H - 8:
            return False
        for a in self.ocupado:
            if not (x1 + margen < a[0] or x0 - margen > a[2] or y1 + margen < a[1] or y0 - margen > a[3]):
                return False
        return self.pisa_track(r) <= track_max

    def en_agua(self, x, y, radio=25):
        if self.agua is None:
            return False
        fy, fx = self.agua.shape[0] / self.H, self.agua.shape[1] / self.W
        y0, y1 = int(max(0, (y - radio) * fy)), int(min(self.agua.shape[0], (y + radio) * fy + 1))
        x0, x1 = int(max(0, (x - radio) * fx)), int(min(self.agua.shape[1], (x + radio) * fx + 1))
        return bool((self.agua[y0:y1, x0:x1] > 0.3).any())

    def mayus(self, texto):
        """Al-Ballut rotula en mayúsculas; el estilo personal, en mayúsculas y minúsculas."""
        return texto.upper() if self.fuentes is FUENTES["alballut"] else texto

    def letra(self, rol, tam):
        """Parámetros de texto (familia, estilo, peso y tamaño) para un papel dado."""
        familia, estilo, peso, factor = self.fuentes[rol]
        if rol in TOPONIMOS:
            factor *= self.top
        return dict(fontsize=tam * factor, family=familia, style=estilo, weight=peso)

    def ajustar_pie(self, alto_pie):
        """Cambia el alto de la franja inferior sin mover nada del mapa."""
        self.alto_pie = alto_pie
        total = self.H + alto_pie
        self.fig.set_size_inches(self.W / 100, total / 100)
        self.ax.set_position([0, alto_pie / total, 1, self.H / total])
        self.render = self.fig.canvas.get_renderer()

    def medir(self, texto, **kw):
        t = self.ax.text(0, 0, texto, **kw)
        bb = t.get_window_extent(renderer=self.render)
        t.remove()
        return bb.width, bb.height

    def halo(self, ancho=4):
        if getattr(self, "tronos", False):      # sobre el relieve oscuro hace falta un halo más claro y ancho
            # doble: uno ancho y suave que aclara el fondo (bosques, umbrías) y otro estrecho y opaco que perfila la letra
            return [pe.withStroke(linewidth=ancho * 2.6 * self.F ** 0.5, foreground="#f3ecd4", alpha=0.55),
                    pe.withStroke(linewidth=ancho * 1.5 * self.F ** 0.5, foreground="#f6f0da", alpha=1.0)]
        return [pe.withStroke(linewidth=ancho * self.F ** 0.5, foreground=self.c["papel"])]


# ------------------------------------------------------------------ fondo

def _ondula(poligono, amplitud, rng, n=500):
    """Deforma el contorno de un polígono con ruido suave para darle aspecto orgánico."""
    anillo = np.asarray(poligono.exterior.coords)
    d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(anillo, axis=0).T))])
    t = np.linspace(0, d[-1], n)
    x, y = np.interp(t, d, anillo[:, 0]), np.interp(t, d, anillo[:, 1])
    ang = t / d[-1] * 2 * np.pi
    ruido = sum(rng.uniform(0.3, 1) / k * np.sin(k * ang + rng.uniform(0, 6.3))
                for k in (3, 5, 8, 13, 21, 34))
    ruido = ruido / np.abs(ruido).max() * amplitud
    dx, dy = np.gradient(x), np.gradient(y)
    norma = np.hypot(dx, dy) + 1e-9
    return np.c_[x - dy / norma * ruido, y + dx / norma * ruido]


def _tierra(lz, TX, TY, rng, manchas=True, alfa=1.0):
    linea = LineString(np.c_[TX, TY]).simplify(4)
    R = 0.085 * min(lz.W, lz.H)
    for factor, color, a in ((1.25, lz.c["tierra"][0], 0.9), (0.6, lz.c["tierra"][1], 0.55)):
        zona = linea.buffer(R * factor, resolution=24)
        for g in getattr(zona, "geoms", [zona]):
            lz.ax.add_patch(Polygon(_ondula(g, R * 0.28 * factor, rng), closed=True, fc=color,
                                    ec="none", alpha=a * alfa, zorder=1))
    if not manchas:
        return
    for _ in range(int(len(TX) / 900) + 8):
        i = rng.integers(0, len(TX))
        ang = rng.uniform(0, 2 * np.pi)
        dist = rng.uniform(0.3, 1.4) * R
        cx, cy = TX[i] + np.cos(ang) * dist, TY[i] + np.sin(ang) * dist
        r = rng.uniform(0.08, 0.22) * R
        circulo = LineString([(cx, cy), (cx + 0.1, cy)]).buffer(r)
        lz.ax.add_patch(Polygon(_ondula(circulo, r * 0.35, rng, 120), closed=True,
                                fc=lz.c["manchas"], ec="none", alpha=0.55 * alfa, zorder=1.2))


def _papel(lz, rng):
    """Textura de papel: grano suave y bordes ligeramente oscurecidos."""
    h, w = lz.H // 4, lz.W // 4
    grano = rng.normal(0, 1, (h, w))
    img = Image.fromarray(((grano - grano.min()) / np.ptp(grano) * 255).astype(np.uint8))
    grano = np.asarray(img.filter(ImageFilter.GaussianBlur(1.2))) / 255.0
    yy, xx = np.mgrid[0:h, 0:w]
    borde = np.hypot((xx / w - 0.5) * 2, (yy / h - 0.5) * 2) / np.sqrt(2)
    oscuro = np.clip(grano * 0.5 + borde ** 3 * 0.9, 0, 1)
    rgba = np.zeros((h, w, 4))
    rgba[..., :3] = np.array(lz.c.get("grano", (0.35, 0.28, 0.18)))
    rgba[..., 3] = oscuro * (0.09 if getattr(lz, "tronos", False) else 0.13)
    lz.ax.imshow(rgba, extent=(0, lz.W, 0, lz.H), zorder=0.5, interpolation="bilinear")


def _agua(lz):
    """Mar, embalses y lagos a partir del color del agua en las teselas OSM estándar."""
    from scipy import ndimage
    xmin, ymin, xmax, ymax = lz.caja
    z = zoom_para(xmin, xmax, lz.W / 2.5, "osm")
    img = mapa_base(xmin, ymin, xmax, ymax, z, "osm").resize((lz.W // 3, lz.H // 3))
    a = np.asarray(img).astype(int)
    agua = (np.abs(a - [170, 211, 223]).sum(axis=2) < 18).astype(np.uint8) * 255
    mascara = Image.fromarray(agua)
    # cierre (dilatar + erosionar): elimina fronteras, rutas de ferri y rótulos dibujados en el mar
    mascara = mascara.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    # apertura: quita embalses y ríos diminutos
    mascara = mascara.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    # islotes de "tierra" dentro del mar (restos de rótulos) y charcas sueltas: fuera
    m_bin = np.asarray(mascara) > 127
    minimo = m_bin.size * 0.0004
    etq, n = ndimage.label(~m_bin)
    tam = ndimage.sum(np.ones_like(etq), etq, range(1, n + 1))
    m_bin |= np.isin(etq, np.flatnonzero(tam < minimo) + 1)
    etq, n = ndimage.label(m_bin)
    tam = ndimage.sum(np.ones_like(etq), etq, range(1, n + 1))
    m_bin &= ~np.isin(etq, np.flatnonzero(tam < minimo * 0.15) + 1)
    suave = Image.fromarray(m_bin.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(3))
    m = np.asarray(suave)[::-1] / 255.0
    lz.agua = m
    if m.max() < 0.5:
        return
    xs = np.linspace(0, lz.W, m.shape[1])
    ys = np.linspace(0, lz.H, m.shape[0])
    lz.ax.contourf(xs, ys, m, levels=[0.5, 1.01], colors=[lz.c["agua"]], zorder=2)
    cs = lz.ax.contour(xs, ys, m, levels=[0.5], colors=[lz.c["agua_borde"]],
                       linewidths=1.4 * lz.F ** 0.5, zorder=2.1)
    cs.set_sketch_params(*BOCETO)
    # líneas de costa repetidas, como en los mapas dibujados
    for nivel, alfa in ((0.78, 0.6), (0.93, 0.35)):
        cs = lz.ax.contour(xs, ys, m, levels=[nivel], colors=[lz.c["agua_borde"]], linewidths=0.8,
                           alpha=alfa, zorder=2.1)
        cs.set_sketch_params(*BOCETO)


# ------------------------------------------------------------------ relieve dibujado

def _elevacion(lz, divisor=6):
    """Rejilla de altitudes (m) del encuadre, desde las teselas Terrarium (AWS, dominio público)."""
    xmin, ymin, xmax, ymax = lz.caja
    z = min(11, zoom_para(xmin, xmax, lz.W / 3, "terreno"))
    img = np.asarray(mapa_base(xmin, ymin, xmax, ymax, z, "terreno")).astype(float)
    ele = img[..., 0] * 256 + img[..., 1] + img[..., 2] / 256 - 32768
    return np.asarray(Image.fromarray(ele.astype(np.float32)).resize((lz.W // divisor, lz.H // divisor),
                                                                     Image.BILINEAR))[::-1]


def _relieve(lz, rng, densidad=1.0):
    """Montañas dibujadas a mano donde el terreno se eleva sobre su entorno, y curvas de nivel."""
    from scipy import ndimage
    ele = _elevacion(lz)
    ele = np.where(ele < -50, 0, ele)
    gh, gw = ele.shape
    fx, fy = lz.W / gw, lz.H / gh
    suave = ndimage.gaussian_filter(ele, 1.2)
    entorno = ndimage.gaussian_filter(ele, max(gw, gh) * 0.035)
    rugosidad = ndimage.generic_filter(suave, np.std, size=5)
    resalte = suave - entorno

    # curvas de nivel a mano alzada (pocas y suaves)
    niveles = [n for n in (600, 1000, 1400, 1800, 2200) if ele.max() > n + 150]
    if niveles:
        xs, ys = np.arange(gw) * fx, np.arange(gh) * fy
        cs = lz.ax.contour(xs, ys, ndimage.gaussian_filter(ele, 2.5), levels=niveles,
                           colors=[lz.c["relieve"]], linewidths=0.9, alpha=0.28, zorder=1.6)
        cs.set_sketch_params(1.2, 60, 3)

    # montañas: una rejilla con jitter; se dibuja donde hay resalte y rugosidad
    paso = 34 * lz.F ** 0.5 / densidad
    lineas, sombras = [], []
    umbral = np.percentile(rugosidad, 65)
    for y in np.arange(paso, lz.H - paso, paso * 0.86):
        desfase = (paso / 2) if int(y / paso) % 2 else 0
        for x in np.arange(paso + desfase, lz.W - paso, paso):
            jx, jy = x + rng.uniform(-0.3, 0.3) * paso, y + rng.uniform(-0.3, 0.3) * paso
            i, j = int(jy / fy), int(jx / fx)
            if not (0 <= i < gh and 0 <= j < gw):
                continue
            r, rug = resalte[i, j], rugosidad[i, j]
            if r < 60 or rug < umbral or lz.en_agua(jx, jy, 10):
                continue
            caja = (jx - paso * 0.4, jy - 4, jx + paso * 0.4, jy + paso * 0.6)
            if lz.pisa_track(caja) > 0 or any(not (caja[2] < a[0] or caja[0] > a[2] or caja[3] < a[1]
                                                   or caja[1] > a[3]) for a in lz.ocupado):
                continue
            fuerza = np.clip((r - 40) / 350, 0, 1) * 0.6 + np.clip(rug / (umbral * 4), 0, 1) * 0.4
            ancho = paso * (0.45 + 0.5 * fuerza)
            alto = ancho * (0.55 + 0.45 * fuerza)
            cima = jx + rng.uniform(-0.12, 0.12) * ancho
            lineas.append([(jx - ancho / 2, jy), (cima, jy + alto), (jx + ancho / 2, jy)])
            # sombreado: rayas en la ladera derecha
            for k in (0.3, 0.55, 0.8):
                xa = cima + (jx + ancho / 2 - cima) * k
                ya = jy + alto * (1 - k)
                sombras.append([(xa, ya), (xa - ancho * 0.12, jy + alto * (1 - k) * 0.25)])
    if lineas:
        lc = LineCollection(lineas, colors=lz.c["relieve"], linewidths=1.5 * lz.F ** 0.4,
                            capstyle="round", joinstyle="round", zorder=1.7, alpha=0.85)
        lc.set_sketch_params(0.6, 30, 2)
        lz.ax.add_collection(lc)
        lz.ax.add_collection(LineCollection(sombras, colors=lz.c["relieve"], linewidths=0.9,
                                            alpha=0.55, zorder=1.7))


# ------------------------------------------------------------------ geografía

def _rios(lz, rios, maximo):
    candidatos = []
    for nombre, tramos in rios.items():
        partes, largo = [], 0.0
        for t in tramos:
            lat, lon = np.array(t).T
            x, y = lz.px(lon, lat)
            dentro = (x > 0) & (x < lz.W) & (y > 0) & (y < lz.H)
            if dentro.sum() < 2:
                continue
            partes.append((x, y))
            largo += np.hypot(np.diff(x[dentro]), np.diff(y[dentro])).sum()
        if partes:
            candidatos.append((largo, _limpia(nombre), partes))
    candidatos.sort(key=lambda c: -c[0])
    elegidos = [c for c in candidatos[:maximo] if c[0] > 0.04 * lz.W]
    cauces = []
    for largo, nombre, partes in elegidos:
        grosor = (1.3 + 1.2 * min(1, largo / lz.W)) * lz.F ** 0.5
        for x, y in partes:
            ln, = lz.ax.plot(x, y, color=lz.c["rio"], lw=grosor, solid_capstyle="round", zorder=2.5)
            ln.set_sketch_params(0.6, 60, 2)
            cauces.append((x, y))
    # rótulos a lo largo del cauce, lejos del track
    for largo, nombre, partes in elegidos:
        x = np.concatenate([p[0] for p in partes])
        y = np.concatenate([p[1] for p in partes])
        texto = lz.mayus(nombre)
        orden = np.argsort(np.abs(np.arange(len(x)) - len(x) / 2))   # empieza por el centro
        hecho = False
        for red in REDUCCIONES:                    # si no cabe, se prueba más pequeño
            kw = dict(**lz.letra("rio", 17 * lz.F * red), color=lz.c["rio_texto"])
            w, h = lz.medir(texto, **kw)
            for i in orden[::3]:
                j0, j1 = max(0, i - 8), min(len(x) - 1, i + 8)
                ang = np.degrees(np.arctan2(y[j1] - y[j0], x[j1] - x[j0]))
                if ang > 90:
                    ang -= 180
                if ang < -90:
                    ang += 180
                cx, cy = x[i], y[i] + 8 * lz.F
                s = abs(np.sin(np.radians(ang)))
                r = (cx - w / 2, cy - w / 2 * s - h / 2, cx + w / 2, cy + w / 2 * s + h / 2)
                if lz.libre(r, track_max=0.02):
                    lz.ax.text(cx, cy, texto, rotation=ang, rotation_mode="anchor", ha="center",
                               va="center", zorder=3, path_effects=lz.halo(3), **kw)
                    lz.ocupado.append(r)
                    hecho = True
                    break
            if hecho:
                break
    return cauces


def _montes(lz, ancho, x, y, zorder=3):
    """Tres picos dibujados a mano centrados en (x, y)."""
    for dx, alto in ((-0.33, 0.7), (0, 1.0), (0.3, 0.6)):
        a = ancho * 0.28
        px_ = x + dx * ancho
        ln, = lz.ax.plot([px_ - a, px_, px_ + a], [y, y + alto * ancho * 0.45, y],
                         color=lz.c["relieve"], lw=1.4 * lz.F ** 0.5, zorder=zorder,
                         solid_joinstyle="round")
        ln.set_sketch_params(0.8, 40, 2)


def _rotulo_apilado(lz, nombre, tam):
    """SIERRA / de la / BARCA: palabras grandes y conectores pequeños en líneas separadas."""
    palabras = _limpia(nombre).split()
    lineas, actual_con = [], []
    for p in palabras:
        if p.lower() in CONECTORES:
            actual_con.append(p.lower())
        else:
            if actual_con:
                lineas.append((" ".join(actual_con), tam * 0.55))
                actual_con = []
            lineas.append((p.upper(), tam))
    if len(lineas) > 5:            # nombres muy largos: en una línea
        lineas = [(_limpia(nombre).upper(), tam * 0.8)]
    if lz.fuentes is FUENTES["personal"]:      # versalitas: «Sierra de la Barca» en una o dos líneas
        lineas = [(_limpia(nombre), tam)]
    medidas = [lz.medir(t, **lz.letra("sierra", s)) for t, s in lineas]
    alto = sum(m[1] * 0.95 for m in medidas)
    ancho = max(m[0] for m in medidas)
    return lineas, medidas, ancho, alto


def _sierras(lz, sierras, maximo, TX, TY):
    vistos = set()
    candidatas = []
    for s_ in sierras:
        clave = _norm(s_["nombre"])
        if clave in vistos or not clave:
            continue
        vistos.add(clave)
        x, y = lz.px(s_["lon"], s_["lat"])
        if not (0.03 * lz.W < x < 0.97 * lz.W and 0.03 * lz.H < y < 0.97 * lz.H):
            continue
        dist = np.min(np.hypot(TX[::20] - x, TY[::20] - y))
        if dist < 0.25 * min(lz.W, lz.H):
            candidatas.append((dist, s_, x, y))
    colocadas = 0
    tronos = getattr(lz, "tronos", False)
    paso = 0.03 * min(lz.W, lz.H)
    # cerca de su sitio (como mucho dos pasos): más lejos, el rótulo acaba en otra sierra o al otro lado de un río
    desplazamientos = [(0, 0)] + [(np.cos(a) * k * paso, np.sin(a) * k * paso)
                                  for k in (0.5, 1, 1.5, 2)
                                  for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
    for dist, s_, x, y in sorted(candidatas, key=lambda c: c[0]):
        if colocadas >= maximo:
            break
        extra = 0 if tronos else 30 * lz.F        # sitio para los montecitos bajo el nombre
        sitio = None
        # apilado («SIERRA / de / SAN PEDRO») y, si no cabe, en una línea; cada uno, cada vez más pequeño
        for red in REDUCCIONES + (0.5,):
            for apilado in (True, False):
                if apilado:
                    lineas, medidas, ancho, alto = _rotulo_apilado(lz, s_["nombre"], 24 * lz.F * red)
                else:
                    t = lz.mayus(_limpia(s_["nombre"]))
                    tam = 24 * lz.F * red * 0.75
                    w, h = lz.medir(t, **lz.letra("sierra", tam))
                    lineas, medidas, ancho, alto = [(t, tam)], [(w, h)], w, h
                for dx, dy in desplazamientos:
                    cx, cy = x + dx, y + dy
                    r = (cx - ancho / 2, cy - alto / 2, cx + ancho / 2, cy + alto / 2 + extra)
                    if lz.libre(r, margen=14 if red > 0.6 else 8, track_max=0.0):
                        sitio = r
                        break
                if sitio:
                    break
            if sitio:
                break
        if not sitio:
            continue
        yy = cy + alto / 2
        for (t, s2), (w, h) in zip(lineas, medidas):
            yy -= h * 0.95
            lz.ax.text(cx, yy + h * 0.45, t, **lz.letra("sierra", s2),
                       color=lz.c["relieve"] if tronos else lz.c["tinta"], ha="center", va="center", zorder=4,
                       path_effects=lz.halo(3))
        if not tronos:
            _montes(lz, 30 * lz.F, cx, cy + alto / 2 + 4 * lz.F)
        lz.ocupado.append(sitio)
        colocadas += 1


def _espaciado(texto):
    return "  ".join(" ".join(p) for p in texto.upper().split())


def _regiones(lz, regiones):
    for reg in regiones:
        x, y = lz.px(reg["lon"], reg["lat"])
        texto = _espaciado(_limpia(reg["nombre"]))
        kw = dict(**lz.letra("region", 22 * lz.F), color=lz.c["comarca"], alpha=0.5)
        w, h = lz.medir(texto, **kw)
        r = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
        if lz.libre(r, margen=20):
            lz.ax.text(x, y, texto, ha="center", va="center", zorder=2.8, **kw)
            lz.ocupado.append(r)


def _comarcas(lz, comarcas, maximo, TX, TY):
    """Nombres de comarca en versalitas espaciadas, cerca de la ruta."""
    candidatas = []
    for c in comarcas:
        x, y = lz.px(c["lon"], c["lat"])
        if 0.04 * lz.W < x < 0.96 * lz.W and 0.04 * lz.H < y < 0.96 * lz.H:
            candidatas.append((np.min(np.hypot(TX[::20] - x, TY[::20] - y)), c, x, y))
    paso = 0.025 * min(lz.W, lz.H)
    desplazamientos = [(0, 0)] + [(np.cos(a) * k * paso, np.sin(a) * k * paso)
                                  for k in (1, 2, 3) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
    puestas = 0
    for _, c, x, y in sorted(candidatas, key=lambda t: t[0]):
        if puestas >= maximo:
            break
        texto = _espaciado(c["nombre"])
        kw = dict(**lz.letra("comarca", 15 * lz.F), color=lz.c["comarca"])
        w, h = lz.medir(texto, **kw)
        for dx, dy in desplazamientos:
            r = (x + dx - w / 2, y + dy - h / 2, x + dx + w / 2, y + dy + h / 2)
            if lz.libre(r, margen=10, track_max=0.03):
                lz.ax.text(x + dx, y + dy, texto, ha="center", va="center", zorder=2.9,
                           path_effects=lz.halo(3), **kw)
                lz.ocupado.append(r)
                puestas += 1
                break


def _embalses(lz, embalses, maximo):
    hechos = 0
    for e in sorted(embalses, key=lambda e: -e["tam_km"]):
        if hechos >= maximo or e["tam_km"] < 0.8:
            break
        x, y = lz.px(e["lon"], e["lat"])
        if not (0 < x < lz.W and 0 < y < lz.H):
            continue
        nombre = re.sub(r"^(Embalse|Pantano)\s+(de\s+|del\s+)?", "Emb. ", _limpia(e["nombre"]))
        texto = lz.mayus(nombre)
        hecho = False
        for red in REDUCCIONES:
            kw = dict(**lz.letra("rio", 13 * lz.F * red), color=lz.c["rio_texto"])
            w, h = lz.medir(texto, **kw)
            for dx, dy in ((0, -h * 1.1), (0, h * 1.1), (w * 0.6, 0), (-w * 0.6, 0),
                           (0, -h * 2.2), (0, h * 2.2)):
                r = (x + dx - w / 2, y + dy - h / 2, x + dx + w / 2, y + dy + h / 2)
                if lz.libre(r, margen=6, track_max=0.05):
                    lz.ax.text(x + dx, y + dy, texto, ha="center", va="center", zorder=3,
                               path_effects=lz.halo(3), **kw)
                    lz.ocupado.append(r)
                    hechos += 1
                    hecho = True
                    break
            if hecho:
                break


def _cumbres(lz, cimas, maximo):
    puestos = []
    for c in sorted(cimas, key=lambda c: -(c["ele"] or 0)):
        if len(puestos) >= maximo:
            break
        x, y = lz.px(c["lon"], c["lat"])
        if any(np.hypot(x - a, y - b) < 0.1 * lz.W for a, b in puestos):
            continue
        texto = f"{c['ele']:.0f}\n{lz.mayus(_limpia(c['nombre']))}"
        kw = dict(**lz.letra("lugar", 13 * lz.F), color=lz.c["tinta"], linespacing=0.95)
        w, h = lz.medir(texto, **kw)
        sep = 8 * lz.F
        r = (x - w / 2, y + sep, x + w / 2, y + sep + h)
        if not lz.libre(r, track_max=0.05):
            continue
        lz.ax.plot(x, y, marker="^", ms=8 * lz.F, color=lz.c["tinta"], zorder=6)
        lz.ax.text(x, y + sep, texto, ha="center", va="bottom", zorder=6, path_effects=lz.halo(3), **kw)
        lz.ocupado.append(r)
        puestos.append((x, y))


def _puertos(lz, puertos):
    hechos = set()
    for p in puertos:
        clave = _norm(p["nombre"])
        if clave in hechos:
            continue
        hechos.add(clave)
        x, y = lz.px(p["lon"], p["lat"])
        nombre = lz.mayus(_limpia(p["nombre"])).replace("PUERTO ", "PTO. ").replace("Puerto ", "Pto. ")
        texto = f"{nombre} · {p['ele']:.0f}" if p["ele"] else nombre
        kw = dict(**lz.letra("lugar", 14 * lz.F), color="#5a3d1e")
        w, h = lz.medir(texto, **kw)
        s = 12 * lz.F
        for dx, dy, ha in ((s, 0, "left"), (-s, 0, "right"), (0, s, "center"), (0, -s, "center")):
            x0 = x + dx if ha == "left" else x + dx - w if ha == "right" else x - w / 2
            r = (x0, y + dy - h / 2, x0 + w, y + dy + h / 2)
            if lz.libre(r, track_max=0.15):
                lz.ax.plot(x, y, marker="^", ms=8 * lz.F, mfc="#5a3d1e", mec="white", mew=1, zorder=7)
                lz.ax.text(x + dx, y + dy, texto, ha=ha, va="center", zorder=7,
                           path_effects=lz.halo(3), **kw)
                lz.ocupado.append(r)
                break


# ------------------------------------------------------------------ lugares de la ruta

def _lugares(plan, separacion_km=1.5):
    """Agrupa los puntos de la hoja que son el mismo sitio (ida y vuelta)."""
    lugares = []
    for p in plan.puntos:
        num = p.control[1:] if p.control else ""
        for l in lugares:
            d = np.hypot((p.lat - l["lat"]) * 111, (p.lon - l["lon"]) * 111 * np.cos(np.radians(p.lat)))
            mismo_nombre = _norm(p.nombre).split()[0] == _norm(l["nombre"]).split()[0]
            if d < separacion_km or (mismo_nombre and d < 8 * separacion_km):
                if p.es_control and not l["control"]:       # el nombre del control manda
                    l["nombre"] = p.nombre
                elif mismo_nombre and len(p.nombre) < len(l["nombre"]):
                    l["nombre"] = p.nombre                  # el más corto ("Tórtoles")
                l["control"] = l["control"] or p.es_control
                if p.extra.get("mostrar") is not None:   # elección en el Planificador de VenB
                    l["mostrar"] = l.get("mostrar") or p.extra["mostrar"]
                if num:
                    l["numeros"].append(num)
                break
        else:
            lugares.append({"nombre": p.nombre, "lat": p.lat, "lon": p.lon,
                            "control": p.es_control, "km": p.km, "numeros": [num] if num else [],
                            # las hojas por líneas distinguen localidades de indicaciones
                            "localidad": p.extra.get("localidad", True),
                            # None = decide el generador; True/False = elegido en el Planificador
                            "mostrar": p.extra.get("mostrar")})
    return lugares


DESCRIPTIVOS = re.compile(r"\b(cruce|circunvalacion|giro|rotonda|desvio|enlace|salida|km|interseccion)\b")


def _seleccion_lugares(lz, lugares, maximo, separacion):
    """Salida y controles siempre; de los demás, solo localidades y bien repartidas.

    Se eligen por "punto más lejano": cada nuevo lugar es el más alejado de los ya elegidos,
    hasta `maximo` o hasta que quede a menos de `separacion` (fracción del lado corto).
    """
    fijos = [lugares[0]] + [l for l in lugares[1:] if l["control"] or l.get("mostrar")]
    resto = [l for l in lugares[1:] if not l["control"] and l.get("mostrar") is None and l.get("localidad", True)
             and not DESCRIPTIVOS.search(_norm(l["nombre"]))]
    pos = lambda l: np.array(lz.px(l["lon"], l["lat"]))
    elegidos = list(fijos)
    minimo = separacion * min(lz.W, lz.H)
    while resto and len(elegidos) - len(fijos) < maximo:
        dist = [min(np.hypot(*(pos(l) - pos(e))) for e in elegidos) for l in resto]
        i = int(np.argmax(dist))
        if dist[i] < minimo:
            break
        elegidos.append(resto.pop(i))
    return [l for l in lugares if any(l is e for e in elegidos)]


def _rotular_lugar(lz, x, y, texto, tam, peso_track=0.25, sep_extra=0):
    kw = dict(**lz.letra("lugar", tam), color=lz.c.get("lugar", lz.c["tinta"]))
    w, h = lz.medir(texto, **kw)
    sep = 10 * lz.F + tam * 0.2 + sep_extra
    opciones = [(sep, 0, "left", "center"), (-sep, 0, "right", "center"),
                (0, sep, "center", "bottom"), (0, -sep, "center", "top"),
                (sep * 0.8, sep * 0.8, "left", "bottom"), (-sep * 0.8, sep * 0.8, "right", "bottom"),
                (sep * 0.8, -sep * 0.8, "left", "top"), (-sep * 0.8, -sep * 0.8, "right", "top")]
    mejor = None
    for dx, dy, ha, va in opciones:
        x0 = x + dx if ha == "left" else x + dx - w if ha == "right" else x + dx - w / 2
        y0 = y + dy if va == "bottom" else y + dy - h if va == "top" else y + dy - h / 2
        r = (x0, y0, x0 + w, y0 + h)
        if lz.libre(r, margen=3, track_max=1.0):
            pisa = lz.pisa_track(r)
            if mejor is None or pisa < mejor[0]:
                mejor = (pisa, dx, dy, ha, va, r)
            if pisa == 0:
                break
    if mejor is None or mejor[0] > peso_track:
        return False
    _, dx, dy, ha, va, r = mejor
    lz.ax.text(x + dx, y + dy, texto, ha=ha, va=va, zorder=12, path_effects=lz.halo(5), **kw)
    lz.ocupado.append(r)
    return True


def _numeros_texto(numeros):
    """«1», «1 y 4», «1, 4 y 7»: con «·» los controles 1 y 4 se leían «14»."""
    n = list(dict.fromkeys(numeros))
    return " y ".join(n) if len(n) < 3 else ", ".join(n[:-1]) + " y " + n[-1]


def _marca_numerada(lz, x, y, numeros, grande=False):
    """Círculo con el número del control; si se pasa varias veces, píldora con «2 y 12»."""
    texto = _numeros_texto(numeros)
    tam = (15 if grande else 12) * lz.F
    w, h = lz.medir(texto, fontsize=tam, family=E.SANS, weight="bold")
    r = max(w, h) / 2 + 6 * lz.F
    lw = 2.5 * lz.F ** 0.5
    if len(set(numeros)) > 1:      # píldora: no se agranda en vertical
        alto = h / 2 + 6 * lz.F
        ancho = max(w / 2 + 9 * lz.F, alto)
        lz.ax.add_patch(FancyBboxPatch((x - ancho, y - alto), 2 * ancho, 2 * alto,
                                       boxstyle=f"round,pad=0,rounding_size={alto}", mutation_aspect=1,
                                       fc=lz.c["acento"], ec="white", lw=lw, zorder=13))
        r, ry = ancho, alto
    else:
        lz.ax.add_patch(Circle((x, y), r, fc=lz.c["acento"], ec="white", lw=lw, zorder=13))
        ry = r
    lz.ax.text(x, y, texto, fontsize=tam, family=E.SANS, weight="bold", color="white",
               ha="center", va="center", zorder=14)
    lz.ocupado.append((x - r, y - ry, x + r, y + ry))
    return r


# ------------------------------------------------------------------ pueblos y árboles dibujados

def _mezcla(c1, c2, t):
    """Color entre c1 y c2 (t = 0 → c1)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _poligono(lz, puntos, fc, z, lw=None):
    p = Polygon(puntos, closed=True, fc=fc, ec=lz.c["tinta"], lw=lw or 1.1 * lz.F ** 0.45,
                joinstyle="round", zorder=z)
    p.set_sketch_params(0.35, 25, 1.5)
    lz.ax.add_patch(p)


def _casa(lz, x, y, w, h, z):
    """Casita: muro y tejado a dos aguas, con la base en (x, y) y centrada en x."""
    tejado = lz.c.get("tejado", "#b8644a")
    _poligono(lz, [(x - w / 2, y), (x + w / 2, y), (x + w / 2, y + h), (x - w / 2, y + h)], lz.c["papel"], z)
    _poligono(lz, [(x - w * 0.62, y + h), (x, y + h + w * 0.5), (x + w * 0.62, y + h)], tejado, z + 0.01)


def _torre(lz, x, y, w, h, castillo, z):
    """Torre almenada (castillo) o campanario con chapitel, con la base en (x, y)."""
    _poligono(lz, [(x - w / 2, y), (x + w / 2, y), (x + w / 2, y + h), (x - w / 2, y + h)], lz.c["papel"], z)
    if castillo:
        a = w / 5
        almenas = [(x - w / 2, y + h)]
        for i in range(5):
            x0 = x - w / 2 + i * a
            alto = y + h + (a * 0.9 if i % 2 == 0 else 0)
            almenas += [(x0, alto), (x0 + a, alto)]
        almenas += [(x + w / 2, y + h)]
        _poligono(lz, almenas, lz.c["papel"], z + 0.01)
        lz.ax.add_patch(Polygon([(x - w * 0.12, y), (x - w * 0.12, y + h * 0.3), (x, y + h * 0.38),
                                 (x + w * 0.12, y + h * 0.3), (x + w * 0.12, y)], fc=lz.c["tinta"], ec="none", zorder=z + 0.02))
    else:
        _poligono(lz, [(x - w * 0.6, y + h), (x, y + h + w * 1.3), (x + w * 0.6, y + h)], lz.c.get("tejado", "#b8644a"), z + 0.01)
        lz.ax.add_patch(Circle((x, y + h * 0.75), w * 0.16, fc=lz.c["tinta"], ec="none", zorder=z + 0.02))


def _dibujo_pueblo(lz, x, y, tam, castillo, rng):
    """Pueblo en miniatura: una torre o un castillo entre casitas. (x, y) es el centro de la base.
    Devuelve la caja que ocupa."""
    z = 8.5
    if castillo:
        _torre(lz, x - tam * 0.42, y, tam * 0.24, tam * 0.5, True, z)
        _torre(lz, x + tam * 0.42, y, tam * 0.24, tam * 0.5, True, z)
        _poligono(lz, [(x - tam * 0.3, y), (x + tam * 0.3, y), (x + tam * 0.3, y + tam * 0.36), (x - tam * 0.3, y + tam * 0.36)],
                  lz.c["papel"], z - 0.05)
        _torre(lz, x, y + tam * 0.02, tam * 0.3, tam * 0.66, True, z + 0.1)
    else:
        _torre(lz, x + rng.uniform(-0.1, 0.1) * tam, y + tam * 0.12, tam * 0.2, tam * 0.5, False, z - 0.1)
    for dx, esc in ((-0.33, 0.8), (0.3, 0.7), (0.0, 0.9)) if not castillo else ((-0.2, 0.55), (0.25, 0.5)):
        w = tam * 0.3 * esc
        _casa(lz, x + dx * tam, y - (0.02 if castillo else 0) * tam, w, w * 0.7, z + 0.2)
    return (x - tam * 0.62, y - 2, x + tam * 0.62, y + tam * (0.95 if castillo else 0.98))


def _hueco_cerca(lz, x, y, ancho, alto, dist, track_max=0.0):
    """Caja libre de ancho×alto junto a (x, y), a `dist` píxeles o algo más; devuelve su base (cx, cy) o None."""
    for f in (1.0, 1.35, 1.75):
        for ang in np.radians([90, 45, 135, 0, 180, 315, 225, 270]):
            cx = x + np.cos(ang) * dist * f
            cy = y + np.sin(ang) * dist * f - (alto if np.sin(ang) < -0.1 else alto / 2 if abs(np.sin(ang)) < 0.1 else 0)
            r = (cx - ancho / 2, cy, cx + ancho / 2, cy + alto)
            if lz.libre(r, margen=3, track_max=track_max) and not lz.en_agua(cx, cy + alto / 2, ancho / 3):
                return cx, cy
    return None


def _pueblos_ruta(lz, lugares, F, rng, castillos):
    """Dibujo de pueblo junto a cada localidad rotulada de la ruta (castillo si OSM tiene uno al lado)."""
    tam = 46 * F ** 0.6
    for k, l in enumerate(lugares):
        if not (k == 0 or l.get("rotulado") or l["control"]) or not l.get("localidad", True) or DESCRIPTIVOS.search(_norm(l["nombre"])):
            continue
        x, y = lz.px(l["lon"], l["lat"])
        hueco = _hueco_cerca(lz, x, y, tam * 1.3, tam, 14 * F ** 0.6 + tam * 0.55)
        if hueco:
            castillo = any(np.hypot(*(np.array(lz.px(c[1], c[0])) - (x, y))) < 40 * F ** 0.5 for c in castillos)
            lz.ocupado.append(_dibujo_pueblo(lz, *hueco, tam, castillo, rng))


def _pueblos_cercanos(lz, pueblos, lugares, maximo, F, rng):
    """Pueblos de OpenStreetMap cerca de la ruta que no son de la hoja: dibujo pequeño y nombre si cabe."""
    if not pueblos or maximo <= 0:
        return
    tam = 36 * F ** 0.6
    ya = [np.array(lz.px(l["lon"], l["lat"])) for l in lugares]
    cand = []
    for p in sorted(pueblos, key=lambda p: (p["tipo"] != "town", not p["castillo"], p["km_ruta"])):
        xy = np.array(lz.px(p["lon"], p["lat"]))
        if not (0.04 * lz.W < xy[0] < 0.96 * lz.W and 0.04 * lz.H < xy[1] < 0.96 * lz.H):
            continue
        if any(np.hypot(*(xy - q)) < 0.05 * min(lz.W, lz.H) for q in ya):
            continue
        cand.append((p, xy))
    minimo, puestos = 0.06 * min(lz.W, lz.H), []
    for p, xy in cand:
        if len(puestos) >= maximo:
            break
        if any(np.hypot(*(xy - q)) < minimo for q in puestos):
            continue
        x, y = xy
        r = (x - tam * 0.62, y - tam * 0.45, x + tam * 0.62, y + tam * 0.6)
        if not lz.libre(r, margen=4, track_max=0.0) or lz.en_agua(x, y, tam / 2):
            continue
        caja = _dibujo_pueblo(lz, x, y - tam * 0.45, tam, p["castillo"], rng)
        lz.ocupado.append(caja)
        puestos.append(xy)
        kw = dict(**lz.letra("lugar", 12 * F), color=lz.c.get("lugar", lz.c["tinta"]), alpha=0.85)
        texto = lz.mayus(_limpia(p["nombre"]))
        w, h = lz.medir(texto, **kw)
        for ty, va in ((caja[1] - 3, "top"), (caja[3] + 3, "bottom")):
            rt = (x - w / 2, ty - h if va == "top" else ty, x + w / 2, ty if va == "top" else ty + h)
            if lz.libre(rt, margen=2, track_max=0.0):
                lz.ax.text(x, ty, texto, ha="center", va=va, zorder=12, path_effects=lz.halo(3), **kw)
                lz.ocupado.append(rt)
                break


def _arbol(lz, x, y, s, rng, conifera=False):
    """Árbol a mano: copa redondeada (o conífera) sobre un tronco corto; (x, y) es el pie."""
    copa = lz.c.get("arbol") or _mezcla(lz.c["manchas"], lz.c["relieve"], 0.35)
    lw = 0.9 * lz.F ** 0.4
    lz.ax.plot([x, x], [y, y + s * 0.4], color=lz.c["relieve"], lw=lw * 1.3, zorder=7.9, solid_capstyle="round")
    if conifera:
        _poligono(lz, [(x - s * 0.36, y + s * 0.3), (x, y + s * 1.25), (x + s * 0.36, y + s * 0.3)], copa, 8, lw)
    else:
        for dx, dy, r in ((0, 0.78, 0.36), (-0.2, 0.62, 0.26), (0.2, 0.64, 0.25)):
            c = Circle((x + dx * s, y + dy * s), r * s, fc=copa, ec=lz.c["tinta"], lw=lw, zorder=8)
            c.set_sketch_params(0.3, 20, 1.5)
            lz.ax.add_patch(c)


def _puentes(lz, TX, TY, cauces, F, grosor_px, maximo=30):
    """Puentecillo donde el track cruza un río dibujado: tablero en la dirección general del track (medida en un
    tramo largo, porque el GPS suele hacer eses al cruzar), más ancho que el track con su halo, y pretiles abiertos
    en los extremos. Se omite si el track cruza el río casi en paralelo."""
    ancho = grosor_px * 2.6
    track = LineString(np.c_[TX, TY]).simplify(grosor_px * 0.7)    # sin el temblor del GPS: queda bajo el tablero
    if track.length == 0:
        return
    largo = max(ancho * 2.0, 30 * F ** 0.5)
    puestos = []
    for x, y in cauces:
        if len(x) < 2:
            continue
        rio = LineString(np.c_[x, y])
        cruce = track.intersection(rio)
        pts = getattr(cruce, "geoms", [cruce]) if not cruce.is_empty else []
        for p in pts:
            if p.geom_type != "Point" or len(puestos) >= maximo:
                continue
            if any(np.hypot(p.x - q[0], p.y - q[1]) < largo * 1.5 for q in puestos):
                continue
            d = track.project(p)
            for L in (largo, largo * 0.8, largo * 0.65, ancho * 1.25):     # si el track curva, un puente más corto
                a, b = track.interpolate(max(d - L / 2, 0)), track.interpolate(min(d + L / 2, track.length))
                extremos = np.array([[a.x, a.y], [b.x, b.y]])
                t = extremos[1] - extremos[0]
                if np.hypot(*t) >= L * 0.8:
                    break
            dr = rio.project(p)
            a, b = rio.interpolate(max(dr - largo * 0.6, 0)), rio.interpolate(min(dr + largo * 0.6, rio.length))
            r = np.array([b.x - a.x, b.y - a.y])
            if np.hypot(*t) < L * 0.8 or np.hypot(*r) < largo * 0.3:     # curva cerrada en el cruce
                continue
            u = t / 2                                      # eje del puente: sus extremos caen sobre el track
            t, r = t / np.hypot(*t), r / np.hypot(*r)
            if abs(t @ r) > 0.8:                           # cruce casi en paralelo al río: no parece un puente
                continue
            v = np.array([-t[1], t[0]]) * ancho / 2        # media anchura
            c = extremos.mean(axis=0)
            # por encima del track: un tramo recto (el tablero) tapa la ese del GPS y el track entra y sale por él
            lz.ax.add_patch(Polygon([c - u - v, c + u - v, c + u + v, c - u + v], closed=True,
                                    fc=lz.c["papel"], ec="none", zorder=10.1))
            w = v * grosor_px / ancho
            lz.ax.add_patch(Polygon([c - u - w, c + u - w, c + u + w, c - u + w], closed=True,
                                    fc=lz.c["tinta"], ec="none", zorder=10.15))
            lw = 1.7 * F ** 0.4
            for lado in (-1, 1):
                o = v * lado
                pre = [c - u * 1.12 + o * 1.7, c - u * 0.82 + o, c + u * 0.82 + o, c + u * 1.12 + o * 1.7]
                lz.ax.plot(*np.array(pre).T, color=lz.c["tinta"], lw=lw, solid_capstyle="round",
                           solid_joinstyle="round", zorder=10.2)
            puestos.append((p.x, p.y))
            lz.ocupado.append((p.x - largo / 2, p.y - largo / 2, p.x + largo / 2, p.y + largo / 2))


def _hueco_arbol(lz, x, y, s):
    r = (x - s * 0.45, y - 1, x + s * 0.45, y + s * 1.25)
    return r if lz.libre(r, margen=1, track_max=0.0) and not lz.en_agua(x, y + s * 0.5, s * 0.3) else None


def _arboles_ribera(lz, cauces, rng, maximo, F):
    """Hileras de árboles a uno y otro lado de los ríos dibujados."""
    s, paso, puestos = 22 * F ** 0.55, 42 * F ** 0.55, 0
    for x, y in cauces:
        d = np.r_[0, np.cumsum(np.hypot(np.diff(x), np.diff(y)))]
        for k, dist in enumerate(np.arange(paso * rng.uniform(0.3, 1), d[-1], paso)):
            if puestos >= maximo:
                return
            if rng.random() < 0.25:
                continue
            i = min(np.searchsorted(d, dist), len(x) - 2)
            tx, ty = x[i + 1] - x[i], y[i + 1] - y[i]
            n = np.hypot(tx, ty) or 1
            lado = 1 if k % 2 else -1
            sep = (13 + rng.uniform(0, 6)) * F ** 0.55
            px_, py_ = x[i] - ty / n * sep * lado, y[i] + tx / n * sep * lado - (s * 0.4 if lado < 0 else 0)
            r = _hueco_arbol(lz, px_, py_, s)
            if r:
                _arbol(lz, px_, py_, s * rng.uniform(0.85, 1.1), rng)
                lz.ocupado.append(r)
                puestos += 1


def _arboles_sueltos(lz, rng, grupos, F):
    """Bosquecillos de 1 a 4 árboles repartidos por el mapa, lejos del track, el agua y los rótulos."""
    s = 25 * F ** 0.55
    puestos = 0
    for _ in range(grupos * 25):
        if puestos >= grupos:
            break
        x, y = rng.uniform(0.04, 0.96) * lz.W, rng.uniform(0.05, 0.92) * lz.H
        conifera = rng.random() < 0.35
        n = int(rng.choice([1, 2, 3, 3, 4]))
        sitios = [(x + rng.uniform(-1, 1) * s * 0.9 * (n > 1), y + rng.uniform(-0.4, 0.4) * s * (n > 1)) for _ in range(n)]
        cajas = []
        for px_, py_ in sorted(sitios, key=lambda p: -p[1]):     # los de detrás, primero
            r = _hueco_arbol(lz, px_, py_, s)
            if r and not any(not (r[2] < c[0] or r[0] > c[2] or r[3] < c[1] or r[1] > c[3]) for c in cajas):
                cajas.append(r)
        if not cajas:
            continue
        for r in cajas:
            _arbol(lz, (r[0] + r[2]) / 2, r[1] + 1, s * rng.uniform(0.8, 1.15), rng, conifera)
        lz.ocupado.extend(cajas)
        puestos += 1


# ------------------------------------------------------------------ elementos de composición

def _rosa(lz, cx, cy, r):
    ax, t_ = lz.ax, lz.c["tinta"]
    ax.add_patch(Circle((cx, cy), r * 1.08, fill=False, ls=(0, (1, 3)), lw=1.2, ec=t_, zorder=8))
    ax.add_patch(Circle((cx, cy), r * 0.98, fill=False, lw=0.6, ec=t_, zorder=8))
    for ang, largo in [(a, 1.0) for a in (90, 0, 270, 180)] + [(a, 0.55) for a in (45, 135, 225, 315)]:
        t = np.radians(ang)
        punta = (cx + np.cos(t) * r * largo, cy + np.sin(t) * r * largo)
        izq = (cx + np.cos(t + np.pi / 2) * r * 0.12, cy + np.sin(t + np.pi / 2) * r * 0.12)
        der = (cx + np.cos(t - np.pi / 2) * r * 0.12, cy + np.sin(t - np.pi / 2) * r * 0.12)
        ax.add_patch(Polygon([punta, izq, (cx, cy)], fc=t_, ec=t_, lw=0.8, zorder=9))
        ax.add_patch(Polygon([punta, der, (cx, cy)], fc="white", ec=t_, lw=0.8, zorder=9))
    for letra, (dx, dy) in {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}.items():
        ax.text(cx + dx * r * 1.32, cy + dy * r * 1.32, letra, **lz.letra("titulo", r / 3.2), ha="center", va="center", zorder=9, color=t_)
    lz.ocupado.append((cx - r * 1.5, cy - r * 1.5, cx + r * 1.5, cy + r * 1.5))


def _esquinas(lz):
    """Esquinas ordenadas de más vacía a más ocupada por el track."""
    W, H = lz.W, lz.H
    cajas = {"ne": (0.6 * W, 0.7 * H, W, H), "no": (0, 0.7 * H, 0.4 * W, H),
             "se": (0.6 * W, 0, W, 0.3 * H), "so": (0, 0, 0.4 * W, 0.3 * H)}
    return sorted(cajas, key=lambda k: lz.pisa_track(cajas[k]))


def _titulo(lz, esquina, titulo, subtitulo):
    W, H, t_ = lz.W, lz.H, lz.c["tinta"]
    derecha = esquina.endswith("e")
    arriba = esquina.startswith("n")
    palabras = titulo.upper().split()
    if len(titulo) > 11 and len(palabras) > 1:
        corte = int(np.argmin([abs(len(" ".join(palabras[:i])) - len(titulo) / 2)
                               for i in range(1, len(palabras))])) + 1
        lineas = [" ".join(palabras[:corte]), " ".join(palabras[corte:])]
    else:
        lineas = [titulo.upper()]
    tam = 0.045 * min(W, H) / PT * (1 + 0.3 * (lz.F - 1))
    kw = dict(**lz.letra("titulo", tam), color=t_)
    medidas = [lz.medir(l, **kw) for l in lineas]
    sub = _espaciado(subtitulo)
    # distancia y desnivel bajo el título (más grandes en el estilo personal)
    kws = dict(**lz.letra("titulo", tam * (0.32 if lz.fuentes is FUENTES["alballut"] else 0.64)),
               color=t_)
    ws, hs = lz.medir(sub, **kws)
    bloque_w = max([m[0] for m in medidas] + [ws])
    bloque_h = sum(m[1] * 0.92 for m in medidas) + hs * 1.6 + tam * PT * 1.1
    cx = W - 0.05 * W - bloque_w / 2 if derecha else 0.05 * W + bloque_w / 2
    y = H - 0.04 * H if arriba else 0.04 * H + bloque_h
    for l, (w, h) in zip(lineas, medidas):
        lz.ax.text(cx, y, l, ha="center", va="top", zorder=13, **kw)
        y -= h * 0.92
    y -= hs * 0.4
    lz.ax.text(cx, y, sub, ha="center", va="top", zorder=13, **kws)
    y -= hs * 1.6
    tb = tam * 0.75
    lz.ax.text(cx, y - tb * PT * 0.55, E.ICONOS["bici"], fontproperties=E.EMOJI, fontsize=tb,
               ha="center", va="center", zorder=13, color=t_)
    yc = y - tb * PT * 0.55
    for lado in (-1, 1):
        for ang in (-25, 0, 25):
            t = np.radians(ang)
            x0 = cx + lado * tb * PT * 0.95
            lz.ax.plot([x0, x0 + lado * np.cos(t) * tb * 0.45], [yc, yc + np.sin(t) * tb * 0.45],
                       color=t_, lw=2 * lz.F ** 0.5, solid_capstyle="round", zorder=13)
    lz.ocupado.append((cx - bloque_w / 2 - 20, y - tb * PT * 1.2 - 10, cx + bloque_w / 2 + 20,
                       H - 0.04 * H + 10 if arriba else 0.04 * H + bloque_h + 10))


def _decoracion(lz, simbolo, n, rng, TX, TY):
    if not simbolo or n <= 0:
        return
    R = 0.085 * min(lz.W, lz.H)
    tam = 19 * lz.F ** 0.7
    puestos = 0
    for _ in range(n * 30):
        if puestos >= n:
            break
        i = rng.integers(0, len(TX))
        ang = rng.uniform(0, 2 * np.pi)
        dist = rng.uniform(0.25, 1.15) * R
        x, y = TX[i] + np.cos(ang) * dist, TY[i] + np.sin(ang) * dist
        m = tam * PT * 0.65
        r = (x - m, y - m, x + m, y + m)
        if not lz.libre(r, margen=10, track_max=0.0) or lz.en_agua(x, y):
            continue
        lz.ax.add_patch(Circle((x + m * 0.35, y - m * 0.45), m * 0.7, fc=lz.c["manchas"], ec="none",
                               alpha=0.9, zorder=3.5))
        lz.ax.text(x, y, simbolo, fontproperties=E.EMOJI, fontsize=tam, color="#3b3b2b",
                   ha="center", va="center", zorder=3.6)
        lz.ocupado.append(r)
        puestos += 1


def cargar_logo(ruta, umbral=235):
    """Abre el logotipo y vuelve transparente el fondo blanco que toca los bordes."""
    from scipy import ndimage
    img = Image.open(ruta).convert("RGBA")
    a = np.asarray(img).astype(float)
    if (a[..., 3] < 250).mean() > 0.02:        # ya trae fondo transparente
        return a.astype(np.uint8)
    blanco = a[..., :3].min(axis=2) >= umbral
    etq, _ = ndimage.label(blanco)
    bordes = np.unique(np.r_[etq[0], etq[-1], etq[:, 0], etq[:, -1]])
    fondo = np.isin(etq, bordes[bordes > 0])
    # borde suave: los píxeles casi blancos junto al fondo se vuelven semitransparentes
    cerca = ndimage.binary_dilation(fondo, iterations=2) & ~fondo
    alfa = a[..., 3].copy()
    alfa[fondo] = 0
    claro = (255 - a[..., :3].min(axis=2)) / (255 - umbral + 1e-9)
    alfa[cerca] = np.minimum(alfa[cerca], np.clip(claro[cerca], 0, 1) * 255)
    a[..., 3] = alfa
    return a.astype(np.uint8)


def _logo_y_texto(marca, base):
    """Logotipo (array RGBA o None) y texto de la marca desde la sección [marca]."""
    logo = None
    if marca.get("logo"):
        ruta = Path(marca["logo"])
        ruta = ruta if ruta.is_absolute() else base / ruta
        if ruta.exists():
            logo = cargar_logo(ruta)
        else:
            print(f"  aviso: no encuentro el logotipo {ruta}")
    texto = marca.get("texto") or " - ".join(t for t in (marca.get("nombre"), marca.get("web")) if t)
    return logo, texto


def _cartucho(lz, esquina, plan, marca, base):
    """Recuadro con la marca personal (logo y texto) y los datos de la ruta."""
    W, H, F, c = lz.W, lz.H, lz.F, lz.c
    derecha, arriba = esquina.endswith("e"), esquina.startswith("n")
    logo, texto_marca = _logo_y_texto(marca, base)
    controles = len({p.control for p in plan.puntos if p.control})
    datos = [("Salida", f"{plan.salida:%d/%m/%Y · %H:%M} h"),
             ("Distancia", f"{plan.total_km:.0f} km"),
             ("Desnivel", f"+{plan.total_asc:,.0f} m".replace(",", " ")),
             ("Controles", f"{controles}"),
             ("Tiempo límite", f"{fmt_dur(timedelta(hours=plan.limite_h))} h")]
    tam_d = 23 * F * float(lz.cfg_mapa.get("escala_leyenda", 1.0))
    pad = 14 * F
    antigua = getattr(lz, "tronos", False)
    kw_e = dict(fontsize=tam_d * (1.05 if antigua else 1), family="IM FELL English" if antigua else E.SANS)
    kw_v = dict(fontsize=tam_d * (1.05 if antigua else 1), family="IM FELL English SC" if antigua else E.SANS,
                weight="normal" if antigua else "bold")
    alto_fila = lz.medir("Ág", **kw_e)[1] * 1.3
    ancho_datos = max(lz.medir(e, **kw_e)[0] + lz.medir(v, **kw_v)[0] for e, v in datos) + tam_d * 2.5
    ancho = max(0.25 * W, ancho_datos + 2 * pad)
    kw_marca = dict(**lz.letra("marca", 17 * F), color=c["acento"])
    if texto_marca:     # se reduce hasta que quepa en el ancho del cartucho
        w_m = lz.medir(texto_marca, **kw_marca)[0]
        if w_m > ancho - 2 * pad:
            kw_marca["fontsize"] *= (ancho - 2 * pad) / w_m
    alto_marca = lz.medir(texto_marca, **kw_marca)[1] * 1.15 if texto_marca else 0
    alto_logo = min(ancho * 0.36, ancho / logo.shape[1] * logo.shape[0]) if logo is not None else 0
    alto = pad * 3 + alto_logo + alto_marca + len(datos) * alto_fila + 6 * F
    # se prueban posiciones pegadas al borde izquierdo y derecho, de abajo arriba
    mejor = None
    for xx in (0.035 * W, W - 0.035 * W - ancho):
        for yy in np.linspace(0.03 * H + alto, H - 0.03 * H, 25):
            r = (xx, yy - alto, xx + ancho, yy)
            if not lz.libre(r, margen=10, track_max=1.0):
                continue
            pisa = lz.pisa_track(r)
            preferida = (xx > W / 2) == derecha and (yy > H / 2) == arriba
            clave = (round(pisa, 3), not preferida)
            if mejor is None or clave < mejor[0]:
                mejor = (clave, xx, yy)
    if mejor:
        _, x0, y1 = mejor
    else:
        x0 = W - 0.035 * W - ancho if derecha else 0.035 * W
        y1 = H - 0.03 * H if arriba else 0.03 * H + alto
    caja = FancyBboxPatch((x0, y1 - alto), ancho, alto, boxstyle=f"round,pad=0,rounding_size={10 * F}",
                          fc=c["papel"], ec=c["tinta"], lw=1.8 * F ** 0.5, zorder=14, alpha=0.95)
    caja.set_sketch_params(0.8, 80, 2)
    lz.ax.add_patch(caja)
    y = y1 - pad
    cx = x0 + ancho / 2
    if logo is not None:
        w_logo = alto_logo / logo.shape[0] * logo.shape[1]
        lz.ax.imshow(logo, extent=(cx - w_logo / 2, cx + w_logo / 2, y - alto_logo, y), zorder=15,
                     interpolation="lanczos")
        lz.ax.set_xlim(0, W)
        lz.ax.set_ylim(0, H)
        y -= alto_logo + pad * 0.5
    if texto_marca:
        lz.ax.text(cx, y, texto_marca, ha="center", va="top", zorder=15, **kw_marca)
        y -= alto_marca
    y -= pad * 0.4
    ln, = lz.ax.plot([x0 + pad, x0 + ancho - pad], [y, y], color=c["tinta"], lw=1.2, zorder=15)
    ln.set_sketch_params(0.6, 40, 2)
    y -= pad * 0.6
    for etiqueta, valor in datos:
        lz.ax.text(x0 + pad, y, etiqueta, ha="left", va="top", zorder=15, alpha=0.8, color=c["tinta"], **kw_e)
        lz.ax.text(x0 + ancho - pad, y, valor, ha="right", va="top", zorder=15, color=c["tinta"], **kw_v)
        y -= alto_fila
    lz.ocupado.append((x0 - 10, y1 - alto - 10, x0 + ancho + 10, y1 + 10))


def _marca_pequena(lz, esquina, marca, base):
    """Logotipo y enlace discretos en una esquina (mapa Al-Ballut)."""
    logo, texto = _logo_y_texto(marca, base)
    if logo is None and not texto:
        return
    W, H, F, c = lz.W, lz.H, lz.F, lz.c
    derecha, arriba = esquina.endswith("e"), esquina.startswith("n")
    kw = dict(fontsize=12 * F, family=E.SANS, weight="medium", color=c["tinta"])
    w_t, h_t = lz.medir(texto, **kw) if texto else (0, 0)
    alto_logo = 0.07 * min(W, H) if logo is not None else 0
    w_logo = alto_logo / logo.shape[0] * logo.shape[1] if logo is not None else 0
    ancho = max(w_t, w_logo)
    x0 = W - 0.03 * W - ancho if derecha else 0.03 * W
    y1 = H - 0.025 * H if arriba else 0.025 * H + alto_logo + h_t * 1.4
    cx = x0 + ancho / 2
    if logo is not None:
        lz.ax.imshow(logo, extent=(cx - w_logo / 2, cx + w_logo / 2, y1 - alto_logo, y1), zorder=15,
                     interpolation="lanczos")
        lz.ax.set_xlim(0, W)
        lz.ax.set_ylim(0, H)
    if texto:
        lz.ax.text(cx, y1 - alto_logo - h_t * 0.3, texto, ha="center", va="top", zorder=15, **kw)
    lz.ocupado.append((x0 - 10, y1 - alto_logo - h_t * 1.5, x0 + ancho + 10, y1 + 10))


def _leyenda_lineas(lz, partes, kw, ancho):
    """Reparte las entradas de la leyenda en líneas que quepan en `ancho` píxeles."""
    lineas, actual = [], ""
    for p in partes:
        prueba = f"{actual}     {p}" if actual else p
        if actual and lz.medir(prueba, **kw)[0] > ancho:
            lineas.append(actual)
            actual = p
        else:
            actual = prueba
    if actual:
        lineas.append(actual)
    return lineas


def _perfil(lz, plan, lugares_ctrl):
    """Perfil de elevación dibujado a mano en la franja inferior, con los controles numerados.

    La franja se dimensiona según el texto: título y leyenda de controles arriba, km abajo.
    """
    F, c, tr = lz.F, lz.c, plan.track
    esc = float(lz.cfg_mapa.get("escala_perfil", 3.0))     # título, leyenda y km del perfil
    kw_tit = dict(**lz.letra("perfil_titulo", 16 * F * esc), color=c["tinta"])
    kw_ley = dict(**lz.letra("perfil", 11 * F * esc), color=c["tinta"])
    kw_km = dict(**lz.letra("perfil", 11 * F * esc), color=c["tinta"])
    titulo = f"PERFIL  ·  {plan.total_km:.0f} KM  ·  +{plan.total_asc:,.0f} M".replace(",", " ")
    partes = [f"{_numeros_texto(l['numeros'])}: {l['nombre']}"
              for l in sorted(lugares_ctrl, key=lambda l: l["km"])]
    if partes:
        partes[0] = "Controles:  " + partes[0]      # sin título, la lista no se entendía
    x_izq = 0.06 * lz.W
    w_num = lz.medir(f"{tr.total_km:.0f}", **kw_km)[0]
    w_unidad = lz.medir("km", **kw_km)[0]
    x_der = 0.96 * lz.W - w_unidad - w_num * 0.6 - 12 * F    # sitio para "km" tras el último número
    lineas = _leyenda_lineas(lz, partes, kw_ley, 0.94 * lz.W - x_izq)
    h_tit = lz.medir(titulo, **kw_tit)[1]
    h_ley = lz.medir("Ág", **kw_ley)[1] * 1.15
    h_km = lz.medir("0", **kw_km)[1]
    h_graf = 0.13 * min(lz.W, lz.H)
    margen = 24 * F
    alto_pie = int(margen + h_tit + margen * 0.5 + len(lineas) * h_ley + margen * 0.6 + h_graf
                   + margen * 0.5 + h_km + margen)
    lz.ajustar_pie(alto_pie)
    fig = lz.fig
    total_px = lz.H + alto_pie

    def fy(px):
        return px / total_px

    y = alto_pie - margen
    fig.text(x_izq / lz.W, fy(y), titulo, ha="left", va="top", **kw_tit)
    y -= h_tit + margen * 0.5
    for l in lineas:
        fig.text(x_izq / lz.W, fy(y), l, ha="left", va="top", **kw_ley)
        y -= h_ley
    y -= margen * 0.6
    y_graf0 = margen + h_km + margen * 0.5
    ax = fig.add_axes([x_izq / lz.W, fy(y_graf0), (x_der - x_izq) / lz.W, fy(h_graf)])
    paso = max(1, len(tr.km) // 1500)
    km, ele = tr.km[::paso], tr.ele[::paso]
    base = max(0, ele.min() - (ele.max() - ele.min()) * 0.25)
    ax.fill_between(km, base, ele, color=c["tierra"][1], alpha=0.85, lw=0, zorder=1)
    ln, = ax.plot(km, ele, color=c["tinta"], lw=2.2 * F ** 0.5, zorder=3, solid_capstyle="round")
    ln.set_sketch_params(0.8, 70, 2)
    ax.set_xlim(0, tr.total_km)
    ax.axis("off")
    ln, = ax.plot([0, tr.total_km], [base, base], color=c["tinta"], lw=1.4, zorder=3, clip_on=False)
    ln.set_sketch_params(0.6, 50, 2)
    # km bajo el eje, con el mismo paso que quepa sin solaparse
    ancho_px = x_der - x_izq
    paso_km = next((p for p in (10, 20, 25, 50, 100, 200, 250, 500)
                    if ancho_px / (tr.total_km / p) > w_num * 1.8), 500)
    for k in np.arange(0, tr.total_km + 1, paso_km):
        fig.text((x_izq + k / tr.total_km * ancho_px) / lz.W, fy(y_graf0 - margen * 0.3), f"{k:.0f}",
                 ha="center", va="top", **kw_km)
    fig.text((x_der + w_num * 0.6 + 12 * F) / lz.W, fy(y_graf0 - margen * 0.3), "km", ha="left",
             va="top", **kw_km)

    # controles numerados sobre el perfil, escalonados si los círculos se tocan
    tam_num = 10 * F
    diam_px = tam_num * PT * 1.75
    km_px = tr.total_km / ancho_px
    rango = ele.max() * 1.08 - base
    paso_y = diam_px * 1.1 / h_graf * rango
    separacion = diam_px * 1.15 * km_px
    colocados, numeros = [], []
    for p in sorted((p for p in plan.puntos if p.es_control), key=lambda p: p.km):
        y_n = float(np.interp(p.km, km, ele)) + rango * 0.05
        while any(abs(p.km - k) < separacion and abs(y_n - yy) < paso_y * 0.95 for k, yy in colocados):
            y_n += paso_y
        colocados.append((p.km, y_n))
        numeros.append((p, y_n))
    tope = max(ele.max() * 1.08, max(v for _, v in numeros) + paso_y * 1.1)
    ax.set_ylim(base, tope)
    i = int(np.argmax(ele))
    ax.text(km[i], ele[i] + rango * 0.03, f"{ele[i]:.0f} m", **lz.letra("perfil", 12 * F),
            color=c["relieve"], ha="left", va="bottom")
    for p, y_n in numeros:
        ax.plot([p.km, p.km], [base, y_n], color=c["acento"], lw=1.2 * F ** 0.5, ls=(0, (2, 2)), zorder=2)
        ax.text(p.km, y_n, p.control[1:], fontsize=tam_num, family=E.SANS,
                weight="bold", color="white", ha="center", va="bottom", zorder=5,
                bbox=dict(boxstyle="circle,pad=0.25", fc=c["acento"], ec="white", lw=1.5))
    fig.add_artist(plt.Line2D([0.03, 0.97], [fy(alto_pie)] * 2, color=c["tinta"], lw=1.2, alpha=0.6))


# ------------------------------------------------------------------ composición

def _encuadre(tr, cfg):
    X, Y = a_mercator(tr.lon, tr.lat)
    xmin, xmax, ymin, ymax = X.min(), X.max(), Y.min(), Y.max()
    w, h = xmax - xmin, ymax - ymin
    orient = cfg.get("orientacion", "auto")
    if orient == "auto":
        orient = "vertical" if h > w * 1.1 else "horizontal"
    prop = 1.414 if orient == "horizontal" else 1 / 1.414
    margen = cfg.get("margen", 0.12) * max(w, h)
    xmin, xmax, ymin, ymax = xmin - margen, xmax + margen, ymin - margen, ymax + margen
    w, h = xmax - xmin, ymax - ymin
    if w / h < prop:
        extra = (h * prop - w) / 2
        xmin, xmax = xmin - extra, xmax + extra
    else:
        extra = (w / prop - h) / 2
        ymin, ymax = ymin - extra, ymax + extra
    lado_largo = int(cfg.get("lado_px", 3300))
    W, H = (lado_largo, int(lado_largo / prop)) if prop >= 1 else (int(lado_largo * prop), lado_largo)
    return W, H, xmin, ymin, xmax, ymax


def _terreno_tronos(lz, rng):
    """Relieve sombreado con colores por altitud (llanura verde pálida, ocre, roca gris, cumbres claras)
    y textura de roca en las laderas, como los mapas antiguos de fantasía."""
    from matplotlib.colors import LightSource, LinearSegmentedColormap
    from scipy import ndimage
    ele = _elevacion(lz, 3)
    ele = np.where(ele < -50, 0, ele)
    # llanuras lisas y sierras con detalle: se suaviza más donde el terreno apenas cambia
    local = ndimage.generic_filter(ndimage.zoom(ele, 0.25, order=1), np.ptp, size=5)
    local = np.asarray(Image.fromarray(local.astype(np.float32)).resize(ele.shape[::-1], Image.BILINEAR))
    peso = np.clip((local - 60) / 250, 0, 1)
    ele = ndimage.gaussian_filter(ele, 1.0) * peso + ndimage.gaussian_filter(ele, 3.0) * (1 - peso)
    gh, gw = ele.shape
    xmin, _, xmax, _ = lz.caja
    dx = (xmax - xmin) / gw                         # metros (Mercator) por celda
    lo, hi = np.percentile(ele, 2), np.percentile(ele, 99.7)
    norm = np.clip((ele - lo) / max(hi - lo, 1), 0, 1)
    # la roca clara de las cumbres (parece nieve), solo por encima de unos 1.200 m
    norm = np.minimum(norm, 0.88 + 0.12 * np.clip((ele - 1200) / 800, 0, 1))
    # tintas hipsométricas: llanura verde, colinas ocre, sierra parda y cumbres de roca clara; el tono sube con la altura
    rampa = LinearSegmentedColormap.from_list("tronos", [
        (0.0, "#bcc78f"), (0.25, "#c6c894"), (0.45, "#cdbd8a"), (0.62, "#bf9f6f"),
        (0.78, "#a5845e"), (0.9, "#9c8f7e"), (1.0, "#e2ddd2")])
    rgb = rampa(norm)[..., :3]
    # textura de roca: ruido fino que crece con la pendiente
    gy, gx = np.gradient(ele, dx)
    pendiente = np.clip(np.hypot(gx, gy) / 0.35, 0, 1)
    ruido = ndimage.gaussian_filter(rng.normal(0, 1, ele.shape), 0.7)
    rgb = np.clip(rgb * (1 + ruido[..., None] * 0.03 * (0.2 + 2 * pendiente[..., None])), 0, 1)
    # La luz viene del noroeste (arriba a la izquierda), como en todos los mapas: si viene de abajo, el ojo ve
    # las sierras como valles. LightSource supone la fila 0 arriba (norte) y la rejilla está al revés (origin
    # "lower"): se sombrea con el norte arriba y se vuelve a voltear.
    ls = LightSource(azdeg=315, altdeg=45)
    exag = float(getattr(lz, "cfg_mapa", {}).get("exageracion_relieve", 3.5))
    norte = ele[::-1]
    luz = ls.hillshade(norte, vert_exag=exag, dx=dx, dy=dx)[::-1]
    sombra = ls.shade_rgb(rgb[::-1], norte, vert_exag=exag, dx=dx, dy=dx, blend_mode="soft", fraction=0.9)[::-1]
    # más contraste en las laderas: las umbrías oscurecen y las solanas aclaran, con un toque frío y cálido
    k = (luz[..., None] - 0.55) * pendiente[..., None] ** 0.6
    sombra = np.clip(sombra * (1 + 0.45 * k) + k * np.array([0.05, 0.035, -0.01]), 0, 1)
    lz.ax.imshow(sombra, extent=(0, lz.W, 0, lz.H), origin="lower", zorder=0.3, interpolation="bicubic")
    lz.luz = luz


def _bosques_tronos(lz, rng):
    """Bosques con textura de copas, a partir del verde de los bosques en las teselas OSM estándar."""
    from scipy import ndimage
    xmin, ymin, xmax, ymax = lz.caja
    z = zoom_para(xmin, xmax, lz.W / 2.5, "osm")
    img = mapa_base(xmin, ymin, xmax, ymax, z, "osm").resize((lz.W // 3, lz.H // 3))
    a = np.asarray(img).astype(int)
    m = (np.abs(a - [173, 209, 158]).sum(axis=2) < 22).astype(np.uint8) * 255
    m = Image.fromarray(m).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))   # cierra huecos de rótulos
    m = m.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))                    # quita motas
    m = np.asarray(m.filter(ImageFilter.GaussianBlur(1.5)))[::-1] / 255.0
    if m.max() < 0.5:
        return
    h, w = m.shape
    # copas: manchas de ruido a dos escalas, verde oscuro con luces
    copas = ndimage.gaussian_filter(rng.normal(0, 1, (h, w)), 0.7) + 0.6 * ndimage.gaussian_filter(rng.normal(0, 1, (h, w)), 1.8)
    copas = (copas - copas.min()) / np.ptp(copas)
    # cada copa, iluminada desde el noroeste: el relieve del ruido hace de copas
    gy, gx = np.gradient(ndimage.gaussian_filter(copas, 0.8))
    brillo = np.clip(0.5 + (gx - gy) * 9, 0, 1)        # filas hacia el norte: lado iluminado, el que mira al noroeste
    base = np.array([int(lz.c["bosque"][i:i + 2], 16) / 255 for i in (1, 3, 5)])
    rgb = base[None, None, :] * (0.55 + 0.6 * copas[..., None] + 0.5 * (brillo[..., None] - 0.5))
    luz = getattr(lz, "luz", None)
    if luz is not None:                                 # el bosque también recibe la luz del relieve
        luz = np.asarray(Image.fromarray((luz * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)) / 255.0
        rgb = rgb * (0.55 + 0.75 * luz[..., None])
    rgba = np.dstack([np.clip(rgb, 0, 1), np.clip((m - 0.35) / 0.3, 0, 1) * 0.82])
    lz.ax.imshow(rgba, extent=(0, lz.W, 0, lz.H), origin="lower", zorder=0.4, interpolation="bilinear")
    lz.ax.contour(np.linspace(0, lz.W, w), np.linspace(0, lz.H, h), m, levels=[0.5],
                  colors=[_mezcla(lz.c["bosque"], "#000000", 0.35)], linewidths=0.8, alpha=0.6, zorder=0.45)


def _marca_roja(lz, x, y, r, z=11):
    """Marca de pueblo de los mapas de fantasía: disco granate con aro oscuro y un brillo."""
    lz.ax.add_patch(Circle((x, y), r, fc=lz.c["acento"], ec="#3a0d0b", lw=1.2 * lz.F ** 0.4, zorder=z))
    lz.ax.add_patch(Circle((x - r * 0.3, y + r * 0.3), r * 0.28, fc="#f1c9b8", ec="none", alpha=0.8, zorder=z + 0.01))


def _estrella(lz, x, y, r, z=12.5):
    """Sol de ocho puntas (la salida), como las capitales del mapa de referencia."""
    ang = np.linspace(0, 2 * np.pi, 33)[:-1] + np.pi / 16
    radio = np.where(np.arange(32) % 2 == 0, r, r * 0.55)
    radio = np.where(np.arange(32) % 4 == 0, r * 1.25, radio)
    lz.ax.add_patch(Polygon(np.c_[x + np.cos(ang) * radio, y + np.sin(ang) * radio], closed=True,
                            fc=lz.c["acento"], ec="#3a0d0b", lw=1.2 * lz.F ** 0.4, zorder=z))


def _colores(cfg, estilo):
    nombre = cfg.get("paleta", "verde") if estilo == "personal" else estilo
    colores = dict(PALETAS.get(nombre, PALETAS["verde"]))
    colores.update(cfg.get("colores", {}))
    return colores


def _generar_estilo(proyecto, plan, osm, estilo):
    cfg = proyecto.seccion("mapa")
    tronos = estilo == "tronos"              # variante del personal con aspecto de mapa antiguo de fantasía
    personal = estilo in ("personal", "tronos")
    F = float(cfg.get("escala_texto", 2.0))
    tr = plan.track
    rng = np.random.default_rng(cfg.get("semilla", 7))
    W, H, xmin, ymin, xmax, ymax = _encuadre(tr, cfg)
    con_perfil = personal and cfg.get("perfil", True)
    lz = Lienzo(W, H, xmin, ymin, xmax, ymax, _colores(cfg, estilo), F, 0, estilo,
                float(cfg.get("escala_toponimos", 2.0)) if personal else 1.0)
    lz.cfg_mapa = cfg
    lz.tronos = tronos
    TX, TY = lz.px(tr.lon, tr.lat)
    lz.marcar_track(TX, TY, grosor=int(10 + 4 * F))

    # 1. fondo
    if tronos:
        try:
            _terreno_tronos(lz, rng)
        except Exception as e:
            print(f"  aviso: sin relieve sombreado ({e})")
        try:
            _bosques_tronos(lz, rng)
        except Exception as e:
            print(f"  aviso: sin bosques ({e})")
        _papel(lz, rng)
    else:
        if personal:
            _papel(lz, rng)
        _tierra(lz, TX, TY, rng, manchas=not personal, alfa=0.7 if personal else 1.0)
    if cfg.get("agua", True):
        try:
            _agua(lz)
        except Exception as e:
            print(f"  aviso: sin capa de agua ({e})")

    # 2. título, cartucho y rosa de los vientos en las esquinas más despejadas
    esquinas = _esquinas(lz)
    sub = cfg.get("subtitulo") or f"{plan.total_km:.0f} km · {plan.total_asc:,.0f} m+".replace(",", " ")
    _titulo(lz, esquinas[0], cfg.get("titulo", proyecto.nombre), sub)
    libres = list(esquinas[1:])
    if personal:
        marca = proyecto.seccion("marca")
        esq = next((e for e in libres if e[0] != esquinas[0][0]), libres[0])
        _cartucho(lz, esq, plan, marca, proyecto.base)
        libres.remove(esq)
    if cfg.get("rosa", True) and libres:
        # la rosa, en la primera esquina libre (el cartucho puede haberse desplazado)
        r = 0.04 * min(W, H) * (1 + 0.15 * (F - 1))

        def centro(e):
            return (W * 0.07 + r if e.endswith("o") else W * 0.93 - r,
                    H * 0.06 + r if e.startswith("s") else H * 0.94 - r)
        orden = sorted(libres, key=lambda e: e[0] == esquinas[0][0])
        rosa = next((e for e in orden if lz.libre((centro(e)[0] - 1.5 * r, centro(e)[1] - 1.5 * r,
                                                    centro(e)[0] + 1.5 * r, centro(e)[1] + 1.5 * r),
                                                   margen=10, track_max=1.0)), None)
        if rosa:
            _rosa(lz, *centro(rosa), r)
            libres.remove(rosa)
    if not personal and libres:          # Al-Ballut: logo y enlace en la esquina que queda
        _marca_pequena(lz, libres[0], proyecto.seccion("marca"), proyecto.base)

    # 3. lugares de la ruta (reservan sitio antes que la geografía)
    lugares = _seleccion_lugares(lz, _lugares(plan), cfg.get("lugares_max", 8),
                                 cfg.get("separacion_lugares", 0.11))
    inicio = lugares[0]
    x0, y0 = lz.px(inicio["lon"], inicio["lat"])
    marcas = {}
    if personal:      # los números van primero: el rótulo se coloca a su lado
        for l in lugares:
            if l["control"]:
                x, y = lz.px(l["lon"], l["lat"])
                if tronos and l is inicio:
                    _estrella(lz, x, y, 26 * F ** 0.6)
                marcas[id(l)] = _marca_numerada(lz, x, y, l["numeros"], grande=l is inicio)
    # la salida, la primera (es el rótulo más grande); si no cabe cerca de un borde, algo más pequeña
    # en el estilo personal los topónimos se agrandan (escala_toponimos): los pueblos, algo menos
    esc = float(cfg.get("escala_lugares", 0.85 if personal else 1.0))
    for red in REDUCCIONES + (0.5,):                # mismo tamaño que los controles (antes, casi el doble)
        if _rotular_lugar(lz, x0, y0, lz.mayus(inicio["nombre"]), 21 * F * esc * red, 1.0, marcas.get(id(inicio), 0)):
            break
    lz.ocupado.append((x0 - 14, y0 - 14, x0 + 14, y0 + 14))
    for l in sorted(lugares[1:], key=lambda l: not l["control"]):
        x, y = lz.px(l["lon"], l["lat"])
        # los controles prueban tamaños menores antes de quedarse sin rótulo; el resto de pueblos, no
        for red in (REDUCCIONES if l["control"] else (1.0,)):
            if _rotular_lugar(lz, x, y, lz.mayus(l["nombre"]), (21 if l["control"] else 15) * F * esc * red,
                              0.3 if l["control"] else 0.05, marcas.get(id(l), 0)):
                l["rotulado"] = True
                lz.ocupado.append((x - 9, y - 9, x + 9, y + 9))
                break
    pueblos = osm.get("pueblos", [])
    if cfg.get("pueblos", True):
        _pueblos_ruta(lz, lugares, F, rng, [(p["lat"], p["lon"]) for p in pueblos if p["castillo"]])

    # 4. geografía (el relieve, al final: rellena los huecos que dejan los rótulos)
    _sierras(lz, osm.get("sierras", []), cfg.get("sierras_max", 7 if tronos else 10), TX, TY)
    cauces = _rios(lz, osm.get("rios", {}), cfg.get("rios_max", 22))
    _embalses(lz, osm.get("embalses", []), cfg.get("embalses_max", 10))
    _comarcas(lz, osm.get("comarcas", []), cfg.get("comarcas_max", 10), TX, TY)
    _regiones(lz, osm.get("regiones", []))
    _cumbres(lz, osm.get("cimas", []), cfg.get("cumbres_max", 6 if personal else 3))
    _puertos(lz, osm.get("puertos", []))
    if cfg.get("pueblos", True):
        _pueblos_cercanos(lz, pueblos, lugares, cfg.get("pueblos_max", 12), F, rng)
    if personal and cfg.get("puentes", True):
        _puentes(lz, TX, TY, cauces, F, cfg.get("grosor_track", 5) * F ** 0.5 * PT)
    if cfg.get("arboles", True):
        _arboles_ribera(lz, cauces, rng, cfg.get("arboles_ribera_max", 140), F)
        _arboles_sueltos(lz, rng, cfg.get("arboles_grupos", 45), F)
    if not personal:
        _decoracion(lz, cfg.get("decoracion", ""), cfg.get("decoracion_n", 40), rng, TX, TY)
    if personal and not tronos and cfg.get("relieve", True):
        try:
            _relieve(lz, rng, cfg.get("densidad_relieve", 1.0))
        except Exception as e:
            print(f"  aviso: sin relieve dibujado ({e})")

    # 5. track y marcas de los lugares
    grosor = cfg.get("grosor_track", 5) * F ** 0.5
    if personal:
        halo, = lz.ax.plot(TX, TY, color=lz.c["papel"], lw=grosor * 2.2, solid_capstyle="round",
                           solid_joinstyle="round", zorder=9.5)
        halo.set_sketch_params(*BOCETO)
    ln, = lz.ax.plot(TX, TY, color=lz.c["tinta"], lw=grosor, solid_capstyle="round",
                     solid_joinstyle="round", zorder=10)
    ln.set_sketch_params(*BOCETO)
    for l in lugares[1:]:
        if not l.get("rotulado") and not l["control"]:
            continue
        x, y = lz.px(l["lon"], l["lat"])
        if l["control"] and not personal:
            lz.ax.add_patch(Circle((x, y), 9 * F ** 0.6, fc="white", ec=lz.c["tinta"], lw=2.4, zorder=11))
            lz.ax.add_patch(Circle((x, y), 3 * F ** 0.6, fc=lz.c["tinta"], ec="none", zorder=11))
        elif not l["control"]:
            if tronos:
                _marca_roja(lz, x, y, 6 * F ** 0.6)
            else:
                lz.ax.add_patch(Circle((x, y), 5 * F ** 0.6, fc="white", ec=lz.c["tinta"], lw=2, zorder=11))
    if not personal:
        lz.ax.add_patch(Circle((x0, y0), 15 * F ** 0.6, fc="white", ec=lz.c["tinta"], lw=3, zorder=11))
        lz.ax.add_patch(Circle((x0, y0), 9 * F ** 0.6, fc=lz.c["tinta"], ec="none", zorder=11))

    if con_perfil:
        _perfil(lz, plan, [l for l in lugares if l["control"]])

    fuentes = "© OpenStreetMap contributors"
    if osm and osm.get("fuente_nombres") == "ign":
        fuentes += " · Nombres: NGBE, © IGN España (CC BY 4.0)"
    if personal:
        fuentes += " · Wikidata · Relieve: Terrarium (Mapzen/AWS)"
    lz.fig.text(0.995, 0.004, fuentes, fontsize=8 * F, family=E.SANS, color="#8a8270",
                ha="right", va="bottom")
    nombre = proyecto.salida_dir / {"alballut": "mapa_ilustrado", "personal": "mapa_personal"}.get(estilo, f"mapa_{estilo}")
    lz.fig.savefig(f"{nombre}.png", dpi=100, facecolor=lz.c["papel"])
    lz.fig.savefig(f"{nombre}.pdf", dpi=100, facecolor=lz.c["papel"])
    plt.close(lz.fig)
    return [f"{nombre}.png", f"{nombre}.pdf"]


def generar(proyecto, plan, osm=None):
    """Genera los estilos pedidos en [mapa] estilos (por defecto, los dos)."""
    cfg = proyecto.seccion("mapa")
    estilos = cfg.get("estilos", ["alballut", "personal"])
    salidas = []
    for estilo in estilos:
        salidas += _generar_estilo(proyecto, plan, osm or {}, estilo)
    return salidas
