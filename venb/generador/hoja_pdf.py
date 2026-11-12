"""Lectura de hojas de ruta en PDF (formato habitual de los brevets BRM).

Busca la tabla por los títulos de sus columnas (LOCALIDADES, KM TOTAL, ABIERTO,
CERRADO…), no por su posición, y saca de la cabecera la fecha, la hora de salida,
la distancia y el desnivel oficiales.
"""
import re
from datetime import datetime, timedelta

from .datos import Punto, _norm

MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], 1)}
CONECTORES = {"de", "del", "la", "las", "los", "el", "y", "e", "a", "con", "en"}
# "(C.6)"; el paréntesis de cierre puede caer en la celda vecina: "(C.6"
RE_CONTROL = re.compile(r"\(\s*C\.?\s*([0-9]+|[A-Z])\b\s*\)?", re.I)
# "07:00" o, en el último control de algunas hojas, con la fecha delante: "12/04/26 03:00"
RE_HORA = re.compile(r"^\s*(?:\d{1,2}/\d{1,2}/\d{2,4}\s+)?(\d{1,2})[:.h](\d{2})\s*$")
MESES_CORTOS = {"ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "avr": 4, "may": 5, "mai": 5, "jun": 6, "jui": 7,
                "jul": 7, "ago": 8, "aug": 8, "aou": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12}


def _titulo(texto):
    """'EL CASAR DE TALAMANCA' -> 'El Casar de Talamanca'."""
    palabras = texto.lower().split()
    return " ".join(p.upper() if any(ch.isdigit() for ch in p)          # carreteras: CM-1001
                    or (len(p) <= 3 and not set(p) & set("aeiouáéíóú"))   # siglas: CC
                    else p if (i and p in CONECTORES) else p[:1].upper() + p[1:]
                    for i, p in enumerate(palabras))


def limpiar_nombre(texto):
    """Quita la marca de control y las indicaciones: 'CONGOSTRINA. Giro derecha…' -> 'Congostrina'."""
    t = RE_CONTROL.sub("", texto or "").replace("\n", " ")
    t = re.split(r"\.\s*(?=\S)", t, maxsplit=1)[0]
    return _titulo(re.sub(r"\s+", " ", t).strip(" .-"))


def _num(v):
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if "," in str(v) else float(v)
    except (TypeError, ValueError):
        return None


def _hora(v):
    m = RE_HORA.match(str(v or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _anio(a):
    a = int(a)
    return a + 2000 if a < 100 else a


def _fecha(t, etiqueta=r"(?:FECHA|DATE)"):
    """Fecha tras la etiqueta, en los formatos vistos en hojas de brevets: «11 de Abril de 2026», «26/09/2026»,
    «14-nov-26» (impreso del ACP en inglés) o «sábado, abril 19, 2025» (en francés, exportado de una hoja de cálculo)."""
    pre = etiqueta + r"\s*:?\s*(?:[a-záéíóúñ]+,?\s+)??"
    m = re.search(pre + r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de\s+)?(\d{4})", t, re.I)
    if m and m.group(2).lower() in MESES:
        return datetime(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))
    m = re.search(pre + r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", t, re.I)
    if m:
        return datetime(_anio(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(pre + r"(\d{1,2})[-\s/.]([a-záéíóúû]{3,10})\.?[-\s/.](\d{2,4})\b", t, re.I)
    if m and _norm(m.group(2))[:3] in MESES_CORTOS:
        return datetime(_anio(m.group(3)), MESES_CORTOS[_norm(m.group(2))[:3]], int(m.group(1)))
    m = re.search(pre + r"([a-záéíóú]+)\s+(\d{1,2}),?\s+(\d{4})", t, re.I)
    if m and _norm(m.group(1))[:3] in MESES_CORTOS:
        return datetime(int(m.group(3)), MESES_CORTOS[_norm(m.group(1))[:3]], int(m.group(2)))
    return None


def _metadatos(texto):
    meta = {}
    t = texto.replace("\n", " ")
    f = _fecha(t)
    if f:
        meta["fecha"] = f
    m = re.search(r"(?:HORA\s+(?:DE\s+)?SALIDA|STARTING\s+HOUR|HEURE\s+DE(?:\s+D[ÉE]PART)?)\s*:?\s*(\d{1,2})[:.h](\d{2})", t, re.I)
    if m:
        meta["hora"] = (int(m.group(1)), int(m.group(2)))
    m = (re.search(r"BREVET\s+DE\s+(\d{3,4})\s*KM", t, re.I) or re.search(r"DISTANCE\s*:?\s*(\d{3,4})\s*KM", t, re.I)
         or re.search(r"BREVET\s+(\d{3,4})\s*KM", t, re.I))
    if m:
        meta["distancia"] = int(m.group(1))
    m = re.search(r"\+\s*([\d.]+)\s*m\b", t)
    if m:
        meta["desnivel"] = int(m.group(1).replace(".", ""))
    m = (re.search(r"CLUB\s+ORGANIZADOR\s*:?\s*(.+?)\s+FECHA", t, re.I) or re.search(r"ORGANIZING\s+CLUB\s+NAME\s*:\s*(.+?)\s+ORG\.", t, re.I)
         or re.search(r"SOCI[ÉE]T[ÉE]\s+ORGANISATRICE\s*:\s*(.+?)\s+\d", t, re.I))
    if m:
        meta["club"] = m.group(1).strip()
    m = re.search(r"LUGAR\s+DE\s+SALIDA\s*:?\s*(.+?)\s+HORA", t, re.I)
    if m:
        meta["lugar_salida"] = m.group(1).strip()
    if "fecha" in meta and "hora" in meta:
        meta["salida"] = meta["fecha"].replace(hour=meta["hora"][0], minute=meta["hora"][1])
    return meta


NOMBRES_COL = ("localidad", "poblacion", "lugar", "ubicacion", "location", "localite")


def _columnas(filas):
    """Localiza la fila de títulos y el índice de cada columna (los títulos pueden ocupar dos filas)."""
    for i, fila in enumerate(filas):
        normas = [_norm(c) for c in fila]
        if not any(n.startswith(NOMBRES_COL) for n in normas):
            continue
        siguiente = [_norm(c) for c in filas[i + 1]] if i + 1 < len(filas) else []
        comb = [" ".join(x for x in (a, b) if x) for a, b in
                zip(normas, siguiente + [""] * (len(normas) - len(siguiente)))]

        def busca(*claves, excluye=()):
            for j, n in enumerate(comb):
                if any(c in n for c in claves) and not any(e in n for e in excluye):
                    return j
            return None

        cols = {
            "nombre": busca(*NOMBRES_COL),
            "km": busca("km total", "total", "km acum", "acumulad", "pk"),
            "abierto": busca("abierto", "apertura", "abre", "open", "ouverture"),
            "cerrado": busca("cerrad", "cierre", "cierra", "close", "fermeture"),  # «CERRAD0», con cero, en alguna hoja
        }
        if cols["km"] is None:
            cols["km"] = busca("km", excluye=("parcial",))
        datos = i + 2 if any(siguiente) and not _num(next((c for c in filas[i + 1] if c), None)) else i + 1
        return cols, datos
    raise ValueError("No encuentro la fila de títulos (LOCALIDADES, KM TOTAL…)")


def leer_pdf(ruta):
    """Lee la hoja en PDF: primero como tabla por columnas; si no encaja, como lista de líneas."""
    import pdfplumber
    filas, texto = [], ""
    with pdfplumber.open(ruta) as pdf:
        for pagina in pdf.pages:
            texto += (pagina.extract_text() or "") + "\n"
            for tabla in pagina.extract_tables():
                filas += [[(c or "").strip() for c in fila] for fila in tabla]
    if not texto.strip():
        raise ValueError(f"{ruta.name}: el PDF no tiene texto (¿es una imagen escaneada?)")
    return leer_documento(filas, texto, ruta.name)


def leer_documento(filas, texto, nombre):
    """Hoja de organizador ya extraída (PDF, ODT…): tabla por columnas o, si no encaja, lista de líneas."""
    if filas:
        try:
            puntos, meta = leer_tabla(filas, texto, nombre)
            if len(puntos) >= 3 and sum(1 for p in puntos if p.control) >= 2:
                return puntos, meta
        except ValueError:
            pass
    return leer_lineas(texto, nombre)


def leer_tabla(filas, texto, ruta):
    meta = _metadatos(texto)
    cols, inicio = _columnas(filas)
    salida = meta.get("salida")

    puntos = []
    ultima = {"apertura": salida, "cierre": salida}
    for fila in filas[inicio:]:
        def celda(clave):
            j = cols.get(clave)
            return fila[j] if j is not None and j < len(fila) else ""
        km = _num(celda("km"))
        bruto = celda("nombre")
        if km is None or not bruto:
            continue
        m = RE_CONTROL.search(bruto)
        abre, cierra = _hora(celda("abierto")), _hora(celda("cerrado"))
        control = f"C{m.group(1).upper()}" if m else ""
        p = Punto(limpiar_nombre(bruto), km, control)
        p.extra["nombre_hoja"] = bruto.replace("\n", " ")
        # horas sin fecha: se encadenan a partir de la salida (cambio de día si la hora retrocede)
        for clave, hm in (("apertura", abre), ("cierre", cierra)):
            if hm and salida:
                t = ultima[clave].replace(hour=hm[0], minute=hm[1])
                if t < ultima[clave]:
                    t += timedelta(days=1)
                ultima[clave] = t
                setattr(p, f"{clave}_hoja", t)
        puntos.append(p)
    if not puntos:
        raise ValueError(f"{ruta}: no se han podido leer puntos de la tabla")
    # sin marca "(C.n)": las filas con horas de control son controles
    if not any(p.control for p in puntos):
        n = 0
        for p in puntos:
            if p.cierre_hoja:
                n += 1
                p.control = f"C{n}"
    if salida and puntos[-1].cierre_hoja:
        meta["limite_horas"] = round((puntos[-1].cierre_hoja - salida).total_seconds() / 3600, 2)
    return puntos, meta


# ------------------------------------------------------------------ hojas por líneas
# Formato tipo "km  LOCALIDAD O PUNTO DE PASO  abierto cerrado  CONTINÚA POR  km parcial",
# p. ej. "109,5 C01 - CABALLAR 22:14 2:20 SG-V-2362 3,1" (CC Chamartín).

RE_LINEA = re.compile(r"^\s*(\d{1,4}[.,]\d)\s+(.*)$")
RE_KM = re.compile(r"^(\d{1,4}[.,]\d)\s+(.*)$")  # segunda columna de km (parcial y total, como en Galapagar 2026)
# «C1 - CABALLAR», «CF - …»; no «CL-505» (carretera): una letra sola necesita espacio antes del guion
RE_CONTROL_LINEA = re.compile(r"\bC\s*0*(\d+|[A-Z](?=\s))\s*[-–]\s*", re.I)
RE_CARRETERA = re.compile(r"^[A-Z]{1,3}-?\s?\d[\w-]*(\s*/\s*[A-Z]{1,3}-?\s?\d[\w-]*)*$")
RE_DOS_HORAS = re.compile(r"\b(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})\b")
RE_PUERTO = re.compile(r"^(pto\.?|puerto|alto|collado|collada|port)\b", re.I)
PALABRAS_INDICACION = {"STOP", "X", "ROT", "STOP!"}


def _mayusculas_iniciales(texto):
    """Primer tramo en mayúsculas: 'MELGAR DE FERNAMENTAL, STOP zda…' -> 'MELGAR DE FERNAMENTAL'."""
    palabras = []
    for w in re.split(r"\s+", texto.strip()):
        limpia = w.strip(",.;:!")
        if not limpia:
            break
        if limpia.upper() in PALABRAS_INDICACION and not palabras:
            return ""
        es_mayus = limpia.isupper() and any(c.isalpha() for c in limpia)
        if not es_mayus or "/" in limpia or re.match(r"^[A-Z]{1,3}-[A-Z0-9-]+$", limpia):  # C/, CL-603
            break
        if limpia.upper() in PALABRAS_INDICACION:
            break
        palabras.append(limpia)
        if w.endswith((",", ".")):
            break
    return " ".join(palabras)


def _nombre_linea(resto):
    """Nombre del punto y si es una localidad (para los mapas) a partir del texto de la línea."""
    resto = RE_DOS_HORAS.sub(" ", resto)
    m = RE_CONTROL_LINEA.match(resto)
    if m:
        resto = resto[m.end():]
    nombre = _mayusculas_iniciales(resto)
    if len(nombre.replace(" ", "")) >= 3:
        return _titulo(nombre), True
    if RE_PUERTO.match(resto):                         # puertos y altos: útiles en los mapas
        n = re.split(r"\(|\d{3,4}\s*m\b", resto)[0].strip(" ,.")
        return n, False
    # indicación de ruta: se conserva corta y no se rotula
    n = re.split(r"\s[A-Z]{1,3}-[A-Z0-9]", resto)[0]
    return n.strip(" ,.")[:40], False


def leer_lineas(texto, ruta):
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    meta = _metadatos_lineas(texto)
    if "salida" not in meta and "fecha" in meta:
        # sin hora de salida en la cabecera: la apertura del control del km 0
        for l in lineas:
            m = RE_LINEA.match(l)
            if m and float(m.group(1).replace(",", ".")) == 0:
                h = RE_DOS_HORAS.search(m.group(2))
                if h:
                    hh, mm = map(int, h.group(1).split(":"))
                    meta["salida"] = meta["fecha"].replace(hour=hh, minute=mm)
                break
    salida = meta.get("salida")

    puntos, pendiente = [], ""
    ultima = {"apertura": salida, "cierre": salida}
    for l in lineas:
        m = RE_LINEA.match(l)
        if not m:
            # el nombre de un control puede ir en la línea anterior a su km (último control)
            if RE_CONTROL_LINEA.match(l):
                pendiente = l
            elif not RE_CARRETERA.match(l):     # una carretera suelta («CL-505») no corta el nombre
                pendiente = ""
            continue
        km = float(m.group(1).replace(",", "."))
        resto = m.group(2)
        m2 = RE_KM.match(resto)
        if m2 and float(m2.group(1).replace(",", ".")) >= km:   # «parcial total»: manda el total
            km, resto = float(m2.group(1).replace(",", ".")), m2.group(2)
        # el nombre de un control puede ir en la línea anterior: se une si esta no empieza por un nombre
        # o si trae las horas del control
        if pendiente and not RE_CONTROL_LINEA.match(resto) and (not re.match(r"^[A-Za-zÁÉÍÓÚÑ]", resto) or RE_DOS_HORAS.search(resto)):
            resto = pendiente + " " + resto
        pendiente = ""
        if puntos and km < puntos[-1].km_hoja:          # números sueltos del margen
            continue
        mc = RE_CONTROL_LINEA.match(RE_DOS_HORAS.sub(" ", resto).strip())
        nombre, localidad = _nombre_linea(resto)
        if not nombre:
            continue
        p = Punto(nombre, km, f"C{mc.group(1).upper()}" if mc else "")
        p.extra["nombre_hoja"] = resto
        p.extra["localidad"] = localidad or bool(mc)
        horas = RE_DOS_HORAS.search(resto)
        if horas and salida:
            for clave, hm in zip(("apertura", "cierre"), horas.groups()):
                hh, mm = map(int, hm.split(":"))
                t = ultima[clave].replace(hour=hh, minute=mm)
                if t < ultima[clave]:
                    t += timedelta(days=1)
                ultima[clave] = t
                setattr(p, f"{clave}_hoja", t)
        if puntos and abs(km - puntos[-1].km_hoja) < 1e-6 and not p.control:
            continue
        puntos.append(p)
    if len(puntos) < 3:
        raise ValueError(f"{ruta}: VenB no reconoce el formato de esta hoja de ruta")
    if salida and meta.get("limite_horas") is None and puntos[-1].cierre_hoja:
        meta["limite_horas"] = round((puntos[-1].cierre_hoja - salida).total_seconds() / 3600, 2)
    return puntos, meta


def _metadatos_lineas(texto):
    meta = {}
    t = texto.replace("\n", " ")
    anio = re.search(r"\b(20\d{2})\b", t)
    m = re.search(r"Salida[^:]*:\s*(\d{1,2})\s+de\s+([a-záéíóú]+)(?:\s+de\s+(\d{4}))?\s+a\s+las\s+"
                  r"(\d{1,2})[:.h](\d{2})", t, re.I)
    if m and m.group(2).lower() in MESES:
        a = int(m.group(3) or (anio.group(1) if anio else datetime.now().year))
        meta["salida"] = datetime(a, MESES[m.group(2).lower()], int(m.group(1)),
                                  int(m.group(4)), int(m.group(5)))
    else:
        # «Sábado 12/09/2026 / Salida 07:30» o solo la fecha («Sábado 14/03/2026»)
        f = _fecha(t, r"(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo|fecha)")
        if f:
            meta["fecha"] = f
            m = re.search(r"Salida\s*:?\s*(\d{1,2})[:.h](\d{2})\b", t, re.I)
            if m:
                meta["salida"] = f.replace(hour=int(m.group(1)), minute=int(m.group(2)))
    m = re.search(r"Tiempo\s+m[áa]x(?:imo|\.)?\s*:?\s*(\d{1,3})\s*h(?:oras?)?\s*(\d{1,2})?", t, re.I)
    if m:
        meta["limite_horas"] = int(m.group(1)) + int(m.group(2) or 0) / 60
    m = re.search(r"\bBRM\s*(\d{3,4})\b", t, re.I)
    if m:
        meta["distancia"] = int(m.group(1))
    return meta
