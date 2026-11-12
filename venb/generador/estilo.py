"""Tipografías, iconos y colores compartidos por las infografías y el mapa."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager as fm  # noqa: E402

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
    "otra": "\u2733",
    "meta": "\U0001F3C1",
    "bici": "\U0001F6B2",
}

# nombres de los tipos de parada para las leyendas, en el orden en que se muestran
NOMBRES_TIPO = {"salida": "salida", "cafe": "café", "desayuno": "desayuno", "comida": "comida", "cena": "cena",
                "dormir": "dormir", "agua": "agua", "cruce": "cruce", "peligro": "peligro",
                "interes": "punto de interés", "llegada": "llegada", "otra": "otra"}

# un color por día de ruta (cajas, track y bandas del perfil)
COLORES_DIA = ["#d62728", "#2c5aa0", "#16855f", "#b0124f", "#c25a00", "#5b3b8c", "#00838f"]

# relleno del perfil por pendiente (límite superior del tramo en %, color)
COLORES_PENDIENTE = [(2, "#f3e48a"), (4, "#f2c14e"), (6, "#ee8f35"), (8, "#de4f2a"), (99, "#a51d1d")]


def color_dia(i):
    return COLORES_DIA[i % len(COLORES_DIA)]


def color_pendiente(pct):
    for lim, c in COLORES_PENDIENTE:
        if pct < lim:
            return c
    return COLORES_PENDIENTE[-1][1]
