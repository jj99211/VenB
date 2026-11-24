"""Informe semanal en PDF (volumen, carga, descanso y gráficas) de la semana de lunes a domingo.
VenB lo genera solo cada semana (venb/datos_venb.py: informe_en_segundo_plano) en VenB-datos/informes/<domingo>_semanal/.
Uso: python3 informe_semanal.py <domingo AAAA-MM-DD> [<notas.json>] [<carpeta_salida>]
notas.json (opcional): {"lectura": "...", "plan": ["...", "..."]}; añade «Lectura» y «Próxima semana»."""
import json
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402

import graficos  # noqa: E402
import rutas  # noqa: E402

NOMBRE = 'informe_semanal_{}.pdf'


def carpeta(fin):
    return os.path.join(rutas.INFORMES, f'{fin:%Y-%m-%d}_semanal')


def es(x, d=1):
    return f'{x:.{d}f}'.replace('.', ',')


def _hay(*v):
    return all(x is not None and not (isinstance(x, float) and math.isnan(x)) for x in v)


def semana(df, ini, fin):
    b = df[df.bici & (df.Fecha >= ini) & (df.Fecha < fin + pd.Timedelta(days=1))]
    return b.h.sum(), b.Distancia.sum(), b.tss.sum(), len(b)


def descanso(ini, fin):
    """Medias de FC en reposo, VFC y sueño entre dos fechas; {} si no hay bases de Garmin o no tienen esos datos."""
    ruta_db = rutas.ruta_garmin_db()
    if not ruta_db or not os.path.exists(ruta_db):
        return {}
    try:
        # Desde garmindb 4, sueño y VFC van en sleep.db y hrv.db (antes, tablas de garmin.db)
        d = sqlite3.connect(f'file:{ruta_db}?mode=ro', uri=True)
        esquemas = ['main']
        for nombre in ('sleep', 'hrv'):
            ruta = os.path.join(os.path.dirname(ruta_db), nombre + '.db')
            if os.path.exists(ruta):
                d.execute(f'attach database ? as {nombre}db', (f'file:{ruta}?mode=ro',))
                esquemas.append(nombre + 'db')
        tablas = {r[0] for e in esquemas for r in d.execute(f"select name from {e}.sqlite_master where type='table'")}
        rango = (ini.strftime('%Y-%m-%d'), (fin + pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
        r = {}
        if 'resting_hr' in tablas:
            r['fc'] = pd.read_sql('select avg(resting_heart_rate) from resting_hr where day>=? and day<?', d, params=rango).iloc[0, 0]
        if 'hrv_status_summary' in tablas:
            r['vfc'] = pd.read_sql('select avg(last_night_average) from hrv_status_summary where day>=? and day<?', d, params=rango).iloc[0, 0]
        elif 'hrv' in tablas:
            r['vfc'] = pd.read_sql('select avg(last_night_avg) from hrv where day>=? and day<?', d, params=rango).iloc[0, 0]
        if 'sleep' in tablas:
            sueno = pd.read_sql('select total_sleep, score from sleep where day>=? and day<?', d, params=rango)
            horas = pd.to_timedelta(sueno.total_sleep.astype(str).str.slice(0, 8), errors='coerce').dt.total_seconds() / 3600
            horas = horas[horas > 0]
            r.update(h=horas.mean() if len(horas) else None, score=sueno.score.mean() if len(sueno) else None, noches=len(horas))
        d.close()
        return r
    except (sqlite3.Error, pd.errors.DatabaseError, ValueError):
        return {}


def _en(pmc, dia):
    """Fila de la carga en ese día (o la anterior más cercana); None si no hay datos tan atrás."""
    p = pmc.loc[:dia]
    return p.iloc[-1] if len(p) else None


def generar(fin, salida=None, notas=None, df=None, pmc=None):
    """PDF de la semana que acaba el domingo `fin` y sus gráficas en `salida` (por defecto, informes/<fin>_semanal).
    df y pmc: los de carga.cargar (se recortan a `fin`). Devuelve la ruta del PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    fin = pd.Timestamp(fin).normalize()
    salida = salida or carpeta(fin)
    if df is None or pmc is None:
        from carga import cargar
        df, pmc, _ = cargar('garmin', fin)
    df, pmc = df[df.Fecha < fin + pd.Timedelta(days=1)], pmc.loc[:fin]
    os.makedirs(salida, exist_ok=True)
    ini = fin - pd.Timedelta(days=6)
    h, km, tss, n = semana(df, ini, fin)
    h0, km0, _, _ = semana(df, ini - pd.Timedelta(days=7), fin - pd.Timedelta(days=7))
    h4 = sum(semana(df, ini - pd.Timedelta(days=7 * k), fin - pd.Timedelta(days=7 * k))[0] for k in range(4)) / 4
    hoy, antes = _en(pmc, fin), _en(pmc, fin - pd.Timedelta(days=7))
    r, r0 = descanso(ini, fin), descanso(ini - pd.Timedelta(days=28), ini - pd.Timedelta(days=1))

    st = getSampleStyleSheet()
    N = ParagraphStyle('n', parent=st['Normal'], fontName='Helvetica', fontSize=9.5, leading=13)
    H = ParagraphStyle('h', parent=st['Heading2'], fontName='Helvetica-Bold', fontSize=11, spaceBefore=8, spaceAfter=3)
    T = ParagraphStyle('t', parent=st['Title'], fontName='Helvetica-Bold', fontSize=14, alignment=0, spaceAfter=2)
    S = ParagraphStyle('s', parent=N, fontSize=8.5, textColor=colors.HexColor('#52514e'))
    C = ParagraphStyle('c', parent=N, fontSize=8.5, leading=10.5)
    filas = [['', 'Esta semana', 'Referencia'],
             ['Volumen de bici', f'{es(h)} h, {km:.0f} km, {n} {"salida" if n == 1 else "salidas"}',
              f'Semana anterior: {es(h0)} h, {km0:.0f} km; media de 4 semanas: {es(h4)} h']]
    if hoy is not None:
        filas.append(['Forma / fatiga / frescura (CTL / ATL / TSB)', f'{hoy.CTL:.0f} / {hoy.ATL:.0f} / {hoy.TSB:+.0f}',
                      f'Hace 7 días: {antes.CTL:.0f} / {antes.ATL:.0f} / {antes.TSB:+.0f}' if antes is not None else ''])
    filas.append(['TSS semanal', f'{tss:.0f}', 'Con potencia, el de la actividad; sin potencia, estimado por la duración'])
    if _hay(r.get('h'), r.get('score')):
        ref = f'4 semanas previas: {es(r0["h"])} h, puntuación {r0["score"]:.0f}' if _hay(r0.get('h'), r0.get('score')) else ''
        filas.append(['Sueño', f'{es(r["h"])} h/noche, puntuación {r["score"]:.0f} ({r["noches"]} noches)', ref])
    if _hay(r.get('fc'), r.get('vfc')):
        ref = f'4 semanas previas: {r0["fc"]:.0f} ppm / {r0["vfc"]:.0f} ms' if _hay(r0.get('fc'), r0.get('vfc')) else ''
        filas.append(['FC en reposo / VFC', f'{r["fc"]:.0f} ppm / {r["vfc"]:.0f} ms', ref])
    filas = [filas[0]] + [[Paragraph(str(c), C) for c in f] for f in filas[1:]]
    t = Table(filas, colWidths=[3.6 * cm, 5.4 * cm, 8.2 * cm])
    t.setStyle(TableStyle([('FONT', (0, 0), (-1, -1), 'Helvetica', 8.5), ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8.5),
                           ('LINEBELOW', (0, 0), (-1, 0), .6, colors.black), ('LINEBELOW', (0, -1), (-1, -1), .4, colors.grey),
                           ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    fecha = lambda x: f'{x.day:02d}/{x.month:02d}/{x.year}'  # noqa: E731
    E = [Paragraph(f'Informe semanal: {fecha(ini)} a {fecha(fin)}', T),
         Paragraph('Actividades de VenB (Garmin e importadas)', S), t]
    if notas:
        E += [Paragraph('Lectura', H), Paragraph(notas.get('lectura', ''), N)]
        if notas.get('plan'):
            E += [Paragraph('Próxima semana (orientativo)', H), Paragraph('<br/>'.join(f'{i}. {p}' for i, p in enumerate(notas['plan'], 1)), N)]
    if len(pmc):
        graficos.generar(salida, df, pmc)
        E.append(Spacer(1, .4 * cm))
        for nombre, alto in (('carga_ctl_atl_tsb', 4.6), ('horas_semanales', 2.8)):
            E.append(Image(os.path.join(salida, nombre + '.png'), width=16 * cm, height=16 * cm * alto / 8))
    ruta = os.path.join(salida, NOMBRE.format(f'{fin:%Y-%m-%d}'))
    tmp = ruta + '.tmp'
    SimpleDocTemplate(tmp, pagesize=A4, leftMargin=1.9 * cm, rightMargin=1.9 * cm, topMargin=1.6 * cm, bottomMargin=1.5 * cm,
                      title='Informe semanal').build(E)
    os.replace(tmp, ruta)
    return ruta


if __name__ == '__main__':
    fin = pd.Timestamp(sys.argv[1])
    notas = json.load(open(sys.argv[2], encoding='utf-8')) if len(sys.argv) > 2 and sys.argv[2] != '-' else None
    print(generar(fin, sys.argv[3] if len(sys.argv) > 3 else None, notas))
