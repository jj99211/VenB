"""Tipografías, iconos y colores compartidos por las infografías y el mapa."""
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

FUENTES = Path(__file__).parent / "recursos" / "fuentes"
for _f in FUENTES.glob("*.ttf"):
    fm.fontManager.addfont(str(_f))

SANS = "Barlow Condensed"
MANO = "Amatic SC"
EMOJI = fm.FontProperties(fname=str(FUENTES / "NotoEmoji[wght].ttf"))

ICONOS = {
    "cafe": "☕",
    "desayuno": "☕",
    "comida": "\U0001F37D",
    "cena": "\U0001F37D",
    "dormir": "\U0001F6CF",
    "agua": "\U0001F6B0",
    "salida": "\U0001F6A9",
    "llegada": "\U0001F3C1",
    "cruce": "\U0001F500",
    "peligro": "\u26A0",
    "interes": "\u2B50",
    "poblacion": "\U0001F3D8",
    "panoramica": "\U0001F3DE",
    "puerto": "\u26F0",
    "otra": "\u2733",
    "meta": "\U0001F3C1",
    "bici": "\U0001F6B2",
}

# nombres de los tipos de parada para las leyendas, en el orden en que se muestran
NOMBRES_TIPO = {"salida": "salida", "cafe": "café", "desayuno": "desayuno", "comida": "comida", "cena": "cena",
                "dormir": "dormir", "agua": "agua", "cruce": "cruce", "peligro": "peligro",
                "interes": "punto de interés", "poblacion": "población", "panoramica": "panorámica", "puerto": "puerto", "llegada": "llegada", "otra": "otra"}

# servicios junto al track (mapas e infografías con mapa del IGN): icono y nombre para la leyenda
ICONOS_SERVICIO = {"agua": "\U0001F6B0", "bar": "\u2615", "tienda": "\U0001F6D2", "gasolinera": "\u26FD"}
NOMBRES_SERVICIO = {"agua": "fuente", "bar": "bar", "tienda": "tienda", "gasolinera": "gasolinera"}
# disco de color con el icono en blanco: se distinguen del resto del mapa y entre sí
COLORES_SERVICIO = {"agua": "#1565c0", "bar": "#a0522d", "tienda": "#2e7d32", "gasolinera": "#6a1b9a"}
LEYENDA_SERVICIOS = "Junto al track:"


def leyenda_servicios(servicios):
    """«Servicios: 🚰 fuente · ☕ bar…» con los tipos presentes, o cadena vacía."""
    tipos = {s["tipo"] for s in servicios or []}
    partes = [f"{ICONOS_SERVICIO[k]} {n}" for k, n in NOMBRES_SERVICIO.items() if k in tipos]
    return LEYENDA_SERVICIOS + " " + "  ".join(partes) if partes else ""


def servicio(ax, x, y, cx, cy, tipo, lado, F, z=10.6):
    """Icono de un servicio: disco del color del tipo con el icono en blanco, en (cx, cy), y una línea fina con un
    punto hasta su sitio real (x, y). lado: diámetro en píxeles."""
    col = COLORES_SERVICIO[tipo]
    if np.hypot(cx - x, cy - y) > lado * 0.55:
        ax.plot([x, cx], [y, cy], color="#1b1b1b", lw=1.3 * F ** 0.4, alpha=0.75, zorder=z, solid_capstyle="round")
        ax.add_patch(Circle((x, y), lado * 0.09, fc=col, ec="white", lw=0.8 * F ** 0.4, zorder=z + 0.05))
    ax.add_patch(Circle((cx, cy), lado * 0.5, fc=col, ec="#1b1b1b", lw=1.1 * F ** 0.4, zorder=z + 0.1))
    ax.add_patch(Circle((cx, cy), lado * 0.5 - 2.2 * F ** 0.4, fc="none", ec="white", lw=1.6 * F ** 0.4, zorder=z + 0.15))
    ax.text(cx, cy, ICONOS_SERVICIO[tipo], fontproperties=EMOJI, fontsize=lado / 1.25 * 0.72 / (100 / 72) * 0.8,
            ha="center", va="center", color="white", zorder=z + 0.2)


def texto_leyenda(fig, x, y, texto, tam, color, ha="right", fondo=None, **kw):
    """Escribe una línea de leyenda; lo que sigue a «Junto al track:» lleva cada icono de servicio en su color.
    x, y en coordenadas de la figura; ha: right (por defecto) o left; fondo: color de una caja detrás (para que
    no la crucen ríos ni rótulos del mapa)."""
    familia = [SANS, "Noto Emoji"]
    if LEYENDA_SERVICIOS not in texto:
        fig.text(x, y, texto, family=familia, fontsize=tam, ha=ha, va="bottom", color=color, **kw)
        return
    antes, despues = texto.split(LEYENDA_SERVICIOS, 1)
    iconos = {v: COLORES_SERVICIO[k] for k, v in ICONOS_SERVICIO.items()}
    trozos = [(antes + LEYENDA_SERVICIOS, color)]
    for ch in despues:
        c = iconos.get(ch, color)
        if trozos[-1][1] == c and ch not in iconos:
            trozos[-1] = (trozos[-1][0] + ch, c)
        else:
            trozos.append((ch, c))
    rend = fig.canvas.get_renderer()
    anchos = []
    for t, c in trozos:
        a = fig.text(0, 0, t, family=familia, fontsize=tam, **kw)
        anchos.append(a.get_window_extent(renderer=rend).width / fig.bbox.width)
        a.remove()
    x0 = x - sum(anchos) if ha == "right" else x
    if fondo:
        alto = tam * (100 / 72) * 1.35 / fig.bbox.height
        holgura = tam * 0.5 / fig.bbox.width
        fig.add_artist(Rectangle((x0 - holgura, y - alto * 0.12), sum(anchos) + 2 * holgura, alto, transform=fig.transFigure,
                                     fc=fondo, ec="none", alpha=0.9, zorder=2.5))
    for (t, c), a in zip(trozos, anchos):
        fig.text(x0, y, t, family=familia, fontsize=tam, ha="left", va="bottom", color=c, zorder=3, **kw)
        x0 += a


# un color por día de ruta (cajas, track y bandas del perfil)
COLORES_DIA = ["#d62728", "#2c5aa0", "#16855f", "#b0124f", "#c25a00", "#5b3b8c", "#00838f"]

# relleno del perfil por pendiente (límite superior del tramo en %, color)
COLORES_PENDIENTE = [(2, "#f3e48a"), (4, "#f2c14e"), (6, "#ee8f35"), (8, "#de4f2a"), (99, "#a51d1d")]


# perfiles de puertos: la misma escala, con más tonos en las rampas duras (desde el 8 %)
COLORES_PENDIENTE_PUERTO = [(2, "#f3e48a"), (4, "#f2c14e"), (6, "#ee8f35"), (8, "#de4f2a"), (10, "#a51d1d"),
                            (12, "#741313"), (15, "#4a0c0c"), (999, "#1e0505")]


def color_pendiente_puerto(pct):
    for lim, c in COLORES_PENDIENTE_PUERTO:
        if pct < lim:
            return c
    return COLORES_PENDIENTE_PUERTO[-1][1]


def color_dia(i):
    return COLORES_DIA[i % len(COLORES_DIA)]


def color_pendiente(pct):
    for lim, c in COLORES_PENDIENTE:
        if pct < lim:
            return c
    return COLORES_PENDIENTE[-1][1]


# ---------------------------------------------------------------- iconos en el perfil

SIN_ICONO_PERFIL = {"salida", "llegada", "meta"}     # en los extremos del perfil: no hace falta


def puntos_con_icono(plan):
    """[(km, icono, nombre)] de los puntos del plan cuyo tipo tiene icono, para marcarlos en el perfil."""
    return [(p.km, ICONOS[p.tipo_parada], p.nombre) for p in plan.puntos
            if p.tipo_parada in ICONOS and p.tipo_parada not in SIN_ICONO_PERFIL]


def paso_rejilla_km(total_km):
    """Separación de las líneas verticales del perfil: cada 10 km; en rutas largas, más espaciadas."""
    return 10 if total_km <= 300 else 50 if total_km <= 1000 else 100


def paso_rotulos_km(total_km, ancho_px, ancho_rotulo_px):
    """Paso de los km rotulados en el eje: el menor múltiplo de la rejilla en que los rótulos no se tocan."""
    g = paso_rejilla_km(total_km)
    return next((p for p in (g, 2 * g, 5 * g, 10 * g, 20 * g, 50 * g)
                 if ancho_px * p / max(total_km, 1e-9) >= ancho_rotulo_px * 1.6), 50 * g)


def rejilla_km(ax, total_km, zorder=2.5):
    """Líneas verticales del perfil en cada paso de la rejilla, sobre el relleno y bajo la línea."""
    g = paso_rejilla_km(total_km)
    for k in np.arange(g, total_km, g):
        ax.axvline(k, color="#000000", alpha=0.16, lw=0.8, zorder=zorder)


def km_texto(k):
    return f"km {k:.1f}".replace(".", ",") if k < 100 else f"km {k:.0f}"


def iconos_en_perfil(ax, puntos, km, ele, tam, ancho_ax_px, alto_ax_px, base, y_fila, borde="#333333", zorder=7,
                     perfil_min=0.3):
    """Iconos de los puntos en una fila sobre el perfil (eje `ax`, en km y metros, con el pie en `base`), a partir
    de la altura `y_fila`: cada uno en un disco blanco, con su km debajo y una línea vertical hasta el eje X.
    Si dos se tocan, el segundo sube una fila. Fija el alto del eje para que quepan y devuelve su tope (m).
    Si el eje es bajo, los iconos se reducen para dejar al perfil al menos `perfil_min` del alto."""
    if not puntos:
        return y_fila
    diam = tam * 1.9 * 100 / 72                        # disco, en píxeles (las figuras van a 100 ppp)
    alto_km = tam * 0.75 * 1.25 * 100 / 72             # rótulo del km bajo el disco
    fila_px = diam + alto_km + 8                       # alto de una fila
    ancho = max(diam, tam * 0.75 * 0.45 * 8 * 100 / 72) * 1.15 * (km[-1] - km[0]) / ancho_ax_px
    filas = []
    for k, icono, _ in sorted(puntos):
        n = 0
        while any(abs(k - kk) < ancho and nn == n for kk, nn, _ in filas):
            n += 1
        filas.append((k, n, icono))
    n_filas = max(n for _, n, _ in filas) + 1
    if n_filas * fila_px > alto_ax_px * (1 - perfil_min) - 4:    # no caben: iconos más pequeños
        f = (alto_ax_px * (1 - perfil_min) - 4) / (n_filas * fila_px)
        tam, diam, alto_km, fila_px = tam * f, diam * f, alto_km * f, fila_px * f
    # el alto del eje que deja n_filas de iconos por encima de y_fila: (tope - base) = (y_fila - base) + filas en m
    libre = max(alto_ax_px - n_filas * fila_px - 4, alto_ax_px * perfil_min)   # perfil_min: parte para el perfil
    tope = base + (y_fila - base) * alto_ax_px / libre
    px_m = alto_ax_px / (tope - base)
    ax.set_ylim(base, tope)
    for k, n, icono in filas:
        y_km = y_fila + (n * fila_px + 2) / px_m                     # base del rótulo del km
        y = y_km + (alto_km + 3 + diam / 2) / px_m                 # centro del disco
        ax.plot([k, k], [base, y_km], color=borde, lw=0.9, ls=(0, (3, 2)), zorder=zorder - 1)
        ax.text(k, y_km, km_texto(k), fontsize=tam * 0.75, family=SANS, ha="center", va="bottom", color=borde,
                zorder=zorder, bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.85))
        ax.text(k, y, icono, fontproperties=EMOJI, fontsize=tam, ha="center", va="center", color="#222222",
                zorder=zorder, bbox=dict(boxstyle="circle,pad=0.28", fc="white", ec=borde, lw=1.2))
    return tope
