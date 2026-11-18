"""Infografía de la ruta: mapa base OSM, track por días, cajas por control y perfil."""
from datetime import timedelta

import sys

import matplotlib.pyplot as plt

import numpy as np
from matplotlib import patheffects as pe
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

from . import estilo as E
from .datos import hora_en_km
from .proyecto import MESES, fmt_dur, fmt_fecha, fmt_hora
from .teselas import ESTILOS, a_mercator, cubre, mapa_base, zoom_para

HALO = [pe.withStroke(linewidth=4, foreground="white")]
PT = 100 / 72  # píxeles por punto tipográfico (las figuras se dibujan a 100 ppp)


# ------------------------------------------------------------------ utilidades

def _dia(plan, t):
    return (t.date() - plan.salida.date()).days


def _txt_parada(minutos):
    if not minutos:
        return ""
    if minutos >= 60 and minutos % 60 == 0:
        return f" (+{int(minutos // 60)} h)"
    if minutos >= 60:
        return f" (+{int(minutos // 60)} h {int(minutos % 60)} min)"
    return f" (+{int(minutos)} min)"


def _etiqueta_control(p):
    if p.control:
        return f"{p.control} - {p.nombre.upper()}"
    return p.nombre.upper()


def _seleccion_panel(plan, desde, hasta, sin_caja):
    """Puntos con caja entre el control `desde` y el control `hasta` (incluidos)."""
    pts = plan.puntos
    i0 = next(i for i, p in enumerate(pts) if p.control == desde)
    i1 = next(i for i, p in enumerate(pts) if i >= i0 and p.control == hasta)
    return [p for p in pts[i0:i1 + 1] if p.destacado and p.control not in sin_caja]


# Tamaños de caja y proporciones del mapa que se prueban, por orden de preferencia, antes de dividir la ruta
# en varios mapas: primero cajas más pequeñas (sin bajar de lo legible) y luego un mapa más alto.
INTENTOS = [(1.0, None), (0.85, None), (0.75, None), (0.75, 1.0), (0.66, 1.0), (0.66, 0.8), (0.6, 0.8)]


def _encuadre(X, Y, cfg, proporcion, margen=None):
    """Recuadro en Mercator de X, Y con margen (fracción del lado mayor), ampliado hasta la proporción
    ancho/alto del mapa."""
    xmin, xmax, ymin, ymax = X.min(), X.max(), Y.min(), Y.max()
    lado = max(xmax - xmin, ymax - ymin)
    margen = (cfg.get("margen", 0.05) if margen is None else margen) * lado
    xmin, xmax, ymin, ymax = xmin - margen, xmax + margen, ymin - margen, ymax + margen
    w, h = xmax - xmin, ymax - ymin
    if w / h < proporcion:
        extra = (h * proporcion - w) / 2
        xmin, xmax = xmin - extra, xmax + extra
    else:
        extra = (w / proporcion - h) / 2
        ymin, ymax = ymin - extra, ymax + extra
    return xmin, xmax, ymin, ymax


def _probar(fig, plan, cfg, panel, km0, km1, X, Y, W, esc, prop):
    """Coloca las cajas de un mapa con un tamaño de caja y una proporción; devuelve la disposición."""
    tr = plan.track
    sel = (tr.km >= km0) & (tr.km <= km1)
    Hm = int(round(W / prop))
    cajas = [Caja(fig, p, plan, cfg, esc) for p in panel]
    # sentido de la ruta: si es circular (encierra un área apreciable), las cajas la rodean por el borde del
    # mapa en el orden de la ruta (horario o antihorario), y el mapa deja alrededor del track sitio para ellas
    sx, sy = X[sel], Y[sel]
    area = 0.5 * float(np.sum(sx[:-1] * sy[1:] - sx[1:] * sy[:-1]))
    caja_area = max(1e-9, float((sx.max() - sx.min()) * (sy.max() - sy.min())))
    circular = abs(area) > 0.12 * caja_area and len(cajas) > 2
    margen = None
    if circular:
        # margen ≈ alto de una caja (el lado mayor del track ocupa casi todo el mapa en esa dirección)
        alto_ref = Hm if (sy.max() - sy.min()) * prop >= (sx.max() - sx.min()) else W
        margen = cfg.get("margen", 0.05) + (float(np.mean([c.h for c in cajas])) + 30 * _escala(cfg) * esc) / alto_ref
    xmin, xmax, ymin, ymax = _encuadre(sx, sy, cfg, prop, margen)

    def px(x, y):
        return (x - xmin) / (xmax - xmin) * W, (y - ymin) / (ymax - ymin) * Hm

    TX, TY = px(X, Y)
    for c in cajas:
        c.ax_, c.ay = px(*a_mercator(c.p.lon, c.p.lat))
    marcas = [px(*a_mercator(q.lon, q.lat)) for q in plan.puntos if q.es_control]
    sx, sy = TX[sel], TY[sel]
    for c in cajas:
        c.objetivo = None
    if circular and len(cajas) > 2:
        _objetivos_borde(cajas, W, Hm, (float(sx.mean()), float(sy.mean())), area > 0, _escala(cfg) * esc)
    res = (0, 0, 0.0)
    if cajas:
        res = _colocar(cajas, TX, TY, W, Hm, _escala(cfg) * esc, marcas,
                       centro=(float(TX[sel].mean()), float(TY[sel].mean())))
    forzadas, pisan, lejos = res
    return {"panel": panel, "km": (km0, km1), "encuadre": (xmin, xmax, ymin, ymax), "Hm": Hm, "esc": esc,
            "cajas": cajas, "cabe": not forzadas and not pisan and lejos <= 0.4 * W,
            "nota": (forzadas, pisan, lejos)}


def _mejor(fig, plan, cfg, panel, km0, km1, X, Y, W):
    """Primera disposición en la que caben las cajas (INTENTOS); si no cabe ninguna, la menos mala."""
    prop0 = cfg.get("proporcion_mapa", 4 / 3)
    probadas = []
    for esc, prop in INTENTOS:
        d = _probar(fig, plan, cfg, panel, km0, km1, X, Y, W, esc, min(prop or prop0, prop0))
        if d["cabe"]:
            return d
        probadas.append(d)
    return min(probadas, key=lambda d: (d["nota"][0], d["nota"][1], d["nota"][2]))


def _disponer(fig, plan, cfg, sin_caja, X, Y, W):
    """Mapas de la infografía. Se prefiere un solo mapa con todas las cajas (más pequeñas si hace falta); si no
    caben, dos: ida y vuelta, partiendo en el punto más alejado de la salida, cada uno encuadrado en su parte.
    Solo si tampoco caben, cada parte se divide de nuevo por la mitad."""
    tr = plan.track
    total = float(tr.km[-1])
    if cfg.get("paneles"):     # mapas fijados a mano en la configuración (control desde – control hasta)
        grupos = [_seleccion_panel(plan, a, b, sin_caja) for a, b in cfg["paneles"]]
        return [_mejor(fig, plan, cfg, g, 0 if i == 0 else g[0].km, total if i == len(grupos) - 1 else g[-1].km,
                       X, Y, W) for i, g in enumerate(grupos)]
    con_caja = [p for p in plan.puntos if p.destacado and p.control not in sin_caja]
    unico = _mejor(fig, plan, cfg, con_caja, 0.0, total, X, Y, W)
    if unico["cabe"] or len(con_caja) < 4:
        return [unico]
    # ida y vuelta: corte en el punto con caja más alejado de la salida (sin ser el primero ni el último)
    x0, y0 = X[0], Y[0]
    lejania = [np.hypot(*(np.array(a_mercator(p.lon, p.lat)) - (x0, y0))) for p in con_caja]
    k = int(np.argmax(lejania[1:-1])) + 1

    def partir(grupo, km0, km1, nivel):
        d = _mejor(fig, plan, cfg, grupo, km0, km1, X, Y, W)
        if d["cabe"] or nivel >= 2 or len(grupo) < 4:
            return [d]
        m = len(grupo) // 2
        return partir(grupo[:m + 1], km0, grupo[m].km, nivel + 1) + partir(grupo[m:], grupo[m].km, km1, nivel + 1)

    return partir(con_caja[:k + 1], 0.0, con_caja[k].km, 1) + partir(con_caja[k:], con_caja[k].km, total, 1)


def _escala(cfg):
    """Factor de tamaño de todo el texto (1 = tamaños de la versión 2; 2 = doble)."""
    return float(cfg.get("escala_texto", 2.0))


def _textos_pendiente():
    lims = [0] + [l for l, _ in E.COLORES_PENDIENTE[:-1]]
    return [f"< {lims[1]} %"] + [f"{a}–{b} %" for a, b in zip(lims[1:-1], lims[2:])] + [f"> {lims[-1]} %"]


def _ancho_pendiente(fig, F):
    """Ancho (px) de la leyenda «Pendiente del track» que dibuja _dibujar_pendiente."""
    x = _medir(fig, "Pendiente del track:", 11 * F, "regular")[0] + 10 * F
    for t in _textos_pendiente():
        x += 11 * F * PT * 0.8 + 5 * F + _medir(fig, t, 11 * F, "regular")[0] + 14 * F
    return x


def _dibujar_pendiente(fig, F, W, H, y):
    """Colores del track (los mismos del perfil), desde el borde izquierdo, a la altura y (fracción de la figura)."""
    x = 0.01 * W
    kw = dict(fontsize=11 * F, family=E.SANS, color="#444444", va="bottom")
    fig.text(x / W, y, "Pendiente del track:", **kw)
    x += _medir(fig, "Pendiente del track:", 11 * F, "regular")[0] + 10 * F
    lado = 11 * F * PT * 0.8
    for (_, c), t in zip(E.COLORES_PENDIENTE, _textos_pendiente()):
        fig.patches.append(Rectangle((x / W, y + 2 / H), lado / W, lado / H, transform=fig.transFigure,
                                     figure=fig, fc=c, ec="#5a4a1a", lw=0.6))
        x += lado + 5 * F
        fig.text(x / W, y, t, **kw)
        x += _medir(fig, t, 11 * F, "regular")[0] + 14 * F


def _medir(fig, texto, tam, peso):
    t = fig.text(0, 0, texto, fontsize=tam, family=[E.SANS, "Noto Emoji"], weight=peso)   # como la leyenda, con los iconos
    bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
    t.remove()
    return bb.width, bb.height


# ------------------------------------------------------------------ cajas

class Caja:
    def __init__(self, fig, p, plan, cfg, esc=1.0):
        """esc: tamaño de la caja respecto al normal (se reduce para que quepan más cajas en un mapa)."""
        self.p = p
        F = _escala(cfg) * esc
        self.F = F
        margen = p.margen
        tit, txt = cfg.get("tam_titulo", 17 * _escala(cfg)) * esc, cfg.get("tam_texto", 15 * _escala(cfg)) * esc
        self.lineas = [
            (_etiqueta_control(p), tit, "bold"),
            (f"km {p.km:.0f}  (+{p.asc_total:.0f} m)", txt, "medium"),
            (f"{fmt_hora(p.llegada)} h{_txt_parada(p.parada_min)} < {fmt_hora(p.cierre)} h",
             txt, "medium"),
        ]
        if p.antes_de_apertura:
            self.lineas.append((f"¡abre a las {fmt_hora(p.apertura_hoja)} h!", txt * 0.87, "bold"))
        if p.km > 0:
            aviso = "  ¡FUERA DE CIERRE!" if margen.total_seconds() < 0 else ""
            self.lineas.append((f"margen {fmt_dur(margen, signo=True)} h{aviso}",
                                txt * 0.87, "regular"))
        medidas = [_medir(fig, t, s, w) for t, s, w in self.lineas]
        self.pad = 9 * F
        self.alto_linea = [s * PT * 1.22 for _, s, _ in self.lineas]
        self.icono = E.ICONOS.get(p.tipo_parada, "")
        # el icono del tipo de parada va dentro de la caja, arriba a la derecha (a la altura de las dos primeras líneas)
        self.tam_icono = (self.alto_linea[0] + self.alto_linea[1]) / PT * 0.62 if self.icono else 0
        hueco = self.tam_icono * PT * 1.25 + 6 * F if self.icono else 0
        self.w = max([m[0] + (hueco if i < 2 else 0) for i, m in enumerate(medidas)]) + 2 * self.pad
        self.h = sum(self.alto_linea) + 2 * self.pad - 4 * F
        self.color = E.color_dia(_dia(plan, p.llegada))
        self.fuera = margen.total_seconds() < 0
        self.x = self.y = 0.0     # esquina superior izquierda
        self.lado = "izq"

    def dibujar(self, ax):
        ax.add_patch(FancyBboxPatch((self.x, self.y - self.h), self.w, self.h,
                                    boxstyle="square,pad=0", fc=self.color, ec="black",
                                    lw=2.5 * self.F ** 0.5, zorder=20))
        y = self.y - self.pad + 2
        for (texto, tam, peso), alto in zip(self.lineas, self.alto_linea):
            color = "#ffe14d" if self.fuera and texto.startswith("margen") else "white"
            ax.text(self.x + self.pad, y, texto, fontsize=tam, family=E.SANS, weight=peso,
                    color=color, va="top", ha="left", zorder=21)
            y -= alto
        if self.icono:
            ax.text(self.x + self.w - self.pad, self.y - self.pad * 0.8, self.icono, fontproperties=E.EMOJI,
                    fontsize=self.tam_icono, ha="right", va="top", color="white", zorder=21)

    def ancla_linea(self, ax_, ay):
        """Punto del borde de la caja más cercano a su control, donde arranca la línea."""
        return float(np.clip(self.ax_, self.x, self.x + self.w)), float(np.clip(ay, self.y - self.h, self.y))


def _colocar(cajas, TX, TY, W, Hm, F, marcas, centro=None):
    """Busca para cada caja el hueco del mapa que menos estorba: sin solapar otras cajas, sin tapar el track
    ni los controles, lejos de las zonas donde el track se concentra y a una distancia moderada de su control
    (puede alejarse bastante: la línea lleva a su punto).

    Orden: cada caja tiende a quedar en la recta que une el centro de la ruta con su punto, hacia fuera o hacia
    dentro, así que las cajas siguen el sentido de la ruta (en una ruta circular, una tras otra alrededor del
    recorrido). Al final se intercambian las cajas cuyas líneas se cruzan.

    Se prueba una rejilla de posiciones; el track se cuenta con una imagen integral, así que cada posición
    cuesta lo mismo. Primero se colocan las cajas cuyo control está en la zona más densa.
    Devuelve (forzadas, pisan, lejos): cajas que no cabían sin solaparse, que tapan el track y la mayor distancia
    de una caja a su punto (px).
    """
    g = max(4, int(round(6 * F)))                       # celda de la rejilla de ocupación (px)
    nx, ny = int(np.ceil(W / g)), int(np.ceil(Hm / g))
    # track remuestreado a ~1 punto por celda
    largo = np.hypot(np.diff(TX), np.diff(TY))
    s = np.r_[0, np.cumsum(largo)]
    t = np.arange(0, s[-1], g)
    px_, py_ = np.interp(t, s, TX), np.interp(t, s, TY)
    dentro = (px_ >= 0) & (px_ <= W) & (py_ >= 0) & (py_ <= Hm)       # solo lo que se ve en este mapa
    px_, py_ = px_[dentro], py_[dentro]
    if centro is None:
        centro = (float(px_.mean()), float(py_.mean())) if len(px_) else (W / 2, Hm / 2)

    def integral(xs, ys):
        m = np.zeros((ny + 1, nx + 1))
        ix = np.clip((np.asarray(xs) / g).astype(int), 0, nx - 1)
        iy = np.clip((np.asarray(ys) / g).astype(int), 0, ny - 1)
        np.add.at(m, (iy + 1, ix + 1), 1)
        return m.cumsum(0).cumsum(1)

    S_track = integral(px_, py_)
    S_marca = integral([m[0] for m in marcas], [m[1] for m in marcas]) if marcas else np.zeros((ny + 1, nx + 1))

    def suma(S, x0, y0, x1, y1):
        """Cuenta en rectángulos (arrays, en px; y hacia arriba)."""
        i0 = np.clip(np.floor(x0 / g).astype(int), 0, nx)
        i1 = np.clip(np.ceil(x1 / g).astype(int), 0, nx)
        j0 = np.clip(np.floor(y0 / g).astype(int), 0, ny)
        j1 = np.clip(np.ceil(y1 / g).astype(int), 0, ny)
        return S[j1, i1] - S[j0, i1] - S[j1, i0] + S[j0, i0]

    def densidad(x, y, r):
        return float(suma(S_track, np.array([x - r]), np.array([y - r]), np.array([x + r]), np.array([y + r]))[0])

    sep, borde = 14 * F, 12
    toque = 14 * F                 # el track no debe pasar a menos de esto de la caja
    entorno = 90 * F               # zona alrededor de la caja donde se mide la densidad del track
    d_min, d_ideal = 50 * F, 160 * F
    paso = max(8, int(round(14 * F)))

    def base(c):
        """Posiciones posibles de la caja y su coste sin contar las demás cajas (se calcula una vez)."""
        xs = np.arange(borde, W - c.w - borde + 1, paso)
        ys = np.arange(borde + c.h, Hm - borde + 1, paso)          # borde superior de la caja
        X, Y = np.meshgrid(xs, ys)
        X, Y = X.ravel().astype(float), Y.ravel().astype(float)
        x0, x1 = X, X + c.w
        y0, y1 = Y - c.h, Y
        coste = 400.0 * suma(S_track, x0 - toque, y0 - toque, x1 + toque, y1 + toque)
        coste += 2.0 * suma(S_track, x0 - entorno, y0 - entorno, x1 + entorno, y1 + entorno)
        coste += 3000.0 * suma(S_marca, x0 - toque, y0 - toque, x1 + toque, y1 + toque)
        # distancia del control a la caja: ni encima ni lejos (alejarse cuesta poco: la línea lleva al punto)
        dx = np.maximum(0, np.maximum(X - c.ax_, c.ax_ - (X + c.w)))
        dy = np.maximum(0, np.maximum(y0 - c.ay, c.ay - y1))
        d = np.hypot(dx, dy)
        coste += np.where(d < d_ideal, 1.2 * (d_ideal - d), 0.45 * (d - d_ideal))
        coste += np.where(d < d_min, 40.0 * (d_min - d), 0.0)
        bx, by = X + c.w / 2 - c.ax_, Y - c.h / 2 - c.ay
        # orden de la ruta: el centro de la caja, cerca de la recta centro de la ruta → punto
        ux, uy = c.ax_ - centro[0], c.ay - centro[1]
        n = np.hypot(ux, uy)
        if n > 1 and getattr(c, "objetivo", None) is None:
            coste += 0.5 * np.abs(ux / n * by - uy / n * bx)
        if getattr(c, "objetivo", None) is not None:   # ruta circular: cerca de su sitio en el borde (_objetivos_borde)
            coste += 2.0 * np.hypot(X + c.w / 2 - c.objetivo[0], Y - c.h / 2 - c.objetivo[1])
        # la línea de la caja a su punto no debe cruzar el track: la caja, del mismo lado que su punto
        for f in np.linspace(0.12, 0.88, 9):
            qx, qy = c.ax_ + f * bx, c.ay + f * by
            coste += 35.0 * (suma(S_track, qx - g, qy - g, qx + g, qy + g) > 0)
        return X, Y, coste

    def sitio(c, otras):
        """Mejor posición de c con las demás cajas ya colocadas: sin solaparlas, sin tapar sus puntos y sin que
        las líneas se crucen ni atraviesen cajas."""
        X, Y, coste = c._base
        coste = coste.copy()
        x0, x1, y0, y1 = X, X + c.w, Y - c.h, Y
        cx_, cy_ = X + c.w / 2, Y - c.h / 2
        ok = np.ones(len(X), bool)
        for o in otras:
            ok &= (x1 + sep < o.x) | (x0 - sep > o.x + o.w) | (y1 + sep < o.y - o.h) | (y0 - sep > o.y)
            # la caja no tapa el punto de la otra
            coste += np.where((o.ax_ > x0 - toque) & (o.ax_ < x1 + toque) & (o.ay > y0 - toque) & (o.ay < y1 + toque),
                              3000.0, 0.0)
            lx, ly = o.ancla_linea(None, o.ay)
            for f in np.linspace(0.1, 0.9, 5):
                # la línea de la otra no atraviesa esta caja…
                qx, qy = lx + f * (o.ax_ - lx), ly + f * (o.ay - ly)
                coste += np.where((qx > x0) & (qx < x1) & (qy > y0) & (qy < y1), 300.0, 0.0)
                # …ni la de esta, la otra caja
                qx, qy = c.ax_ + f * (cx_ - c.ax_), c.ay + f * (cy_ - c.ay)
                coste += np.where((qx > o.x) & (qx < o.x + o.w) & (qy > o.y - o.h) & (qy < o.y), 300.0, 0.0)
            # las dos líneas no se cruzan
            def lado(px_, py_, qx_, qy_, rx, ry):
                return (qx_ - px_) * (ry - py_) - (qy_ - py_) * (rx - px_)
            s1 = lado(c.ax_, c.ay, cx_, cy_, lx, ly) * lado(c.ax_, c.ay, cx_, cy_, o.ax_, o.ay)
            s2 = lado(lx, ly, o.ax_, o.ay, c.ax_, c.ay) * lado(lx, ly, o.ax_, o.ay, cx_, cy_)
            coste += np.where((s1 < 0) & (s2 < 0), 250.0, 0.0)
        forzada = not ok.any()
        if forzada:
            ok[:] = True                 # no cabe: mejor solapada que fuera del mapa
        aqui = float(coste[int(np.argmin(np.hypot(X - c.x, Y - c.y)))]) if hasattr(c, "x") else np.inf
        coste = np.where(ok, coste, np.inf)
        k = int(np.argmin(coste))
        return float(X[k]), float(Y[k]), float(coste[k]), forzada, aqui

    for c in cajas:
        c._base = base(c)
    colocadas = []
    for c in sorted(cajas, key=lambda c: -densidad(c.ax_, c.ay, 150 * F)):
        c.x, c.y, _, c.forzada, _ = sitio(c, colocadas)
        c.reserva = 0
        colocadas.append(c)
    # rondas de recolocación, en el orden de la ruta: cada caja busca su mejor sitio con las demás ya puestas
    for _ in range(4):
        cambios = 0
        for c in cajas:
            x, y, coste, forzada, aqui = sitio(c, [o for o in cajas if o is not c])
            if coste < aqui - 1e-6:
                c.x, c.y, c.forzada = x, y, forzada
                cambios += 1
        if not cambios:
            break
    for c in cajas:
        del c._base
    _descruzar(cajas, W, Hm, sep, borde, lambda c: suma(S_track, np.array([c.x]), np.array([c.y - c.h]),
                                                        np.array([c.x + c.w]), np.array([c.y]))[0])
    for c in cajas:
        c.lado = "izq" if c.x + c.w / 2 < c.ax_ else "der"
    pisan = sum(1 for c in cajas if suma(S_track, np.array([c.x + 2]), np.array([c.y - c.h + 2]),
                                         np.array([c.x + c.w - 2]), np.array([c.y - 2]))[0] > 0)
    lejos = max((_dist_caja(c) for c in cajas), default=0.0)
    return sum(c.forzada for c in cajas), pisan, lejos


def _objetivos_borde(cajas, W, Hm, centro, antihorario, F):
    """Ruta circular: reparte las cajas, en el orden de la ruta, a lo largo del borde del mapa. Cada una apunta
    adonde corta el borde la recta que sale del centro de la ruta y pasa por su punto; luego se separan a lo
    largo del borde en el sentido de la ruta (horario o antihorario), para que no se amontonen ni se crucen.
    Deja en cada caja `objetivo` (centro deseado, px)."""
    borde = 12 + 6 * F
    wm = float(np.mean([c.w for c in cajas]))
    hm = float(np.mean([c.h for c in cajas]))
    L, R, B, T = borde + wm / 2, W - borde - wm / 2, borde + hm / 2, Hm - borde - hm / 2
    if R <= L or T <= B:
        return
    ancho, alto = R - L, T - B
    P = 2 * (ancho + alto)

    def a_t(x, y):
        """Coordenada a lo largo del borde (antihoraria desde la esquina inferior izquierda)."""
        if abs(y - B) < 1e-6:
            return x - L
        if abs(x - R) < 1e-6:
            return ancho + (y - B)
        if abs(y - T) < 1e-6:
            return ancho + alto + (R - x)
        return 2 * ancho + alto + (T - y)

    def de_t(t):
        t %= P
        if t < ancho:
            return L + t, B, "h"
        t -= ancho
        if t < alto:
            return R, B + t, "v"
        t -= alto
        if t < ancho:
            return R - t, T, "h"
        return L, T - (t - ancho), "v"

    def rayo(px_, py_):
        dx, dy = px_ - centro[0], py_ - centro[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            dy = -1.0
        k = min([v for v in ((R - centro[0]) / dx if dx > 0 else np.inf, (L - centro[0]) / dx if dx < 0 else np.inf,
                             (T - centro[1]) / dy if dy > 0 else np.inf, (B - centro[1]) / dy if dy < 0 else np.inf)])
        x, y = np.clip(centro[0] + k * dx, L, R), np.clip(centro[1] + k * dy, B, T)
        # al borde más cercano (el punto de corte ya está en uno)
        dist = [abs(y - B), abs(x - R), abs(y - T), abs(x - L)]
        j = int(np.argmin(dist))
        x, y = [(x, B), (R, y), (x, T), (L, y)][j]
        return a_t(x, y)

    signo = 1.0 if antihorario else -1.0
    t = np.array([rayo(c.ax_, c.ay) for c in cajas])
    u = np.unwrap((signo * (t - t[0])) % P * 2 * np.pi / P) * P / (2 * np.pi)   # avance a lo largo del borde
    u -= u[0]

    def hueco(c, ui):
        _, _, lado = de_t(t[0] + signo * ui)
        return (c.w if lado == "h" else c.h) + 10 * F

    # separar: hacia delante y hacia atrás, y la media de las dos pasadas
    n = len(cajas)
    for _ in range(6):
        ade = u.copy()
        for i in range(1, n):
            ade[i] = max(ade[i], ade[i - 1] + (hueco(cajas[i - 1], ade[i - 1]) + hueco(cajas[i], ade[i])) / 2)
        atr = u.copy()
        for i in range(n - 2, -1, -1):
            atr[i] = min(atr[i], atr[i + 1] - (hueco(cajas[i + 1], atr[i + 1]) + hueco(cajas[i], atr[i])) / 2)
        u = (ade + atr) / 2
    # si no caben en una vuelta, se comprimen (el optimizador las ajustará)
    largo = u[-1] - u[0]
    if largo > P * 0.97:
        u = u[0] + (u - u[0]) * P * 0.97 / largo
    for c, ui in zip(cajas, u):
        x, y, _ = de_t(t[0] + signo * ui)
        c.objetivo = (float(x), float(y))


def _dist_caja(c):
    dx = max(0.0, c.x - c.ax_, c.ax_ - (c.x + c.w))
    dy = max(0.0, (c.y - c.h) - c.ay, c.ay - c.y)
    return float(np.hypot(dx, dy))


def _cortan(a, b, c, d):
    """¿Se cortan los segmentos ab y cd (sin contar los extremos)?"""
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def _descruzar(cajas, W, Hm, sep, borde, track_en):
    """Intercambia las cajas cuyas líneas se cruzan (centro por centro), si así no se solapan con otras, no se
    salen del mapa, no tapan más track y bajan los cruces. `cajas` va en el orden de la ruta."""
    def linea(c):
        return c.ancla_linea(None, c.ay), (c.ax_, c.ay)

    def cruces(c, otras):
        a, b = linea(c)
        n = 0
        for o in otras:
            if o is c:
                continue
            p, q = linea(o)
            n += _cortan(a, b, p, q)
            # la línea atraviesa otra caja
            for f in np.linspace(0.1, 0.9, 5):
                x, y = a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])
                if o.x < x < o.x + o.w and o.y - o.h < y < o.y:
                    n += 1
                    break
        return n

    def total():
        return sum(cruces(c, cajas) for c in cajas)

    def valida(c):
        if c.x < borde or c.x + c.w > W - borde or c.y - c.h < borde or c.y > Hm - borde:
            return False
        return all(o is c or (c.x + c.w + sep < o.x) or (c.x - sep > o.x + o.w) or (c.y + sep < o.y - o.h)
                   or (c.y - c.h - sep > o.y) for o in cajas)

    for _ in range(4 * len(cajas)):
        actual = total()
        if not actual:
            return
        mejora = False
        for i, a in enumerate(cajas):
            for b in cajas[i + 1:i + 4]:      # solo cajas próximas en la ruta: las lejanas cambiarían de lado
                pa, pb = linea(a), linea(b)
                if not _cortan(*pa, *pb):
                    continue
                antes = (a.x, a.y, b.x, b.y)
                pisa = track_en(a) + track_en(b)
                ca = (a.x + a.w / 2, a.y - a.h / 2)
                cb = (b.x + b.w / 2, b.y - b.h / 2)
                a.x, a.y = cb[0] - a.w / 2, cb[1] + a.h / 2
                b.x, b.y = ca[0] - b.w / 2, ca[1] + b.h / 2
                if valida(a) and valida(b) and track_en(a) + track_en(b) <= pisa and total() < actual:
                    mejora = True
                    break
                a.x, a.y, b.x, b.y = antes
            if mejora:
                break
        if not mejora:
            return


# ------------------------------------------------------------------ perfil

def _filas_etiquetas(fig, panel, total, ancho_px, tam):
    """Reparte las etiquetas de los controles del perfil en filas sin solaparse."""
    km_por_px = total / ancho_px
    filas_fin, colocadas = [], []
    for p in panel:
        t1 = _etiqueta_control(p)
        t2 = f"km {p.km:.0f}  (+{p.asc_total:.0f} m)"
        w = max(_medir(fig, t1, tam, "bold")[0], _medir(fig, t2, tam, "bold")[0]) + 1.3 * tam
        x0 = p.km - 0.5 * tam * km_por_px
        x1 = x0 + w * km_por_px
        if x1 > total:
            x0, x1 = total - w * km_por_px, total
        fila = next((i for i, fin in enumerate(filas_fin) if x0 > fin + 0.3 * tam * km_por_px), None)
        if fila is None:
            fila = len(filas_fin)
            filas_fin.append(x1)
        else:
            filas_fin[fila] = x1
        colocadas.append((p, fila, x0, t1, t2))
    return colocadas, max(1, len(filas_fin))


def _dibujar_perfil(fig, rect_perfil, rect_etiquetas, rect_dias, plan, panel, puertos, cfg,
                    etiquetas, tam_etq=None):
    tr = plan.track
    total = tr.total_km
    F = _escala(cfg)
    ax = fig.add_axes(rect_perfil)
    paso = max(1, int(round(0.2 / (tr.km[1] - tr.km[0]))))  # tramos de ~200 m
    km, ele = tr.km[::paso], tr.ele[::paso]
    pend = np.diff(ele) / (np.diff(km) * 1000) * 100
    polis = [[(km[i], 0), (km[i], ele[i]), (km[i + 1], ele[i + 1]), (km[i + 1], 0)]
             for i in range(len(km) - 1)]
    ax.add_collection(PolyCollection(polis, facecolors=[E.color_pendiente(s) for s in pend],
                                     edgecolors="none"))
    ax.plot(km, ele, color="#5a4a1a", lw=0.8 * F)
    tope = max(ele.max() * 1.25, 500)
    ax.set_xlim(0, total)
    ax.set_ylim(0, tope)
    ax.set_yticks(np.arange(0, tope, 250 if tope < 2600 else 500))
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f} m".replace(",", " "))
    ax.set_xticks(np.arange(0, total + 1, 60 if total > 600 else 20))
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f} km")
    ax.tick_params(labelsize=10 * F, length=3 * F)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_family(E.SANS)
    ax.grid(axis="y", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    # puertos de montaña (OSM)
    # todos los puertos con su triángulo; nombre solo del más alto de cada zona
    rotulados = []
    for nombre, kmp, alt in sorted(puertos, key=lambda x: -x[2]):
        ax.plot(kmp, alt, marker="^", ms=7 * F, color="#3b2a10", mec="white", mew=0.8, zorder=6)
        if any(abs(kmp - k) < total * 0.045 * F for k in rotulados):
            continue
        rotulados.append(kmp)
        ax.text(kmp, alt + tope * 0.03, f"{nombre}\n{alt:.0f} m", fontsize=8.5 * F, family=E.SANS,
                ha="center", va="bottom", color="#3b2a10", zorder=6, path_effects=HALO)

    # controles: líneas verticales (los del panel resaltados)
    ids_panel = {id(p) for p in panel}
    for p in plan.puntos:
        if not (p.es_control or p.destacado):
            continue
        destacado = id(p) in ids_panel
        ax.plot([p.km, p.km], [0, tope], color="#555555" if destacado else "#9a9a9a",
                lw=(3 if destacado else 1) * F ** 0.5, alpha=0.9 if destacado else 0.5, zorder=3)

    # etiquetas del panel en filas sin solaparse
    ae = fig.add_axes(rect_etiquetas, sharex=ax)
    ae.axis("off")
    ae.set_ylim(0, 1)
    colocadas, n_filas = etiquetas
    tam = tam_etq or 13 * F
    alto_fila = 1 / n_filas
    for p, fila, x0, t1, t2 in colocadas:
        y_top = 1 - fila * alto_fila
        y_bot = y_top - alto_fila * 0.92
        ae.plot([p.km, p.km], [0, y_bot], color="#555555", lw=3 * F ** 0.5, zorder=1)
        ae.text(x0, (y_top + y_bot) / 2, f"{t1}\n{t2}", fontsize=tam, family=E.SANS, weight="bold",
                color="white", va="center", ha="left", linespacing=1.15, zorder=3,
                bbox=dict(boxstyle="square,pad=0.35", fc="#6e6e6e", ec="black", lw=2))

    # banda de días bajo el perfil
    ad = fig.add_axes(rect_dias, sharex=ax)
    ad.axis("off")
    ad.set_ylim(0, 1)
    kms = tr.km[::paso]
    dias = np.array([_dia(plan, t) for t in hora_en_km(plan, kms)])
    cortes = np.flatnonzero(np.diff(dias)) + 1
    tramos = np.split(np.arange(len(kms)), cortes)
    for idx in tramos:
        d = dias[idx[0]]
        a, b = kms[idx[0]], kms[min(idx[-1] + 1, len(kms) - 1)]
        ad.add_patch(Rectangle((a, 0), b - a, 1, color=E.color_dia(d), lw=0))
        fecha = plan.salida.date() + timedelta(days=int(d))
        etiqueta = f"{fecha.day} {MESES[fecha.month - 1][:3]}"
        if (b - a) / total > 0.04:
            ad.text((a + b) / 2, 0.5, etiqueta, ha="center", va="center", color="white",
                    fontsize=10 * F, family=E.SANS, weight="bold")
    return ax


def _puertos_en_ruta(track, puertos, max_dist_m=400):
    """Sitúa los puertos de OSM sobre el track (pueden aparecer más de una vez)."""
    salida = []
    if not puertos:
        return salida
    x, y = a_mercator(track.lon, track.lat)
    escala = np.cos(np.radians(track.lat.mean()))
    for pu in puertos:
        px, py = a_mercator(pu["lon"], pu["lat"])
        d = np.hypot(x - px, y - py) * escala
        cerca = d < max_dist_m
        if not cerca.any():
            continue
        # un paso por cada grupo de puntos cercanos separados más de 5 km
        idx = np.flatnonzero(cerca)
        grupos = np.split(idx, np.flatnonzero(np.diff(track.km[idx]) > 5) + 1)
        for g in grupos:
            i = g[np.argmin(d[g])]
            alt = pu["ele"] or float(track.ele[i])
            nombre = pu["nombre"].replace("Puerto de ", "Pto. de ").replace("Puerto del ", "Pto. del ")
            salida.append((nombre, float(track.km[i]), alt))
    return salida


# ------------------------------------------------------------------ topónimos

class _Huecos:
    """Zonas ocupadas del mapa (cajas, rótulos y track) para colocar topónimos sin solaparse."""

    def __init__(self, W, Hm, TX, TY, rects, res=8):
        self.W, self.Hm, self.res = W, Hm, res
        self.rects = list(rects)
        self.track = np.zeros((int(Hm // res) + 2, int(W // res) + 2), bool)
        ix = np.clip((TX / res).astype(int), 0, self.track.shape[1] - 1)
        iy = np.clip((TY / res).astype(int), 0, self.track.shape[0] - 1)
        for d in (-1, 0, 1):
            self.track[np.clip(iy + d, 0, self.track.shape[0] - 1), ix] = True
            self.track[iy, np.clip(ix + d, 0, self.track.shape[1] - 1)] = True

    def libre(self, r, margen=6):
        x0, y0, x1, y1 = r
        if x0 < 10 or y0 < 10 or x1 > self.W - 10 or y1 > self.Hm - 10:
            return False
        if any(not (x1 + margen < a[0] or x0 - margen > a[2] or y1 + margen < a[1] or y0 - margen > a[3])
               for a in self.rects):
            return False
        c = self.track[int(y0 // self.res):int(y1 // self.res) + 1, int(x0 // self.res):int(x1 // self.res) + 1]
        return not c.any()


def _toponimos(fig, ax, osm, pxll, huecos, TX, TY, F, cfg):
    """Nombres de sierras, ríos, embalses y comarcas sobre el mapa base."""
    if not osm:
        return
    halo = [pe.withStroke(linewidth=4 * F ** 0.5, foreground="white")]
    W, Hm = huecos.W, huecos.Hm

    def poner(texto, x, y, kw, rot=0):
        w, h = _medir(fig, texto, kw["fontsize"], kw.get("weight", "regular"))
        s = abs(np.sin(np.radians(rot)))
        r = (x - w / 2, y - w / 2 * s - h / 2, x + w / 2, y + w / 2 * s + h / 2)
        if huecos.libre(r):
            ax.text(x, y, texto, ha="center", va="center", rotation=rot, rotation_mode="anchor",
                    zorder=12, path_effects=halo, family=E.SANS, **kw)
            huecos.rects.append(r)
            return True
        return False

    def cerca(x, y):
        return float(np.min(np.hypot(TX[::25] - x, TY[::25] - y)))

    # sierras: las más próximas a la ruta
    vistas = set()
    sierras = []
    for sr in osm.get("sierras", []):
        x, y = pxll(sr["lon"], sr["lat"])
        nombre = sr["nombre"].strip()
        if nombre.lower() in vistas or not (0 < x < W and 0 < y < Hm):
            continue
        vistas.add(nombre.lower())
        sierras.append((cerca(x, y), nombre, x, y))
    puestas = 0
    for _, nombre, x, y in sorted(sierras):
        if puestas >= cfg.get("sierras_max", 6):
            break
        kw = dict(fontsize=13 * F, weight="semibold", color="#5a3d1e")
        for dx, dy in ((0, 0), (0, 40 * F), (0, -40 * F), (60 * F, 0), (-60 * F, 0)):
            if poner(nombre.upper(), x + dx, y + dy, kw):
                puestas += 1
                break

    # ríos: los más largos dentro del mapa, rotulados a lo largo del cauce
    rios = []
    for nombre, tramos in osm.get("rios", {}).items():
        xs, ys = [], []
        for t in tramos:
            lat, lon = np.array(t).T
            x, y = pxll(lon, lat)
            dentro = (x > 0) & (x < W) & (y > 0) & (y < Hm)
            xs.append(x[dentro])
            ys.append(y[dentro])
        x, y = np.concatenate(xs), np.concatenate(ys)
        if len(x) > 4:
            rios.append((len(x), nombre.split(" / ")[0], x, y))
    puestos = 0
    for _, nombre, x, y in sorted(rios, key=lambda r: -r[0]):
        if puestos >= cfg.get("rios_max", 10):
            break
        kw = dict(fontsize=12 * F, weight="medium", color="#1d5f8a")
        for i in np.argsort(np.abs(np.arange(len(x)) - len(x) / 2))[::4]:
            j0, j1 = max(0, i - 6), min(len(x) - 1, i + 6)
            ang = np.degrees(np.arctan2(y[j1] - y[j0], x[j1] - x[j0]))
            ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
            if poner(nombre, x[i], y[i] + 10 * F, kw, ang):
                puestos += 1
                break

    # embalses grandes
    puestos = 0
    for e in sorted(osm.get("embalses", []), key=lambda e: -e["tam_km"]):
        if puestos >= cfg.get("embalses_max", 6) or e["tam_km"] < 1.5:
            break
        x, y = pxll(e["lon"], e["lat"])
        kw = dict(fontsize=11 * F, weight="medium", color="#1d5f8a")
        for dy in (-22 * F, 22 * F, 0):
            if poner(e["nombre"], x, y + dy, kw):
                puestos += 1
                break

    # comarcas
    puestas = 0
    for c in sorted(osm.get("comarcas", []), key=lambda c: cerca(*pxll(c["lon"], c["lat"]))):
        if puestas >= cfg.get("comarcas_max", 6):
            break
        x, y = pxll(c["lon"], c["lat"])
        texto = "  ".join(" ".join(p) for p in c["nombre"].upper().split())
        kw = dict(fontsize=11 * F, weight="semibold", color="#6b6b6b")
        for dx, dy in ((0, 0), (0, 30 * F), (0, -30 * F)):
            if poner(texto, x + dx, y + dy, kw):
                puestas += 1
                break


# ------------------------------------------------------------------ infografía

def _servicios(ax, servicios, pxll, rects, TX, TY, W, Hm, F, maximo=80):
    """Iconos de fuentes, bares, tiendas y gasolineras junto al track, fuera de las cajas y sin tapar el track."""
    lado = 15 * F ** 0.55 * PT * 1.25
    paso = max(1, len(TX) // 4000)
    tx, ty = np.asarray(TX)[::paso], np.asarray(TY)[::paso]
    puestos = 0
    for sv in servicios:
        if puestos >= maximo:
            break
        x, y = pxll(sv["lon"], sv["lat"])
        sitio = None
        for f in (0.9, 1.4, 2.0):
            for ang in np.radians([90, 270, 0, 180, 45, 135, 225, 315]):
                cx, cy = x + np.cos(ang) * lado * f, y + np.sin(ang) * lado * f
                r = (cx - lado / 2, cy - lado / 2, cx + lado / 2, cy + lado / 2)
                if not (4 < r[0] and r[2] < W - 4 and 4 < r[1] and r[3] < Hm - 4):
                    continue
                if any(not (r[2] < q[0] or r[0] > q[2] or r[3] < q[1] or r[1] > q[3]) for q in rects):
                    continue
                if np.min(np.hypot(tx - cx, ty - cy)) < lado * 0.5 + 6 * F ** 0.5:
                    continue
                sitio = (cx, cy, r)
                break
            if sitio:
                break
        if not sitio:
            continue
        cx, cy, r = sitio
        ax.plot([x, cx], [y, cy], color="#1b1b1b", lw=1.2, alpha=0.7, zorder=13)
        ax.add_patch(Circle((cx, cy), lado * 0.5, fc="white", ec="#1b1b1b", lw=1.6, zorder=13.5))
        ax.text(cx, cy, E.ICONOS_SERVICIO[sv["tipo"]], fontproperties=E.EMOJI, fontsize=15 * F ** 0.55 * 0.72,
                ha="center", va="center", color="#1b1b1b", zorder=14)
        rects.append(r)
        puestos += 1


def generar(proyecto, plan, osm=None):
    cfg = proyecto.seccion("infografia")
    W = int(cfg.get("ancho_px", 2400))
    proporcion = cfg.get("proporcion_mapa", 4 / 3)
    estilo = cfg.get("estilo", "ign_mtn")
    sin_caja = set(cfg.get("sin_caja", []))
    tr = plan.track

    # ---- cobertura del mapa base (con el encuadre de toda la ruta)
    X, Y = a_mercator(tr.lon, tr.lat)
    xmin, xmax, ymin, ymax = _encuadre(X, Y, cfg, proporcion)
    z = zoom_para(xmin, xmax, W / cfg.get("escala_rotulos", 1.0), estilo)
    if estilo.startswith("ign_") and not cubre(estilo, z, X, Y):
        print(f"  aviso: el mapa del IGN solo cubre España; la ruta sale de su cobertura y se usa el topográfico de OpenStreetMap",
              file=sys.stderr)
        estilo = "topo"

    def px(x, y):
        return (x - xmin) / (xmax - xmin) * W, (y - ymin) / (ymax - ymin) * Hm

    # ---- reparto de las cajas en mapas (uno, si caben)
    fig_medir = plt.figure(figsize=(W / 100, 10), dpi=100)
    disposiciones = _disponer(fig_medir, plan, cfg, sin_caja, X, Y, W)
    plt.close(fig_medir)
    print(f"  infografía: {len(disposiciones)} mapa(s); cajas al " +
          ", ".join(f"{d['esc']:.0%}" for d in disposiciones), file=sys.stderr)
    horas = hora_en_km(plan, tr.km)
    dias_track = np.array([_dia(plan, t) for t in horas])
    puertos = _puertos_en_ruta(tr, (osm or {}).get("puertos", []))
    servicios = (osm or {}).get("servicios", []) if cfg.get("servicios", True) and estilo.startswith("ign_") else []

    F = _escala(cfg)
    perfil_h, dias_h, pie_base = int(220 + 90 * F), int(22 * F), int(34 * F)
    salidas = []
    for n_panel, disp in enumerate(disposiciones, 1):
        panel = disp["panel"]
        xmin, xmax, ymin, ymax = disp["encuadre"]
        Hm = disp["Hm"]
        z = zoom_para(xmin, xmax, W / cfg.get("escala_rotulos", 1.0), estilo)
        base = mapa_base(xmin, ymin, xmax, ymax, z, estilo)
        TX, TY = px(X, Y)
        fig = plt.figure(figsize=(W / 100, 10), dpi=100)
        fig.patch.set_facecolor("white")
        marg_x = 0.03 + 0.02 * F
        tam_etq = 13 * F * max(0.75, disp["esc"])      # las etiquetas del perfil, como las cajas (algo menos)
        etiquetas = _filas_etiquetas(fig, panel, tr.total_km, (0.985 - 2 * marg_x) * W, tam_etq)
        etq_h = int(etiquetas[1] * tam_etq * PT * 3.4)
        # cabecera: alto medido de cada línea (título, datos y fechas) para que no se pisen
        titulo = proyecto.nombre.upper()
        total_h = plan.llegada_final - plan.salida
        datos = (f"{plan.total_km:.0f} km  ·  +{plan.total_asc:,.0f} m  ·  salida "
                 f"{plan.salida:%d/%m %H:%M} h  ·  límite {fmt_dur(timedelta(hours=plan.limite_h))} h  ·  "
                 f"tiempo previsto {fmt_dur(total_h)} h  ·  margen en meta "
                 f"{fmt_dur(plan.puntos[-1].margen, signo=True)} h").replace(",", " ")
        pad_chip = 0.35 * 15 * F * PT
        h_tit = _medir(fig, titulo, 34 * F, "bold")[1]
        h_dat = _medir(fig, datos, 15 * F, "medium")[1]
        h_chip = _medir(fig, "18 / Agosto / 2026", 15 * F, "bold")[1] + 2 * pad_chip
        hueco_cab = 10 * F
        cab_h = int(16 + h_tit + hueco_cab + h_dat + hueco_cab * 1.5 + h_chip + 16)
        # pie: atribución a la izquierda y leyenda de los tipos de parada a la derecha; si no caben juntas,
        # la leyenda va en una línea encima y el pie crece
        atrib = ESTILOS[estilo][3]
        if (osm or {}).get("fuente_nombres") == "ign" and "IGN" not in atrib:
            atrib += "  ·  Nombres: NGBE, © IGN España (CC BY 4.0)"
        atrib = f"{atrib}  ·  Altitudes: EU-DEM 25 m (OpenTopoData)  ·  Tiempos estimados según pendiente media de cada tramo"
        usados = {p.tipo_parada for p in plan.puntos if p.tipo_parada}
        ley_serv = E.leyenda_servicios(servicios)
        items = [f"{E.ICONOS[k]} {n}" for k, n in E.NOMBRES_TIPO.items() if k in usados and k in E.ICONOS] + ([ley_serv] if ley_serv else [])
        w_atrib, h_atrib = _medir(fig, atrib, 9.5 * F, "regular")
        ancho_ley = lambda s: _medir(fig, s, 11 * F, "regular")[0] * 1.15
        util = 0.98 * W
        # Leyenda de tipos partida en líneas que quepan en el ancho (hoy, con todos los tipos, cabe en una)
        lineas_ley = []
        for it in items:
            if lineas_ley and ancho_ley(lineas_ley[-1] + "  " + it) <= util:
                lineas_ley[-1] += "  " + it
            else:
                lineas_ley.append(it)
        w_pend = _ancho_pendiente(fig, F) if cfg.get("track_pendiente") else 0
        # Filas del pie por encima de la atribución, de abajo arriba: nada comparte línea si no cabe entero
        tipos_en_atrib = (len(lineas_ley) == 1 and not w_pend
                          and 0.01 * W + w_atrib + 20 * F + ancho_ley(lineas_ley[0]) <= 0.99 * W)
        filas, resto = [], ([] if tipos_en_atrib else lineas_ley)
        if w_pend:
            if resto and w_pend + 30 * F + ancho_ley(resto[-1]) <= util:
                filas.append((True, resto[-1]))
                resto = resto[:-1]
            else:
                filas.append((True, None))
        filas += [(False, x) for x in reversed(resto)]
        h_fila = max(h_atrib, _medir(fig, "Ág", 11 * F, "regular")[1]) + 8 * F
        pie_h = pie_base + int(len(filas) * h_fila)
        H = cab_h + Hm + etq_h + perfil_h + dias_h + pie_h + 40
        fig.set_size_inches(W / 100, H / 100)

        def rect(y_px, alto_px, x0=0.0, ancho=1.0):
            return [x0, y_px / H, ancho, alto_px / H]

        y_mapa = pie_h + dias_h + perfil_h + etq_h + 30
        ax = fig.add_axes(rect(y_mapa, Hm))
        ax.imshow(base, extent=(0, W, 0, Hm), interpolation="lanczos", zorder=0)
        ax.add_patch(Rectangle((0, 0), W, Hm, color="white", alpha=cfg.get("aclarar", 0.25), zorder=1))
        ax.set_xlim(0, W)
        ax.set_ylim(0, Hm)
        ax.axis("off")

        # track: halo oscuro y color por día
        pts = np.c_[TX, TY]
        segs_todos = np.stack([pts[:-1], pts[1:]], axis=1)
        km0, km1 = disp["km"]
        en_panel = (tr.km >= km0) & (tr.km <= km1)
        # fuera del panel: trazo fino y atenuado; dentro: halo oscuro y color por día
        for d in np.unique(dias_track):
            sel = (dias_track == d) & ~en_panel
            ax.add_collection(LineCollection(segs_todos[sel[:-1] & sel[1:]], colors=E.color_dia(d),
                                             lw=3, alpha=0.45, capstyle="round", zorder=4))
        ax.plot(TX[en_panel], TY[en_panel], color="#1b1b1b", lw=(8.5 if cfg.get("track_pendiente") else 8) * F ** 0.5,
                alpha=0.9 if cfg.get("track_pendiente") else 0.6, solid_capstyle="round", zorder=5)
        if cfg.get("track_pendiente"):
            # pendiente en el sentido de la ruta, en tramos de ~200 m como el perfil; llano y bajadas, color claro
            km_t, ele_t = np.asarray(tr.km, float), np.asarray(tr.ele, float)
            paso = max(1, int(round(0.2 / max(km_t[1] - km_t[0], 1e-6))))
            idx = np.arange(0, len(km_t), paso)
            if idx[-1] != len(km_t) - 1:
                idx = np.r_[idx, len(km_t) - 1]
            pend = np.diff(ele_t[idx]) / np.maximum(np.diff(km_t[idx]) * 1000, 1) * 100
            tramo = np.clip(np.searchsorted(idx, np.arange(len(km_t) - 1), side="right") - 1, 0, len(pend) - 1)
            colores = np.array([E.color_pendiente(x) for x in pend])[tramo]
            seg_ok = en_panel[:-1] & en_panel[1:]
            if len(np.unique(dias_track[en_panel])) > 1:     # varios días: el día, en el borde del track
                for d in np.unique(dias_track):
                    sel = (dias_track == d) & en_panel
                    ax.add_collection(LineCollection(segs_todos[sel[:-1] & sel[1:]], colors=E.color_dia(d),
                                                     lw=7 * F ** 0.5, capstyle="round", zorder=5.5))
            ax.add_collection(LineCollection(segs_todos[seg_ok], colors=colores[seg_ok],
                                             lw=4.5 * F ** 0.5, capstyle="round", zorder=6))
        else:
            for d in np.unique(dias_track):
                sel = (dias_track == d) & en_panel
                ax.add_collection(LineCollection(segs_todos[sel[:-1] & sel[1:]], colors=E.color_dia(d),
                                                 lw=4.5 * F ** 0.5, capstyle="round", zorder=6))

        # todos los controles, marcados discretamente
        for p in plan.puntos:
            if p.es_control:
                cx, cy = px(*a_mercator(p.lon, p.lat))
                ax.plot(cx, cy, "o", ms=8 * F ** 0.5, mfc="white", mec="#1b1b1b", mew=2, zorder=8)

        # salida y meta
        x0, y0 = px(*a_mercator(plan.puntos[0].lon, plan.puntos[0].lat))
        ax.plot(x0, y0, "o", ms=16 * F ** 0.6, mfc=E.color_dia(0), mec="black", mew=2.5, zorder=9)
        ax.text(x0, y0, "\U0001F3C1", fontproperties=E.EMOJI, fontsize=11 * F ** 0.6, ha="center",
                va="center", zorder=10, color="white")

        # cajas (ya colocadas en _disponer)
        cajas = disp["cajas"]
        if cajas:
            for c in cajas:
                lx, ly = c.ancla_linea(ax, c.ay)
                ax.plot([lx, c.ax_], [ly, c.ay], color="black", lw=2.2 * F ** 0.5, zorder=15,
                        path_effects=[pe.withStroke(linewidth=5 * F ** 0.5, foreground="white")])
                ax.plot(c.ax_, c.ay, "o", ms=12 * F ** 0.6, mfc="white", mec=c.color, mew=3.5, zorder=16)
                c.dibujar(ax)

        # cambios de día dentro del panel: la etiqueta, al lado que no tape ninguna caja
        # zonas ocupadas: cajas (con su icono) y marca de salida
        rects = [(c.x, c.y - c.h, c.x + c.w, c.y) for c in cajas]
        rects.append((x0 - 25 * F, y0 - 25 * F, x0 + 25 * F, y0 + 25 * F))
        for d in np.unique(dias_track[en_panel])[1:]:
            i = int(np.argmax((dias_track == d) & en_panel))
            fecha = plan.salida.date() + timedelta(days=int(d))
            texto = f"00:00 · {fecha.day} {MESES[fecha.month - 1][:3]}"
            tw, th = _medir(fig, texto, 11 * F, "bold")
            sep = 12 * F
            opciones = [(TX[i] + sep, "left"), (TX[i] - sep, "right")]
            def tapa(x0, ha):
                xa = x0 if ha == "left" else x0 - tw
                return any(not (xa + tw < r[0] or xa > r[2] or TY[i] + th < r[1] or TY[i] - th > r[3])
                           for r in rects)
            x_et, ha = next(((x0, ha) for x0, ha in opciones if not tapa(x0, ha)), opciones[0])
            ax.plot(TX[i], TY[i], "o", ms=9 * F ** 0.5, mfc="white", mec=E.color_dia(d), mew=3, zorder=17)
            ax.text(x_et, TY[i], texto, fontsize=11 * F, family=E.SANS, weight="bold", color="white",
                    va="center", ha=ha, zorder=17,
                    bbox=dict(boxstyle="round,pad=0.25", fc=E.color_dia(d), ec="none"))
            xa = x_et if ha == "left" else x_et - tw
            rects.append((xa - 6, TY[i] - th, xa + tw + 6, TY[i] + th))

        # servicios junto al track (solo con el mapa del IGN, que no los trae; los de OSM ya los muestran)
        if servicios:
            _servicios(ax, servicios, lambda lon, lat: px(*a_mercator(lon, lat)), rects, TX, TY, W, Hm, F)

        # topónimos del mapa base: sierras, ríos, embalses y comarcas
        if cfg.get("toponimos", True):
            _toponimos(fig, ax, osm, lambda lon, lat: px(*a_mercator(lon, lat)),
                       _Huecos(W, Hm, TX, TY, rects), TX, TY, F, cfg)

        # ---- cabecera
        ac = fig.add_axes(rect(H - cab_h, cab_h))
        ac.axis("off")
        ac.set_xlim(0, W)
        ac.set_ylim(0, cab_h)
        sub = proyecto.cfg.get("subtitulo", "")
        ac.text(28, cab_h - 16, titulo, fontsize=34 * F, family=E.SANS, weight="bold", va="top")
        ancho_t = _medir(fig, titulo, 34 * F, "bold")[0]
        ac.text(28, cab_h - 16 - h_tit - hueco_cab, datos, fontsize=15 * F, family=E.SANS,
                weight="medium", color="#222222", va="top")
        # marca: logotipo y enlace en la esquina derecha
        from .ilustrado import _logo_y_texto
        logo, texto_marca = _logo_y_texto(proyecto.seccion("marca"), proyecto.base)
        x_marca = W - 28
        kw_marca = dict(fontsize=12 * F, family=E.SANS, weight="medium", color="#333333")
        h_txt = _medir(fig, texto_marca, 12 * F, "medium")[1] if texto_marca else 0
        if logo is not None:
            alto_logo = cab_h - 32 - h_txt * 1.3
            w_logo = alto_logo / logo.shape[0] * logo.shape[1]
            w_txt = _medir(fig, texto_marca, 12 * F, "medium")[0] if texto_marca else 0
            cx_m = W - 28 - max(w_logo, w_txt) / 2
            ac.imshow(logo, extent=(cx_m - w_logo / 2, cx_m + w_logo / 2, cab_h - 16 - alto_logo, cab_h - 16),
                      aspect="auto", interpolation="lanczos", zorder=3)
            ac.set_xlim(0, W)
            ac.set_ylim(0, cab_h)
            x_marca = W - 28 - max(w_logo, w_txt) - 30 * F
            if texto_marca:
                ac.text(cx_m, 14, texto_marca, ha="center", va="bottom", **kw_marca)
        elif texto_marca:
            ac.text(W - 28, 14, texto_marca, ha="right", va="bottom", **kw_marca)
        n_paneles = len(disposiciones)
        if n_paneles > 1:     # «Hoja 1 de 2», en la fila de los días, junto a la marca: no choca con el subtítulo
            ac.text(x_marca, 16 + pad_chip, f"Hoja {n_panel} de {n_paneles}", fontsize=15 * F,
                    family=E.SANS, weight="bold", color="#777777", ha="right", va="bottom")
        if sub:   # si no cabe hasta la marca, más pequeño y, como último recurso, recortado
            x_sub, libre = 28 + ancho_t + 18 * F, x_marca - (28 + ancho_t + 18 * F) - 10 * F
            tam_sub = 20 * F
            while tam_sub > 13 * F and _medir(fig, sub, tam_sub, "medium")[0] > libre:
                tam_sub -= F
            texto_sub = sub
            while len(texto_sub) > 4 and _medir(fig, texto_sub, tam_sub, "medium")[0] > libre:
                texto_sub = texto_sub[:-2].rstrip() + "…"
                texto_sub = texto_sub.replace("……", "…")
            if libre > 40 * F:
                ac.text(x_sub, cab_h - 16 - (h_tit - _medir(fig, texto_sub, tam_sub, "medium")[1]) / 2,
                        texto_sub, fontsize=tam_sub, family=E.SANS, weight="medium", color="#444444", va="top")
        # chips con los días
        dias = sorted({_dia(plan, p.llegada) for p in plan.puntos})
        xc = 28 + pad_chip
        for d in dias:
            fecha = plan.salida.date() + timedelta(days=d)
            t = fmt_fecha(fecha)
            wt = _medir(fig, t, 15 * F, "bold")[0]
            ac.text(xc, 16 + pad_chip, t, fontsize=15 * F, family=E.SANS, weight="bold",
                    color="white", va="bottom", ha="left",
                    bbox=dict(boxstyle="square,pad=0.35", fc=E.color_dia(d), ec="black", lw=2))
            xc += wt + 30 * F
        ac.plot([0, W], [1, 1], color="#cccccc", lw=1)

        # ---- perfil
        _dibujar_perfil(fig, rect(pie_h + dias_h + 26 * F, perfil_h - 26 * F, marg_x, 0.985 - 2 * marg_x),
                        rect(pie_h + dias_h + perfil_h + 8, etq_h, marg_x, 0.985 - 2 * marg_x),
                        rect(pie_h, dias_h, marg_x, 0.985 - 2 * marg_x), plan, panel, puertos, cfg,
                        etiquetas, tam_etq)

        # ---- pie
        fig.text(0.01, 6 / H, atrib, fontsize=9.5 * F, family=E.SANS, color="#666666", va="bottom")
        # leyenda: solo los tipos de parada que lleva esta ruta, en el orden de la lista (a la derecha);
        # la de pendientes del track, a la izquierda de su fila
        def tipos_en(y, texto):
            fig.text(0.99, y, texto, family=[E.SANS, "Noto Emoji"], fontsize=11 * F, ha="right", va="bottom", color="#444444")
        if tipos_en_atrib:
            tipos_en(6 / H, lineas_ley[0])
        for r, (pend, texto) in enumerate(filas):
            y = (6 + (r + 1) * h_fila) / H
            if pend:
                _dibujar_pendiente(fig, F, W, H, y)
            if texto:
                tipos_en(y, texto)

        nombre = proyecto.salida_dir / f"infografia_{n_panel}"
        fig.savefig(f"{nombre}.png", dpi=100)
        fig.savefig(f"{nombre}.pdf", dpi=100)
        plt.close(fig)
        salidas += [f"{nombre}.png", f"{nombre}.pdf"]
    return salidas
