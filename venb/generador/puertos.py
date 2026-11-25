"""Puertos de montaña en un track: detección de las subidas, Coeficiente de Dificultad y categoría.

Coeficiente de Dificultad de altimetrias.net (Juanto Uribarri, «La obtención del Coeficiente de Dificultad»,
https://www.altimetrias.net): a cada kilómetro de la subida se le aplica el coeficiente de su
pendiente media y el del puerto es la suma. La tabla va de 0 % → 1 a 30 % → 382: hasta el 4 % sube de uno en uno
y desde el 5 % cada punto suma uno más que el anterior (5 → 7, 6 → 10, 7 → 14…); los decimales se interpolan (así
está su tabla completa). El llano y las bajadas cuentan 1. La variante con asterisco (*) aplica la tabla cada 100 m,
lo que pesa más las rampas: cada tramo cuenta en proporción a su longitud (un tramo de 100 m, una décima).

Categorías por coeficiente (escala que eligió José): 4.ª de 15 a 29, 3.ª de 30 a 59, 2.ª de 60 a 119, 1.ª de 120
a 240 y Especial por encima de 240. Por debajo de 15 no se considera puerto.
"""
import math

import numpy as np

FUENTE = "Coeficiente de Dificultad: altimetrias.net (Juanto Uribarri), https://www.altimetrias.net"
FUENTE_CORTA = "Coeficiente de Dificultad: altimetrias.net"
CATEGORIAS = [(241, "Especial", "E"), (120, "1.ª categoría", "1"), (60, "2.ª categoría", "2"),
              (30, "3.ª categoría", "3"), (15, "4.ª categoría", "4")]
COEF_MINIMO = 15


def coef_pendiente(p):
    """Coeficiente de un kilómetro con pendiente media `p` (%): tabla de altimetrias.net. Vale para arrays."""
    p = np.maximum(np.asarray(p, dtype=float), 0.0)

    def entero(n):     # n entero ≥ 0: n + 1 hasta el 4 %; desde ahí, 4 + (n − 3)(n − 2) / 2 (5 → 7, 10 → 32, 30 → 382)
        return np.where(n <= 4, n + 1, 4 + (n - 3) * (n - 2) / 2)

    n = np.floor(p)
    return entero(n) + (p - n) * (entero(n + 1) - entero(n))


def categoria(coef):
    """(nombre, abreviatura) de la categoría o (None, None) si no llega a puerto. Con el coeficiente redondeado."""
    c = round(coef)
    for minimo, nombre, abrev in CATEGORIAS:
        if c >= minimo:
            return nombre, abrev
    return None, None


def _alt(km, ele, k):
    return float(np.interp(k, km, ele))


def tramos(km, ele, km0, km1, paso=1.0):
    """Tramos de `paso` km desde el pie (el último puede ser más corto): [(km_ini, km_fin, alt_ini, alt_fin, %)]
    con los km relativos al pie."""
    salida = []
    a = km0
    while a < km1 - 1e-6:
        b = min(a + paso, km1)
        if b - a < paso * 0.05 and salida:      # resto mínimo: se suma al último tramo
            k0, _, e0, _, _ = salida.pop()
            a = k0 + km0
        ea, eb = _alt(km, ele, a), _alt(km, ele, b)
        salida.append((a - km0, b - km0, ea, eb, (eb - ea) / ((b - a) * 1000) * 100))
        a = b
    return salida


def pendiente_maxima(km, ele, km0, km1, largo):
    """Pendiente media (%) del peor tramo seguido de `largo` km en cualquier punto de la subida (ventana que se
    desplaza cada 10 m), para que no dependa de dónde se pone el pie. Si la subida es más corta, la de toda ella."""
    largo = min(largo, km1 - km0)
    if largo <= 0:
        return 0.0
    x = np.append(np.arange(km0, km1 - largo, 0.01), km1 - largo)
    return float(np.max((np.interp(x + largo, km, ele) - np.interp(x, km, ele)) / (largo * 1000) * 100))


def coeficiente(km, ele, km0, km1, paso=1.0):
    """Suma de los coeficientes de los tramos de `paso` km, cada uno en proporción a su longitud."""
    return float(sum(coef_pendiente(p) * (b - a) for a, b, _, _, p in tramos(km, ele, km0, km1, paso)))


def datos_puerto(km, ele, km0, km1):
    """Cifras de la subida entre km0 (pie) y km1 (cima), en km del track."""
    km0, km1 = float(km0), float(km1)
    largo = km1 - km0
    e0, e1 = _alt(km, ele, km0), _alt(km, ele, km1)
    sel = (km >= km0) & (km <= km1)
    e = ele[sel]
    sube = float(np.clip(np.diff(e), 0, None).sum()) if len(e) > 1 else max(e1 - e0, 0)
    por_km = tramos(km, ele, km0, km1, 1.0)
    por_100 = tramos(km, ele, km0, km1, 0.1)
    coef = coeficiente(km, ele, km0, km1, 1.0)
    coef_100 = coeficiente(km, ele, km0, km1, 0.1)
    cat, abrev = categoria(coef)
    return {"km0": round(km0, 3), "km1": round(km1, 3), "longitud": round(largo, 2),
            "alt_pie": round(e0), "alt_cima": round(e1), "desnivel": round(e1 - e0), "ascenso": round(sube),
            "pendiente_media": round((e1 - e0) / max(largo * 1000, 1) * 100, 2),
            "pendiente_max_km": round(pendiente_maxima(km, ele, km0, km1, 1.0), 1),
            "pendiente_max_100": round(pendiente_maxima(km, ele, km0, km1, 0.1), 1),
            "coef": round(coef), "coef_100": round(coef_100), "categoria": cat, "cat": abrev,
            "por_km": [{"km0": round(a, 3), "km1": round(b, 3), "alt0": round(ea), "alt1": round(eb),
                        "pendiente": round(p, 1), "coef": round(float(coef_pendiente(p)) * (b - a), 1)}
                       for a, b, ea, eb, p in por_km]}


def _giros(ele, umbral):
    """Índices de los valles y cimas (alternos) que se separan más de `umbral` metros: [(i, +1 cima | −1 valle)]."""
    giros, ext, sentido = [], 0, 0
    for i in range(1, len(ele)):
        if sentido == 0:
            if abs(ele[i] - ele[ext]) >= umbral:
                sentido = 1 if ele[i] > ele[ext] else -1
                giros.append((ext, -sentido))
                ext = i
            elif ele[i] < ele[ext]:    # mientras no hay tendencia, el valle inicial es el punto más bajo
                ext = i
            continue
        if (ele[i] - ele[ext]) * sentido > 0:
            ext = i
        elif (ele[ext] - ele[i]) * sentido >= umbral:
            giros.append((ext, sentido))
            sentido, ext = -sentido, i
    if sentido:
        giros.append((ext, sentido))
    return giros


def _cima(km, ele, s, tolerancia_m=25.0, fraccion=0.12, hueco_km=3.0):
    """Desde el pie `s`, la cima: el punto más alto al que se llega sin bajar más de max(tolerancia_m, fraccion del
    desnivel subido) ni pasar más de `hueco_km` sin superar la altitud máxima (descansillos y contrapendientes cortas
    son parte del puerto; una bajada o un llano largos lo terminan)."""
    t = s
    j = s + 1
    n = len(ele)
    while j < n:
        if ele[j] > ele[t]:
            t = j
        else:
            caida = ele[t] - ele[j]
            if caida > max(tolerancia_m, fraccion * (ele[t] - ele[s])) or km[j] - km[t] > hueco_km:
                break
        j += 1
    return t


def _pie(km, ele, s, t, pendiente_min=2.5, ventana_km=0.5):
    """Adelanta el pie mientras el tramo siguiente (ventana_km) no llegue a `pendiente_min`: sin aproximación llana."""
    paso = max(1, int(round(0.1 / max(km[1] - km[0], 1e-6))))
    while s < t:
        k = km[s] + ventana_km
        if k >= km[t]:
            break
        if (_alt(km, ele, k) - ele[s]) / (ventana_km * 1000) * 100 >= pendiente_min:
            break
        s += paso
    return min(s, t)


def detectar(km, ele, coef_min=COEF_MINIMO):
    """Subidas del track candidatas a puerto, en orden de km: lista de datos_puerto (con el coeficiente ≥ coef_min).
    km y ele: el perfil remuestreado y limpio del motor (Track.km, Track.ele)."""
    km, ele = np.asarray(km, float), np.asarray(ele, float)
    if len(km) < 3:
        return []
    candidatos = []
    for i, tipo in _giros(ele, 10.0):
        if tipo != -1:
            continue
        t = _cima(km, ele, i)
        if t <= i:
            continue
        s = _pie(km, ele, i, t)
        if km[t] - km[s] < 0.3:
            continue
        coef = coeficiente(km, ele, km[s], km[t])
        if round(coef) >= coef_min:
            candidatos.append((coef, s, t))
    elegidos = []
    for coef, s, t in sorted(candidatos, reverse=True):    # los más duros primero; fuera los que se solapan
        if all(t <= s2 or s >= t2 for _, s2, t2 in elegidos):
            elegidos.append((coef, s, t))
    return [datos_puerto(km, ele, km[s], km[t]) for _, s, t in sorted(elegidos, key=lambda x: x[1])]


def km_en_track(lat, lon, tlat, tlon, tkm, km0=None, km1=None):
    """(km del track más cercano a un punto, distancia en m), solo entre km0 y km1 si se dan."""
    sel = np.ones(len(tkm), bool)
    if km0 is not None:
        sel &= (tkm >= km0) & (tkm <= km1)
    idx = np.flatnonzero(sel)
    if not len(idx):
        return None, math.inf
    k = math.cos(math.radians(lat))
    d = np.hypot((tlat[idx] - lat) * 111195, (tlon[idx] - lon) * 111195 * k)
    j = int(np.argmin(d))
    return float(tkm[idx[j]]), float(d[j])
