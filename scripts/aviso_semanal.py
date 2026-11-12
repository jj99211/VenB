"""Aviso de escritorio con el resumen semanal y las fechas próximas. 
Uso: python3 aviso_semanal.py [--prueba]   (--prueba imprime el texto y no envía el aviso)"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from carga import cargar
import rutas



VERDE, AMARILLO, ROJO = '🟢', '🟡', '🔴'


SUBIR, BAJAR, MANTENER = '▲ subir', '▼ bajar', '= ok'
CABECERA = ('Indicador', 'Valor', 'Estado', 'Objetivo')


def color_semana(horas, objetivo):
    """Horas de bici frente al objetivo de Ajustes: verde si se cumple, amarillo desde el 75 %, rojo por debajo. Sin objetivo, sin icono."""
    if not objetivo:
        return ''
    return (VERDE if horas >= objetivo else AMARILLO if horas >= 0.75 * objetivo else ROJO) + ' '


def forma(ctl, previa):
    """Más alta es mejor: el color sigue la tendencia de los últimos 7 días."""
    d = ctl - previa
    color, verbo = (VERDE, 'subiendo') if d > 1 else (ROJO, 'bajando') if d < -1 else (AMARILLO, 'estable')
    return ('Forma (CTL)', f'{color} {ctl:.0f}', f'{verbo} (de {previa:.0f})', SUBIR)


def fatiga(atl, previa, ctl):
    """Solo es mala si supera lo que la forma absorbe: rojo si además sigue subiendo."""
    if atl <= ctl + 5:
        return ('Fatiga (ATL)', f'{VERDE} {atl:.0f}', 'asumible', MANTENER)
    if atl - previa > 3:
        return ('Fatiga (ATL)', f'{ROJO} {atl:.0f}', 'alta y subiendo', BAJAR)
    return ('Fatiga (ATL)', f'{AMARILLO} {atl:.0f}', 'alta', BAJAR)


def frescura(tsb):
    """Importa la zona, no que suba: entrenar la baja a propósito, y demasiado alta significa que se pierde forma."""
    if tsb < -30: color, txt, obj = ROJO, 'muy cargado', SUBIR
    elif tsb < -10: color, txt, obj = AMARILLO, 'cargado', SUBIR
    elif tsb <= 5: color, txt, obj = VERDE, 'equilibrado', MANTENER
    elif tsb <= 25: color, txt, obj = VERDE, 'fresco', MANTENER
    else: color, txt, obj = AMARILLO, 'muy fresco', BAJAR
    return ('Fresc (TSB)', f'{color} {tsb:+.0f}', txt, obj)


def guiones(filas):
    """Línea bajo las cabeceras, tan larga como cada columna."""
    return ['-' * max(len(f[i]) for f in [CABECERA, *filas]) for i in range(len(CABECERA))]


def cuadro_texto(filas):
    """Para la terminal y los escritorios que no admiten tablas."""
    return '\n'.join(' | '.join(c) for c in [CABECERA, guiones(filas), *filas])


def cuadro_html(filas):
    celdas = lambda fila, t: ''.join(f'<{t}>{c}</{t}>' for c in fila)
    return '<table border="1" cellpadding="4" cellspacing="0"><tr>' + celdas(CABECERA, 'td') + '</tr>' + ''.join(f'<tr>{celdas(f, "td")}</tr>' for f in [guiones(filas), *filas]) + '</table>'


def admite_tablas():
    """Plasma (KDE) dibuja tablas en sus notificaciones; otros escritorios las descartan."""
    try:
        r = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.Notifications', '--object-path', '/org/freedesktop/Notifications',
                            '--method', 'org.freedesktop.Notifications.GetServerInformation'], capture_output=True, text=True, timeout=5)
        return 'plasma' in r.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False


hoy = pd.Timestamp.today().normalize()
lineas = []
filas = []
try:
    df, pmc, _ = cargar('garmin', hoy)
    ultima = df.Fecha.max()
    fin = hoy - pd.Timedelta(days=hoy.weekday())  # lunes de esta semana
    ini = fin - pd.Timedelta(days=7)
    b = df[df.bici & (df.Fecha >= ini) & (df.Fecha < fin)]
    h = pmc.iloc[-1]
    horas = f'{b.h.sum():.1f}'.replace('.', ',')
    lineas.append(f'{color_semana(b.h.sum(), rutas.ajustes().get("objetivo_horas_bici_semana"))}Semana pasada: {horas} h y {b.Distancia.sum():.0f} km de bici')
    p = pmc.iloc[-8] if len(pmc) >= 8 else pmc.iloc[0]
    filas = [forma(h.CTL, p.CTL), fatiga(h.ATL, p.ATL, h.CTL), frescura(h.TSB)]
    dias = (hoy - ultima.normalize()).days
    if dias > 10:
        lineas.append(f'ATENCIÓN: última actividad hace {dias} días. Si has rodado, la descarga puede estar fallando.')
except Exception as e:
    lineas.append(f'ATENCIÓN: no se han podido leer los datos ({type(e).__name__}). Revisa la descarga de Garmin.')

if os.path.exists(rutas.AVISOS):
    with open(rutas.AVISOS, encoding='utf-8') as f:
        for a in json.load(f):
            faltan = (pd.Timestamp(a['fecha']) - hoy).days
            if 0 <= faltan <= a.get('dias_antes', 14):
                cuando = 'Hoy' if faltan == 0 else 'Mañana' if faltan == 1 else f'En {faltan} días'
                lineas.append(f"{cuando}: {a['texto']}")

if '--prueba' in sys.argv:
    print('\n'.join([*lineas[:1], cuadro_texto(filas), *lineas[1:]]) if filas else '\n'.join(lineas))
else:
    cuadro = (cuadro_html if admite_tablas() else cuadro_texto)(filas) if filas else ''
    texto = '\n'.join([*lineas[:1], cuadro, *lineas[1:]]) if filas else '\n'.join(lineas)
    subprocess.run(['notify-send', '-u', 'critical', '-a', 'VenB', 'Resumen semanal de VenB', texto], check=True)
