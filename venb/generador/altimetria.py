"""Perfil detallado de un puerto (bloques por kilómetro coloreados por pendiente) y ficha A4 del puerto: cabecera con
sus cifras y su categoría, mapa con el track y los waypoints, y el perfil. Ver puertos.py para el cálculo."""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import patheffects as pe  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

from . import estilo as E  # noqa: E402
from .puertos import FUENTE  # noqa: E402

TINTA = "#222222"
SUAVE = "#6b6b6b"
NOTA_100 = ("(*) Coeficiente aplicando la tabla cada 100 m, que pesa más las rampas. Máximas: el peor kilómetro (o los "
            "peores 100 m) seguido en cualquier punto, por eso pueden superar a la del km más duro del perfil.")


def num(v, dec=0):
    """Número a la española: 1.234 / 7,4."""
    t = f"{v:,.{dec}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return t


def _claro(color):
    r, g, b = matplotlib.colors.to_rgb(color)
    return 0.299 * r + 0.587 * g + 0.114 * b > 0.55


def cifras(p):
    """[(rótulo, valor)] del puerto para cabeceras y tablas."""
    return [("Longitud", f"{num(p['longitud'], 1)} km"), ("Desnivel", f"{num(p['desnivel'])} m"),
            ("Pendiente media", f"{num(p['pendiente_media'], 1)} %"),
            ("Máxima (1 km)", f"{num(p['pendiente_max_km'], 1)} %"), ("Máxima (100 m)", f"{num(p['pendiente_max_100'], 1)} %"),
            ("Altitud", f"{num(p['alt_cima'])} m"), ("Coeficiente", f"{p['coef']}  ({p['coef_100']}*)")]


def dibujar_perfil(ax, km, ele, puerto, puntos, F=1.0, ancho_px=2000, alto_px=900, tinta=TINTA, familia=None):
    """Dibuja el perfil en `ax` (km desde el pie y metros). puntos: [{'n', 'nombre', 'km' (desde el pie), 'alt'}]."""
    familia = familia or E.SANS
    km, ele = np.asarray(km, float), np.asarray(ele, float)
    largo = float(km[-1])
    rango = max(float(ele.max() - ele.min()), 30.0)
    base = float(np.floor((ele.min() - rango * 0.12) / 50) * 50)
    px_km = ancho_px / max(largo, 0.1)
    # bloques por km, del color de su pendiente
    for t in puerto["por_km"]:
        sel = (km >= t["km0"] - 1e-9) & (km <= t["km1"] + 1e-9)
        k = np.r_[t["km0"], km[sel], t["km1"]]
        e = np.interp(k, km, ele)
        col = E.color_pendiente_puerto(t["pendiente"])
        ax.fill_between(k, base, e, color=col, lw=0, zorder=1)
        ax.plot([t["km1"]] * 2, [base, e[-1]], color="white", lw=1.6 * F, zorder=2)
        # pendiente dentro del bloque; si no cabe tumbada, de pie
        ancho = (t["km1"] - t["km0"]) * px_km
        texto = f"{num(t['pendiente'], 1)} %"
        tam = 15 * F
        cabe = ancho > len(texto) * tam * 0.55 * 100 / 72 + 6
        if ancho < tam * 1.6:
            continue
        y = base + (min(e) - base) * 0.45
        ax.text((t["km0"] + t["km1"]) / 2, y, texto, rotation=0 if cabe else 90, ha="center", va="center",
                fontsize=tam, family=familia, weight="bold", color=tinta if _claro(col) else "white", zorder=4)
    ax.plot(km, ele, color=tinta, lw=2.4 * F, zorder=3, solid_capstyle="round")
    # altitud en cada km, encima de la línea (no junto a un waypoint, que ya lleva la suya)
    cerca = [pt["km"] for pt in puntos]
    for t in puerto["por_km"]:
        if t["km1"] < largo - 0.05 and all(abs(t["km1"] - c) > 0.15 for c in cerca):
            ax.annotate(f"{num(t['alt1'])}", (t["km1"], t["alt1"]), xytext=(0, 6 * F), textcoords="offset points",
                        rotation=90, ha="center", va="bottom", fontsize=11 * F, family=familia, color=SUAVE, zorder=4)
    # waypoints: disco numerado y rótulo de pie en una fila sobre el perfil, unidos a su sitio con una línea
    y_fila = float(ele.max()) + rango * 0.20
    sep = 30 * F / px_km                       # separación mínima entre rótulos (km)
    orden = sorted(puntos, key=lambda x: x["km"])
    xs = []
    for pt in orden:
        xs.append(max(pt["km"], xs[-1] + sep) if xs else pt["km"])
    tope_x = largo + sep * 0.5                  # si al empujar se salen por la derecha, se reparten hacia la izquierda
    for i in range(len(xs) - 1, -1, -1):
        xs[i] = min(xs[i], tope_x if i == len(xs) - 1 else xs[i + 1] - sep)
    tam_n, tam_r = 12 * F, 13 * F
    disco_pt = tam_n * 1.9
    largo_pt = max((len(f"{p['nombre']}  ·  {num(p['alt'])} m") for p in puntos), default=0) * tam_r * 0.36
    necesita_px = (disco_pt + 6 * F + largo_pt + 8) * 100 / 72
    if necesita_px > 0.45 * alto_px:            # rótulos más pequeños: el perfil ocupa al menos media gráfica
        f = max(0.55, 0.45 * alto_px / necesita_px)
        tam_n, tam_r, disco_pt, largo_pt = tam_n * f, tam_r * f, disco_pt * f, largo_pt * f
        necesita_px *= f
    tope = base + (y_fila - base) / max(1 - necesita_px / max(alto_px, 1), 0.35)
    for pt, x in zip(orden, xs):
        y_pt = float(np.interp(pt["km"], km, ele))
        ax.plot([pt["km"], pt["km"], x], [y_pt, y_fila - rango * 0.05, y_fila], color=tinta, lw=0.9 * F,
                ls=(0, (3, 2)), zorder=5)
        ax.plot([pt["km"]], [y_pt], "o", ms=7 * F, mfc="white", mec=tinta, mew=1.6 * F, zorder=6)
        if pt.get("n"):
            ax.annotate(str(pt["n"]), (x, y_fila), xytext=(0, disco_pt / 2), textcoords="offset points", ha="center",
                        va="center", fontsize=tam_n, family=familia, weight="bold", color="white", zorder=7,
                        bbox=dict(boxstyle="circle,pad=0.25", fc=tinta, ec="white", lw=1.2 * F))
        ax.annotate(f"{pt['nombre']}  ·  {num(pt['alt'])} m", (x, y_fila), xytext=(0, disco_pt + 6 * F),
                    textcoords="offset points", rotation=90, ha="center", va="bottom", fontsize=tam_r,
                    family=familia, color=tinta, zorder=7)
    ax.set_xlim(-largo * 0.01, largo + max(sep * 0.6, largo * 0.01))
    ax.set_ylim(base, tope if puntos else float(ele.max()) + rango * 0.15)
    # ejes: km cada 1 (o cada 2 o 5 si no caben) y altitudes a la izquierda
    paso = next(p for p in (1, 2, 5, 10, 20, 50) if p * px_km >= 40 * F)
    ax.set_xticks(np.arange(0, largo + 1e-6, paso))
    ax.set_xticklabels([f"{k:.0f}" for k in np.arange(0, largo + 1e-6, paso)], fontsize=12 * F, family=familia, color=tinta)
    ax.set_xlabel("km desde el pie", fontsize=12 * F, family=familia, color=tinta)
    ax.tick_params(axis="y", labelsize=11 * F, colors=SUAVE)
    for l in ax.get_yticklabels():
        l.set_family(familia)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{num(v)} m"))
    ax.set_yticks([v for v in ax.get_yticks() if base <= v <= float(ele.max()) + rango * 0.05])
    ax.grid(axis="y", color="#000000", alpha=0.10, lw=0.8 * F, zorder=0)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(SUAVE)


def leyenda_pendientes(fig, x, y, F, ancho_caja=0.035, familia=None):
    """Escala de colores de pendiente en una fila, desde (x, y) en fracciones de la figura."""
    familia = familia or E.SANS
    fig.text(x, y, "Pendiente:", fontsize=12 * F, family=familia, color=TINTA, ha="left", va="center")
    x += 0.075
    previo = 0
    for lim, col in E.COLORES_PENDIENTE_PUERTO:
        etiqueta = f"{previo}–{lim} %" if lim < 100 else f"{previo} % o más"
        fig.patches.append(FancyBboxPatch((x, y - 0.006), ancho_caja * 0.35, 0.012, boxstyle="square,pad=0",
                                          transform=fig.transFigure, fc=col, ec="#555555", lw=0.6, figure=fig))
        fig.text(x + ancho_caja * 0.42, y, etiqueta, fontsize=11 * F, family=familia, color=TINTA, ha="left", va="center")
        x += ancho_caja + 0.03
        previo = lim


def _cabecera(fig, puerto, nombre, subtitulo, F, y_top, alto, marca_logo=None, marca_texto=""):
    """Título, subtítulo, distintivo de categoría y cifras. y_top y alto en fracciones de la figura."""
    fam = E.SANS
    fig.text(0.04, y_top - alto * 0.05, nombre, fontsize=40 * F, family=fam, weight="bold", color=TINTA, va="top")
    if subtitulo:
        fig.text(0.04, y_top - alto * 0.40, subtitulo, fontsize=19 * F, family=fam, color=SUAVE, va="top")
    # distintivo de la categoría, a la derecha
    cat = puerto.get("cat")
    texto_cat = {"E": "ESPECIAL"}.get(cat, f"{cat}.ª" if cat else "—")
    caja = fig.text(0.955, y_top - alto * 0.06, texto_cat, fontsize=(30 if cat == "E" else 44) * F, family=fam, weight="bold",
             color="white", ha="right", va="top",
             bbox=dict(boxstyle="round,pad=0.35", fc="#a51d1d" if cat in ("E", "1") else "#2c5aa0" if cat else "#888888", ec="none"))
    fig.canvas.draw()
    bb = caja.get_bbox_patch().get_window_extent().transformed(fig.transFigure.inverted())
    fig.text((bb.x0 + bb.x1) / 2, bb.y0 - 0.004, "categoría" if cat else "sin categoría", fontsize=15 * F, family=fam, color=TINTA, ha="center", va="top")
    # cifras en una fila
    datos = cifras(puerto)
    ancho = 0.80 / len(datos)
    for i, (r, v) in enumerate(datos):
        x = 0.04 + i * ancho
        fig.text(x, y_top - alto * 0.70, r.upper(), fontsize=11 * F, family=fam, color=SUAVE, va="top")
        fig.text(x, y_top - alto * 0.80, v, fontsize=19 * F, family=fam, weight="semibold", color=TINTA, va="top")


def _pie(fig, F, y, marca_logo=None, marca_texto="", extra=""):
    fam = E.SANS
    fig.text(0.04, y + 0.012 * F, FUENTE, fontsize=10.5 * F, family=fam, color=SUAVE, va="bottom")
    fig.text(0.04, y, NOTA_100, fontsize=10.5 * F, family=fam, color=SUAVE, va="bottom")
    if extra:
        fig.text(0.04, y - 0.012 * F, extra, fontsize=10.5 * F, family=fam, color=SUAVE, va="bottom")
    if marca_texto:
        fig.text(0.96, y, marca_texto, fontsize=11 * F, family=fam, color=TINTA, ha="right", va="bottom")


def _logo(fig, logo, x1, y0, alto_frac, W, H):
    """Logotipo con su esquina inferior derecha en (x1, y0), de alto `alto_frac` de la figura."""
    if logo is None:
        return
    h, w = logo.shape[:2]
    alto_px = alto_frac * H
    ancho = alto_px * w / h / W
    ax = fig.add_axes([x1 - ancho, y0, ancho, alto_frac])
    ax.imshow(logo)
    ax.axis("off")


def perfil(puerto, km, ele, puntos, nombre, subtitulo, ruta_base, marca=None):
    """Perfil suelto (PNG y SVG, 16:9): cabecera, perfil y leyenda. Devuelve las rutas."""
    W, H, F = 2400, 1350, 1.5
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor("white")
    _cabecera(fig, puerto, nombre, subtitulo, F, 0.985, 0.20)
    ax = fig.add_axes([0.075, 0.13, 0.885, 0.62])
    dibujar_perfil(ax, km, ele, puerto, puntos, F, ancho_px=0.885 * W, alto_px=0.62 * H)
    leyenda_pendientes(fig, 0.04, 0.045, F * 0.9, ancho_caja=0.055)
    _pie(fig, F * 0.95, 0.008, marca_texto=(marca or {}).get("texto_pie", ""))
    rutas = [f"{ruta_base}.png", f"{ruta_base}.svg"]
    fig.savefig(rutas[0], dpi=100, facecolor="white")
    fig.savefig(rutas[1], facecolor="white")
    plt.close(fig)
    return rutas


def _mapa(ax, sub, puntos, estilo, W, H, F):
    """Mapa base con el track coloreado por pendiente y los waypoints numerados. W, H: tamaño del eje en px.
    Devuelve el texto de atribución del mapa base."""
    from .teselas import ESTILOS, a_mercator, cubre, mapa_base, zoom_para
    X, Y = a_mercator(sub["lon"], sub["lat"])
    cx, cy = (X.min() + X.max()) / 2, (Y.min() + Y.max()) / 2
    w, h = (X.max() - X.min()) * 1.30 + 400, (Y.max() - Y.min()) * 1.30 + 400
    if w / h < W / H:
        w = h * W / H
    else:
        h = w * H / W
    xmin, xmax, ymin, ymax = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    z = zoom_para(xmin, xmax, W / 1.7, estilo)
    if estilo.startswith("ign_") and not cubre(estilo, z, X, Y):
        print("  aviso: el mapa del IGN solo cubre España; se usa el topográfico de OpenStreetMap", file=sys.stderr)
        estilo = "topo"
    try:
        base = mapa_base(xmin, ymin, xmax, ymax, z, estilo)
        ax.imshow(base, extent=(xmin, xmax, ymin, ymax), interpolation="lanczos", zorder=0)
        atrib = ESTILOS[estilo][3]
    except Exception as ex:     # sin red: el track sobre fondo claro
        print(f"  aviso: sin mapa base ({ex})", file=sys.stderr)
        ax.set_facecolor("#f4f1ea")
        atrib = ""
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(SUAVE)
    # track: borde oscuro y tramos de 100 m del color de su pendiente
    ax.plot(X, Y, color="#1a1a1a", lw=11 * F, solid_capstyle="round", zorder=3, alpha=0.85)
    km, ele = np.asarray(sub["km"]), np.asarray(sub["ele"])
    cortes = np.arange(0, km[-1] + 0.1, 0.1)
    segs, cols = [], []
    for a, b in zip(cortes[:-1], np.minimum(cortes[1:], km[-1])):
        sel = (km >= a) & (km <= b)
        if sel.sum() < 2:
            continue
        p = (np.interp(b, km, ele) - np.interp(a, km, ele)) / max((b - a) * 1000, 1) * 100
        segs.append(np.c_[X[sel], Y[sel]])
        cols.append(E.color_pendiente_puerto(p))
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=7 * F, capstyle="round", zorder=4))
    # waypoints: disco numerado y nombre con halo, en el lado que menos tape el track y los demás rótulos
    m_px = (xmax - xmin) / W
    usados = []
    halo = [pe.withStroke(linewidth=5 * F, foreground="white")]
    tx, ty = X[::max(1, len(X) // 400)], Y[::max(1, len(Y) // 400)]
    for pt in puntos:
        px_, py_ = np.interp(pt["km"], km, X), np.interp(pt["km"], km, Y)
        ax.text(px_, py_, str(pt["n"]), ha="center", va="center", fontsize=13 * F, family=E.SANS, weight="bold",
                color="white", zorder=8, bbox=dict(boxstyle="circle,pad=0.3", fc=TINTA, ec="white", lw=1.5 * F))
        texto = pt["nombre"]
        ancho = len(texto) * 15 * F * 0.48 * 100 / 72 * m_px
        alto = 15 * F * 1.3 * 100 / 72 * m_px
        mejor = None
        for dx, dy, ha, va in ((1, 0, "left", "center"), (-1, 0, "right", "center"), (0, 1, "center", "bottom"),
                               (0, -1, "center", "top"), (1, 1, "left", "bottom"), (-1, 1, "right", "bottom"),
                               (1, -1, "left", "top"), (-1, -1, "right", "top")):
            ox, oy = px_ + dx * 28 * F * m_px, py_ + dy * 28 * F * m_px
            x0 = ox if ha == "left" else ox - ancho if ha == "right" else ox - ancho / 2
            y0 = oy if va == "bottom" else oy - alto if va == "top" else oy - alto / 2
            caja = (x0, y0, x0 + ancho, y0 + alto)
            tapa = ((tx > caja[0]) & (tx < caja[2]) & (ty > caja[1]) & (ty < caja[3])).sum()
            choca = sum(not (caja[2] < u[0] or caja[0] > u[2] or caja[3] < u[1] or caja[1] > u[3]) for u in usados)
            fuera = caja[0] < xmin or caja[2] > xmax or caja[1] < ymin or caja[3] > ymax
            coste = tapa + 50 * choca + 100 * fuera
            if mejor is None or coste < mejor[0]:
                mejor = (coste, ox, oy, ha, va, caja)
        _, ox, oy, ha, va, caja = mejor
        usados.append(caja)
        ax.text(ox, oy, texto, ha=ha, va=va, fontsize=15 * F, family=E.SANS, weight="semibold", color=TINTA,
                zorder=7, path_effects=halo)
    # escala gráfica abajo a la izquierda (en Mercator, corregida por la latitud)
    lat0 = float(np.mean(sub["lat"]))
    m_reales = (xmax - xmin) * np.cos(np.radians(lat0))
    paso = next(p for p in (100, 200, 500, 1000, 2000, 5000, 10000) if p > m_reales * 0.12)
    largo = paso / np.cos(np.radians(lat0))
    x0, y0 = xmin + (xmax - xmin) * 0.03, ymin + (ymax - ymin) * 0.035
    ax.plot([x0, x0 + largo], [y0, y0], color=TINTA, lw=4 * F, zorder=9, solid_capstyle="butt",
            path_effects=[pe.withStroke(linewidth=8 * F, foreground="white")])
    ax.text(x0 + largo / 2, y0 + (ymax - ymin) * 0.008, f"{paso // 1000} km" if paso >= 1000 else f"{paso} m",
            ha="center", va="bottom", fontsize=13 * F, family=E.SANS, color=TINTA, zorder=9, path_effects=halo)
    return atrib


def ficha(puerto, sub, puntos, nombre, subtitulo, ruta_base, estilo="ign_mtn", marca=None):
    """Ficha A4 vertical del puerto (PNG y PDF): cabecera, mapa y perfil. sub: {'lat', 'lon', 'km', 'ele'} del tramo,
    con los km desde el pie. Devuelve las rutas."""
    W, H, F = 2400, 3394, 1.6
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor("white")
    marca = marca or {}
    _cabecera(fig, puerto, nombre, subtitulo, F, 0.985, 0.105)
    # mapa
    ax_m = fig.add_axes([0.04, 0.445, 0.92, 0.415])
    atrib = _mapa(ax_m, sub, puntos, estilo, 0.92 * W, 0.415 * H, F)
    fig.text(0.96, 0.437, " · ".join(t for t in (atrib, "Puntos: © OpenStreetMap contributors") if t),
             fontsize=10 * F, family=E.SANS, color=SUAVE, ha="right", va="top")
    # perfil
    ax_p = fig.add_axes([0.085, 0.095, 0.875, 0.315])
    dibujar_perfil(ax_p, sub["km"], sub["ele"], puerto, puntos, F * 0.95, ancho_px=0.875 * W, alto_px=0.315 * H)
    leyenda_pendientes(fig, 0.04, 0.045, F * 0.85, ancho_caja=0.055)
    logo = None
    if marca.get("logo"):
        try:
            from .ilustrado import cargar_logo
            logo = cargar_logo(marca["logo"])
        except Exception:
            logo = None
    _logo(fig, logo, 0.96, 0.006, 0.026, W, H)
    _pie(fig, F * 0.85, 0.008, marca_texto="" if logo is not None else marca.get("texto_pie", ""))
    rutas = [f"{ruta_base}.png", f"{ruta_base}.pdf"]
    fig.savefig(rutas[0], dpi=100, facecolor="white")
    fig.savefig(rutas[1], dpi=100, facecolor="white")
    plt.close(fig)
    return rutas
