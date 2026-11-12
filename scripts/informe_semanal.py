"""Informe semanal en PDF de media página (carga, volumen, descanso, lectura y plan).
Uso: python3 informe_semanal.py <domingo AAAA-MM-DD> <notas.json> <carpeta_salida>
notas.json: {"lectura": "...", "plan": ["...", "..."]}"""
import json, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from carga import cargar
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

import rutas  # noqa: E402
GARMIN_DB = rutas.ruta_garmin_db()


def es(x, d=1):
    return f'{x:.{d}f}'.replace('.', ',')


def semana(df, ini, fin):
    b = df[df.bici & (df.Fecha >= ini) & (df.Fecha <= fin + pd.Timedelta(days=1))]
    b = b[b.Fecha < fin + pd.Timedelta(days=1)]
    return b.h.sum(), b.Distancia.sum(), b.tss.sum(), len(b)


def descanso(ini, fin):
    """Medias de FC en reposo, VFC y sueño entre dos fechas (None si no hay datos)."""
    d = sqlite3.connect(f'file:{GARMIN_DB}?mode=ro', uri=True)
    rango = (ini.strftime('%Y-%m-%d'), (fin + pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
    def media(sql):
        return pd.read_sql(sql, d, params=rango).iloc[0, 0]
    sueno = pd.read_sql('select total_sleep, score from sleep where day>=? and day<?', d, params=rango)
    horas = pd.to_timedelta(sueno.total_sleep.str.slice(0, 8)).dt.total_seconds() / 3600
    horas = horas[horas > 0]
    return {'fc': media('select avg(resting_heart_rate) from resting_hr where day>=? and day<?'),
            'vfc': media('select avg(last_night_avg) from hrv where day>=? and day<?'),
            'h': horas.mean(), 'score': sueno.score.mean(), 'noches': len(horas)}


fin = pd.Timestamp(sys.argv[1])
notas = json.load(open(sys.argv[2], encoding='utf-8'))
salida = sys.argv[3]
os.makedirs(salida, exist_ok=True)
ini = fin - pd.Timedelta(days=6)
df, pmc, _ = cargar('garmin', fin)
h, km, tss, n = semana(df, ini, fin)
h0, km0, _, _ = semana(df, ini - pd.Timedelta(days=7), fin - pd.Timedelta(days=7))
h4 = sum(semana(df, ini - pd.Timedelta(days=7 * k), fin - pd.Timedelta(days=7 * k))[0] for k in range(4)) / 4
hoy, antes = pmc.loc[fin], pmc.loc[fin - pd.Timedelta(days=7)]
r = descanso(ini, fin)
r0 = descanso(ini - pd.Timedelta(days=28), ini - pd.Timedelta(days=1))

st = getSampleStyleSheet()
N = ParagraphStyle('n', parent=st['Normal'], fontName='Helvetica', fontSize=9.5, leading=13)
H = ParagraphStyle('h', parent=st['Heading2'], fontName='Helvetica-Bold', fontSize=11, spaceBefore=8, spaceAfter=3)
T = ParagraphStyle('t', parent=st['Title'], fontName='Helvetica-Bold', fontSize=14, alignment=0, spaceAfter=2)
S = ParagraphStyle('s', parent=N, fontSize=8.5, textColor=colors.HexColor('#52514e'))
filas = [['', 'Esta semana', 'Referencia'],
         ['Volumen de bici', f'{es(h)} h, {km:.0f} km, {n} salidas', f'Semana anterior: {es(h0)} h, {km0:.0f} km; media de 4 semanas: {es(h4)} h'],
         ['CTL / ATL / TSB', f'{hoy.CTL:.0f} / {hoy.ATL:.0f} / {hoy.TSB:+.0f}', f'Hace 7 días: {antes.CTL:.0f} / {antes.ATL:.0f} / {antes.TSB:+.0f}'],
         ['TSS semanal', f'{tss:.0f}', 'Exterior estimado por duración; rodillo real'],
         ['Sueño', f'{es(r["h"])} h/noche, puntuación {r["score"]:.0f} ({r["noches"]} noches)', f'4 semanas previas: {es(r0["h"])} h, puntuación {r0["score"]:.0f}'],
         ['FC reposo / VFC', f'{r["fc"]:.0f} ppm / {r["vfc"]:.0f} ms', f'4 semanas previas: {r0["fc"]:.0f} ppm / {r0["vfc"]:.0f} ms']]
C = ParagraphStyle('c', parent=N, fontSize=8.5, leading=10.5)
filas = [filas[0]] + [[Paragraph(str(c), C) for c in f] for f in filas[1:]]
t = Table(filas, colWidths=[3 * cm, 5.8 * cm, 8.4 * cm])
t.setStyle(TableStyle([('FONT', (0, 0), (-1, -1), 'Helvetica', 8.5), ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8.5),
                       ('LINEBELOW', (0, 0), (-1, 0), .6, colors.black), ('LINEBELOW', (0, -1), (-1, -1), .4, colors.grey),
                       ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
MES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
fecha = lambda x: f'{x.day:02d}/{x.month:02d}/{x.year}'
E = [Paragraph(f'Informe semanal: {fecha(ini)} a {fecha(fin)}', T),
     Paragraph('Fuente: Garmin (garmindb)', S), t,
     Paragraph('Lectura', H), Paragraph(notas['lectura'], N),
     Paragraph('Próxima semana (orientativo)', H), Paragraph('<br/>'.join(f'{i}. {p}' for i, p in enumerate(notas['plan'], 1)), N)]
SimpleDocTemplate(os.path.join(salida, f'informe_semanal_{fin.strftime("%Y-%m-%d")}.pdf'), pagesize=A4, leftMargin=1.9 * cm, rightMargin=1.9 * cm,
                  topMargin=1.6 * cm, bottomMargin=1.5 * cm, title='Informe semanal').build(E)
print(filas)
