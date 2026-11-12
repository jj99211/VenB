"""Carga de la configuración de un proyecto (.toml) y exportación de la tabla de tiempos."""
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

from .datos import calcular, leer_gpx, leer_hoja, leer_waypoints, puntos_de_lista

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


class Proyecto:
    """Configuración de un proyecto: un fichero .toml o, desde VenB, un diccionario con la misma
    estructura (`cfg`) y la carpeta `base` donde están el GPX, la hoja y el logotipo."""

    def __init__(self, fichero=None, cfg=None, base=None):
        if cfg is None:
            self.fichero = Path(fichero).resolve()
            self.base = self.fichero.parent
            with open(self.fichero, "rb") as f:
                self.cfg = tomllib.load(f)
            nombre = self.fichero.stem
        else:
            self.cfg, self.base = cfg, Path(base).resolve()
            nombre = "ruta"
        c = self.cfg
        self.nombre = c.get("nombre", nombre)
        self.salida_dir = self.base / c.get("carpeta_salida", f"salida/{nombre}")
        self.salida_dir.mkdir(parents=True, exist_ok=True)

    def seccion(self, nombre):
        return self.cfg.get(nombre, {})

    def calcular(self):
        c = self.cfg
        alt = self.seccion("altitud")
        track = leer_gpx(self.base / c["gpx"], ventana_m=alt.get("suavizado_m", 150),
                         altitud=alt.get("fuente", "mdt"))
        if c.get("puntos") is not None:       # puntos ya leídos o editados (VenB): la hoja no se vuelve a leer
            puntos, self.meta = puntos_de_lista(c["puntos"]), dict(c.get("meta") or {})
        else:
            puntos, self.meta = leer_hoja(self.base / c["hoja"])
        paradas = dict(self.seccion("paradas"))
        defecto = paradas.pop("por_defecto_min", 0)
        # salida y límite: los del .toml; si no están, los de la hoja (PDF de brevet)
        salida = c.get("salida", self.meta.get("salida"))
        limite = c.get("limite_horas", self.meta.get("limite_horas"))
        if salida is None or limite is None:
            raise ValueError("Falta 'salida' o 'limite_horas' en el .toml (la hoja no los trae)")
        if not isinstance(salida, datetime):
            salida = datetime.fromisoformat(str(salida))
        self.plan = calcular(track, puntos, salida, limite, defecto, paradas,
                             self.seccion("tipos_parada"), c.get("destacados", []),
                             c.get("ajuste_km", "auto"), alt.get("umbral_m", 3.0), self.nombre,
                             leer_waypoints(self.base / c["gpx"]), self.seccion("velocidades"), c.get("regla"))
        self.plan.meta = self.meta
        return self.plan


def fmt_hora(t):
    return t.strftime("%H:%M")


def fmt_dur(td, signo=False):
    s = int(round(td.total_seconds() / 60))
    neg = s < 0
    s = abs(s)
    txt = f"{s // 60}:{s % 60:02d}"
    return ("-" if neg else "+" if signo else "") + txt


def fmt_fecha(t):
    return f"{t.day} / {MESES[t.month - 1].capitalize()} / {t.year}"


def exportar_excel(plan, ruta):
    import openpyxl
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja de ruta"
    cab = ["Control", "Ubicación", "km hoja", "km", "km parciales", "Altitud", "Asc. total",
           "Ascenso parc", "Descenso parc", "% medio", "% completo", "Veloc", "Parada (min)",
           "Tipo parada", "Llegada", "Salida", "Cierre", "Margen (h)", "Margen", "Apertura", "Aviso"]
    ws.append(cab)
    for p in plan.puntos:
        margen = p.margen
        ws.append([p.control, p.nombre, p.km_hoja, round(p.km, 1), round(p.km_tramo, 1),
                   round(p.alt), round(p.asc_total), round(p.asc_tramo), round(p.desc_tramo),
                   p.pendiente, p.fraccion, round(p.velocidad, 2) if p.velocidad else None,
                   p.parada_min or None, p.tipo_parada or None, p.llegada, p.salida, p.cierre,
                   round(margen.total_seconds() / 3600, 2), fmt_dur(margen, signo=True),
                   p.apertura_hoja,
                   "llega antes de la apertura" if p.antes_de_apertura else
                   ("fuera de cierre" if margen.total_seconds() < 0 else None)])
    n = ws.max_row
    for fila in ws.iter_rows(min_row=2):
        fila[9].number_format = "0.0%"
        fila[10].number_format = "0.0%"
        for c in fila[14:17] + (fila[19],):
            c.number_format = "dd/mm hh:mm"
        if fila[0].value:
            for c in fila:
                c.font = Font(bold=True)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2C5AA0")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    rojo = PatternFill("solid", fgColor="F4C7C3")
    verde = PatternFill("solid", fgColor="D9EAD3")
    ws.conditional_formatting.add(f"R2:S{n}", CellIsRule(operator="lessThan", formula=["0"], fill=rojo))
    ws.conditional_formatting.add(f"R2:R{n}", CellIsRule(operator="greaterThanOrEqual", formula=["0"],
                                                         fill=verde))
    anchos = [9, 24, 8, 8, 9, 8, 9, 9, 9, 8, 9, 7, 9, 11, 13, 13, 13, 9, 8, 13, 22]
    for i, a in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = a
    ws.freeze_panes = "C2"

    r = wb.create_sheet("Resumen")
    resumen = [("Ruta", plan.nombre), ("Distancia (km)", round(plan.total_km, 1)),
               ("Desnivel positivo (m)", round(plan.total_asc)),
               ("Salida", plan.salida), ("Tiempo límite (h)", plan.limite_h),
               ("Llegada prevista", plan.llegada_final),
               ("Tiempo total previsto", fmt_dur(plan.llegada_final - plan.salida)),
               ("Margen en meta", fmt_dur(plan.puntos[-1].margen, signo=True))]
    meta = getattr(plan, "meta", {}) or {}
    if meta.get("distancia"):
        resumen.append(("Distancia oficial (km)", meta["distancia"]))
    if meta.get("desnivel"):
        resumen.append(("Desnivel oficial (m)", meta["desnivel"]))
    for aviso in getattr(plan, "avisos", []):
        resumen.append(("Aviso", aviso))
    for fila in resumen:
        r.append(fila)
    for c in ("B4", "B6"):
        r[c].number_format = "dd/mm/yyyy hh:mm"
    r.column_dimensions["A"].width = 24
    r.column_dimensions["B"].width = 20
    wb.save(ruta)
