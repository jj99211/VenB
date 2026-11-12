"""VenB (Vivir en Bici): consulta local de historial, informes y calendario.
Autor: José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0 (ver LICENSE.md).
Uso: python3 app.py (solo accesible desde este ordenador, salvo que en Ajustes se abra a la red local con clave;
el puerto, `puerto` o, en VenB Rutas, `puerto_rutas` de config/predeterminados.json)"""
import os
import re
import shutil
import tempfile
import threading
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
import markdown
import pandas as pd
from flask import Flask, abort, after_this_request, jsonify, redirect, render_template, request, Response, send_file, send_from_directory, session, url_for
import actualizaciones as AC
import bicis as BI
import brevets as BR
import clubes as CL
import copia as CO
import datos_venb as D
import diario as DI
import importar as IM
import planificador as PL
import red as RED
import rutas as R
from version import VERSION

PUERTO = R.puerto()
ESCUCHA = RED.host_escucha()  # 127.0.0.1 o, abierta a la red local, 0.0.0.0. Cambiarlo exige reiniciar VenB.
app = Flask(__name__)
app.jinja_env.globals.update(freno_garmin=D.FR.estado, aviso_freno_garmin=D.FR.aviso, evento_de_plan=D.evento_local)
app.jinja_env.tests['match_local'] = lambda v: bool(IM.ES_ID.fullmatch(str(v)))
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024
AC.en_segundo_plano()  # ¿hay una versión nueva en GitHub? (como mucho cada AC.CADA_H horas)


app.secret_key = RED.clave_sesion()
app.config.update(SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_HTTPONLY=True, PERMANENT_SESSION_LIFETIME=timedelta(days=90))
# Desde otro equipo no se puede cerrar ni actualizar VenB ni tocar la cuenta de Garmin, las copias o el propio acceso por red.
SOLO_ESTE_EQUIPO = {'cerrar', 'actualizar', 'actualizaciones_buscar', 'garmin_cuenta', 'garmin_descargar', 'garmin_usar', 'copia_exportar', 'copia_importar', 'red_ajustes'}


def remoto():
    return not RED.es_local(request.remote_addr or '')


@app.before_request
def solo_local():
    """Desde este ordenador, como siempre. Desde otro equipo, solo si está abierto a la red local, desde una IP privada
    y con la clave. Se rechazan las peticiones que llegan desde otras webs."""
    if not remoto():
        if request.host not in (f'127.0.0.1:{PUERTO}', f'localhost:{PUERTO}'):
            abort(403)
    else:
        if not RED.activada() or not RED.es_red_privada(request.remote_addr) or not RED.host_valido(request.host, PUERTO):
            abort(403)
        if request.endpoint in SOLO_ESTE_EQUIPO:
            abort(403, 'Esto solo se puede hacer desde el ordenador donde está instalada VenB.')
        if request.endpoint not in ('entrar', 'static') and session.get('red') != RED.marca_clave():
            return redirect(url_for('entrar', siguiente=request.full_path if request.method == 'GET' else None))
    if request.method == 'POST':
        origen = request.headers.get('Origin')
        if origen and urlparse(origen).netloc != request.host:
            abort(403)
    if RUTAS and request.endpoint and not request.endpoint.startswith(EN_RUTAS):
        if request.method == 'GET':
            return redirect(url_for('planificador'))
        abort(404)


@app.route('/entrar', methods=['GET', 'POST'])
def entrar():
    if not remoto():
        return redirect(url_for('inicio'))
    error = ''
    if request.method == 'POST':
        ok, error = RED.comprobar(request.form.get('clave', ''))
        if ok:
            session.clear()
            session.permanent = True
            session['red'] = RED.marca_clave()
            sig = request.form.get('siguiente', '')
            return redirect(sig if sig.startswith('/') and not sig.startswith('//') else url_for('inicio'))
    return render_template('entrar.html', error=error, siguiente=request.values.get('siguiente', ''))


@app.post('/salir')
def salir():
    session.clear()
    return redirect(url_for('entrar') if remoto() else url_for('inicio'))


# Menú: (página, texto, submenú). Brevets va en el primer nivel; Gráficas repite en el submenú la página de Análisis, para que se vea. Cada página secundaria se marca en su sección por el prefijo de su función.
MENU = [('inicio', 'Inicio', []),
        ('graficas', 'Análisis', [('graficas', 'Gráficas'), ('historico', 'Histórico'), ('importar', 'Importar'), ('bicis', 'Bicis'), ('informes', 'Informes')]),
        ('brevets', 'Brevets', []), ('planificador', 'Planificador', []), ('calendario', 'Calendario', []), ('ajustes', 'Ajustes', []),
        ('ayuda', 'Ayuda', [('ayuda', 'Manual de usuario'), ('acerca', 'Acerca de')])]
# VenB Rutas (solo el Planificador): menú reducido; el resto de páginas no existe en esa edición
RUTAS = R.RUTAS
NOMBRE_APP = 'VenB Rutas' if RUTAS else 'VenB'
MENU_RUTAS = [('planificador', 'Planificador', []), ('ajustes', 'Ajustes', []),
              ('ayuda', 'Ayuda', [('ayuda', 'Manual del Planificador'), ('acerca', 'Acerca de')])]
EN_RUTAS = ('planificador', 'plan', 'ajustes', 'club', 'red', 'copia', 'ayuda', 'acerca', 'static', 'entrar', 'salir', 'cerrar', 'actualiza')
PREFIJOS = {'club': 'ajustes', 'importar': 'importar', 'brevet': 'brevets', 'bici': 'bicis', 'actividad': 'historico', 'informe': 'informes', 'diario': 'informes', 'plan': 'planificador',
            'evento': 'calendario', 'fecha_clave': 'calendario', 'actualiza': 'acerca', 'garmin': 'ajustes', 'copia': 'ajustes', 'red': 'ajustes', 'datos_graficas': 'graficas'}


def seccion(ep):
    """(página del menú principal, página del submenú) a la que pertenece un endpoint."""
    ep = ep or ''
    pagina = next((v for k, v in sorted(PREFIJOS.items(), key=lambda x: -len(x[0])) if ep == k or ep.startswith(k + '_') or ep.startswith(k + 's')), ep)
    # Una página del primer nivel manda (Brevets está también en Análisis); se marca además en el submenú donde aparezca
    if any(pagina == ruta for ruta, _, _ in MENU):
        return pagina, pagina
    for ruta, _, sub in MENU:
        if any(pagina == r for r, _ in sub):
            return ruta, pagina
    return '', ''


@app.context_processor
def contexto():
    return {'version': VERSION, 'remoto': remoto(), 'menu': MENU_RUTAS if RUTAS else MENU, 'seccion': seccion(request.endpoint),
            'rutas': RUTAS, 'nombre_app': NOMBRE_APP, 'nueva_version': AC.nueva, 'no_actualizable': AC.se_puede_actualizar}


@app.template_filter('n')
def numero(x, d=0):
    """Formato español: 1.234,5"""
    if x is None or pd.isna(x):
        return '–'
    return f'{x:,.{d}f}'.replace(',', ' ').replace('.', ',').replace(' ', '.')


@app.template_filter('hm')
def horas_minutos(h):
    """Duración legible: 9,25 h -> 9h15m; 0,5 -> 0h30m. Los totales de 100 h o más, solo en horas: 407h."""
    if h is None or pd.isna(h):
        return '–'
    m = int(round(float(h) * 60))
    if m >= 100 * 60:
        return numero(m / 60) + 'h'
    return f'{m // 60}h{m % 60:02d}m'


@app.template_filter('signo')
def signo(x):
    return '–' if x is None or pd.isna(x) else f'{x:+.0f}'.replace('-', '−')


@app.template_filter('fecha')
def fecha(x):
    return f'{x.day:02d}/{x.month:02d}/{x.year}'


@app.template_filter('iso_fecha')
def iso_fecha(txt):
    return fecha(date.fromisoformat(txt)) if txt else '–'


@app.template_filter('tiempo')
def tiempo(h):
    return BR.formato_tiempo(h) or '–'


@app.template_filter('fecha_pieza')
def fecha_pieza(p):
    """Algunos registros importados solo conocen el mes."""
    f = date.fromisoformat(p['fecha'])
    return f'{f.month:02d}/{f.year}' if p.get('aprox') else fecha(f)


def leer_fecha(txt):
    return datetime.strptime(txt.strip(), '%d/%m/%Y').date()


def leer_km(txt):
    """Admite el formato español: 5.000 son cinco mil kilómetros y 12,5 lleva decimales."""
    txt = txt.strip()
    if re.fullmatch(r'\d{1,3}(\.\d{3})+(,\d+)?', txt):
        txt = txt.replace('.', '')
    return float(txt.replace(',', '.'))


@app.route('/')
def inicio():
    D.descargar_recientes(horas=R.ajustes().get('horas_descarga_garmin', 3))  # cada pocas horas mientras VenB está abierta
    AC.en_segundo_plano()
    aviso_carga, m, sem, ant, ultimas, sp = None, None, None, None, [], {}
    try:
        sp = D.tendencias(D.graficas())
        df, pmc = D.carga()
        h, a = pmc.iloc[-1], pmc.iloc[-8]
        m = {'CTL': h.CTL, 'ATL': h.ATL, 'TSB': h.TSB, 'dCTL': h.CTL - a.CTL}
        lunes = pd.Timestamp.today().normalize() - pd.Timedelta(days=pd.Timestamp.today().weekday())
        sem, ant = D.resumen_semana(df, lunes), D.resumen_semana(df, lunes - pd.Timedelta(days=7))
        m.update(D.resumen_mes_y_potencia(df))
        ultimas = df.sort_values('Fecha').tail(25).iloc[::-1].to_dict('records')
    except Exception:
        aviso_carga = True
    meses, _ = D.proximos_eventos(12)
    prox = [e for x in meses for e in x['eventos']][:5]
    p = D.pesos()
    return render_template('inicio.html', sp=sp, m=m, sem=sem, ant=ant, s=D.salud(), avisos=D.avisos(), consejo=D.ultimo_consejo(), prox=prox,
                           peso=(date.fromisoformat(p[-1][0]), p[-1][1]) if p else None, ultimas=ultimas, hoy=fecha(date.today()), error_carga=aviso_carga,
                           error_peso=request.args.get('error_peso'), peso_enviado=request.args.get('peso_enviado'), peso_desde_garmin=D.peso_desde_garmin(),
                           garmin_listo=D.usar_garmin() and bool(D.usuario_garmin()), recientes=D.estado_recientes(), aviso_garmin=request.args.get('aviso_garmin'))


@app.post('/garmin/actualizar')
def garmin_actualizar():
    error = D.descargar_recientes(forzar=True)
    return redirect(url_for('inicio', aviso_garmin=error, _anchor='ultimas') if error else url_for('inicio', _anchor='ultimas'))


@app.route('/garmin/estado')
def garmin_estado():
    e = D.estado_recientes()
    return jsonify(en_curso=e['en_curso'], resultado=e['resultado'], nuevas=e['nuevas'])


@app.post('/peso')
def peso():
    try:
        kg = float(request.form['kg'].replace(',', '.'))
        f = leer_fecha(request.form['fecha'])
    except (KeyError, ValueError):
        abort(400)
    if not 30 <= kg <= 200 or f > date.today():
        abort(400)
    D.anotar_peso(f.isoformat(), round(kg, 1))
    error = D.enviar_peso(f.isoformat(), round(kg, 1))
    return redirect(url_for('inicio', error_peso=error) if error else url_for('inicio', peso_enviado=1) if D.peso_desde_garmin() else url_for('inicio'))


@app.post('/aviso/cerrar')
def aviso_cerrar():
    clave = request.form.get('clave', '').strip()
    if not clave:
        abort(400)
    D.cerrar_aviso(clave)
    return redirect(url_for('inicio'))


@app.route('/analisis')
@app.route('/graficas')
def graficas():
    """Página Análisis: las gráficas y los accesos a Brevets, Histórico, Importar, Bicis e Informes."""
    return render_template('graficas.html')


@app.route('/datos/graficas.json')
def datos_graficas():
    try:
        return jsonify(D.graficas())
    except LookupError:
        abort(503)


@app.post('/cerrar')
def cerrar():
    """Muestra la despedida y termina el proceso cuando ya se ha enviado."""
    threading.Timer(1.5, os._exit, [0]).start()
    return render_template('cerrada.html')


@app.post('/actualizar')
def actualizar():
    """Descarga la versión nueva y, al terminar, cierra VenB y ejecuta su instalador (ver actualizaciones.py)."""
    n = AC.nueva()
    if not n or AC.se_puede_actualizar():
        return redirect(url_for('acerca'))
    AC.actualizar()
    return render_template('actualizando.html', n=n, windows=os.name == 'nt')


@app.route('/actualizar/estado')
def actualizar_estado():
    return jsonify({**AC.progreso(), 'version': VERSION})


@app.post('/actualizaciones/buscar')
def actualizaciones_buscar():
    AC.en_segundo_plano(forzar=True)
    return redirect(url_for('acerca', buscando=1, _anchor='versiones'))


@app.route('/diario')
def diario():
    """El diario está ahora en la página Informes (enlaces antiguos)."""
    return redirect(url_for('informes', editar=request.args.get('editar') or None, _anchor='nota' if request.args.get('editar') else 'notas'))


@app.post('/diario/guardar')
def diario_guardar():
    try:
        f = leer_fecha(request.form['fecha'])
    except (KeyError, ValueError):
        abort(400)
    texto = request.form.get('texto', '').replace('\r\n', '\n').strip()[:20000]
    if not texto:
        abort(400)
    try:
        DI.anotar(f.isoformat(), texto, request.form.get('id') or None)
    except KeyError:
        abort(404)
    return redirect(url_for('informes', _anchor='notas'))


@app.post('/diario/borrar/<nid>')
def diario_borrar(nid):
    DI.borrar(nid)
    return redirect(url_for('informes', _anchor='notas'))


@app.route('/historico')
def historico():
    d = D.historico()
    if d.empty:
        return render_template('sin_datos.html')
    anual = d[d.bici].groupby(d.fecha.dt.year).agg(n=('km', 'size'), km=('km', 'sum'), h=('h', 'sum'), desnivel=('desnivel', 'sum'), maximo=('km', 'max')).sort_index(ascending=False)
    q = request.args.get('q', '').strip()
    anio, tipo, minimo = request.args.get('anio', ''), request.args.get('tipo', ''), request.args.get('minkm', '')
    f = d
    if anio.isdigit():
        f = f[f.fecha.dt.year == int(anio)]
    if tipo == 'bici':
        f = f[f.bici]
    elif tipo:
        f = f[f.tipo == tipo]
    try:
        if minimo:
            f = f[f.km >= float(minimo.replace(',', '.'))]
    except ValueError:
        minimo = ''
    if q:
        f = f[f.titulo.str.contains(q, case=False, regex=False)]
    f = f.sort_values('fecha', ascending=False)
    km_prueba = R.ajustes().get('km_aviso_prueba', 190)
    try:
        en_brevets = BR.registradas(d, km_prueba)
    except Exception:
        en_brevets = set()
    return render_template('historico.html', km_prueba=km_prueba, km_enlace=R.ajustes().get('km_enlace_garmin', 7), en_brevets=en_brevets, anual=anual.reset_index().to_dict('records'), filas=f.head(500).to_dict('records'), total=len(f), km=f.km.sum(), horas=f.h.sum(),
                           anios=sorted(d.fecha.dt.year.unique(), reverse=True), tipos=sorted(d.tipo.dropna().unique()), q=q, anio=anio, tipo=tipo, minkm=minimo,
                           primero=d.fecha.min(), ultimo=d.fecha.max(), dups=D._cache.get('hist_dups', 0), url_garmin=BR.URL_GARMIN,
                           asig=BI.asignaciones(con_origen=True), opciones_bici=BI.opciones_bici())


@app.route('/actividad/<aid>/resumen.json')
def actividad_resumen(aid):
    """Datos principales, perfil y track de una actividad (ventana de resumen del Histórico)."""
    if not es_actividad(aid):
        abort(404)
    r = D.resumen_actividad(aid)
    if r is None:
        abort(404)
    r['garmin'] = None if IM.ES_ID.fullmatch(aid) else BR.URL_GARMIN.format(aid)
    v = BI.asignaciones(con_origen=True).get(aid)
    r['bici_nombre'] = next((o['texto'] for o in BI.opciones_bici() if v and o['valor'] == '|'.join(v[0])), None)
    return jsonify(r)


@app.route('/actividad/<aid>/nombre', methods=['GET', 'POST'])
def actividad_nombre(aid):
    """Cambia el nombre en Garmin Connect y en las copias locales."""
    if not es_actividad(aid):
        abort(404)
    a = D.actividad(aid)
    if a is None:
        abort(404)
    volver = request.values.get('volver', '')
    if not volver.startswith('/') or volver.startswith('//') or '\\' in volver:
        volver = url_for('historico')
    error, nombre = None, a['titulo']
    if request.method == 'POST':
        nombre = ' '.join(request.form.get('nombre', '').split())[:100]
        if not nombre:
            error = 'Escribe un nombre.'
        else:
            error = D.renombrar_actividad(aid, nombre)
            if not error:
                return redirect(volver)
    return render_template('actividad_nombre.html', a=a, nombre=nombre, volver=volver, error=error)


@app.post('/actividad/<aid>/bici')
def actividad_bici(aid):
    """Asigna (o quita) la bici de una actividad. En un mes cerrado no cambia sus km: solo avisa."""
    if not es_actividad(aid):
        abort(404)
    a = D.actividad(aid)
    if a is None:
        return jsonify(error='No encuentro la actividad.'), 404
    try:
        BI.asignar(aid, request.form.get('bici', ''))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    mes = pd.Timestamp(a['fecha']).strftime('%Y-%m')
    avisos = []
    efectiva = BI.asignaciones(con_origen=True).get(aid)
    if efectiva and efectiva[1] == 'garmin':
        avisos.append('Según Garmin Connect')
    if mes in BI.cierres():
        avisos.append(f'{D.MES[int(mes[5:7]) - 1].capitalize()} de {mes[:4]} está cerrado: sus km por bici no cambian. '
                      'Si quieres corregirlos, edita ese mes en Bicis.')
    return jsonify(ok=True, valor='|'.join(efectiva[0]) if efectiva else '', aviso='. '.join(avisos))


def es_actividad(aid):
    """Identificador de Garmin (número) o de una actividad subida a mano (L + fecha y hora)."""
    return aid.isdigit() or bool(IM.ES_ID.fullmatch(aid))


@app.post('/actividad/<aid>/borrar')
def actividad_borrar(aid):
    """Solo las subidas a mano: las de Garmin se borran en Garmin Connect."""
    if not IM.ES_ID.fullmatch(aid):
        abort(404)
    IM.borrar(aid)
    BI.asignar(aid, '')
    D._cache.clear()
    volver = request.form.get('volver', '')
    return redirect(volver if volver.startswith('/') and not volver.startswith('//') and '\\' not in volver else url_for('historico'))


# ---------- Importar actividades de ficheros ----------
MAX_IMPORTAR = 500 * 1024 ** 2


@app.route('/importar', methods=['GET', 'POST'])
def importar():
    if request.method == 'GET':
        return render_template('importar.html', extensiones=', '.join(e.upper()[1:] for e in IM.EXTENSIONES))
    request.max_content_length = MAX_IMPORTAR
    ficheros = [(f.filename, f) for f in request.files.getlist('ficheros') if f and f.filename]
    if not ficheros:
        return render_template('importar.html', error='Elige uno o varios ficheros.', extensiones=', '.join(e.upper()[1:] for e in IM.EXTENSIONES))
    h = D.historico()
    existentes = None
    if not h.empty:
        existentes = h[['fecha', 'titulo']].copy()
        existentes['fin'] = h.fin if 'fin' in h else h.fecha + pd.to_timedelta(h.h_total.fillna(h.h).fillna(0), unit='h')
    lote, filas = IM.preparar(ficheros, existentes)
    return render_template('importar_revisar.html', lote=lote, filas=filas, tipos=IM.TIPOS, opciones_bici=BI.opciones_bici())


@app.post('/importar/<lote>/confirmar')
def importar_confirmar(lote):
    filas = IM.leer_lote(lote)
    if filas is None:
        return render_template('importar.html', error='El envío ha caducado o ya se ha importado: vuelve a subir los ficheros.',
                               extensiones=', '.join(e.upper()[1:] for e in IM.EXTENSIONES))
    valores = {o['valor'] for o in BI.opciones_bici()}
    elegidas, bicis = {}, {}
    for x in filas:
        n = x['n']
        if x.get('error') or not request.form.get(f'importar_{n}'):
            continue
        elegidas[n] = {'tipo': request.form.get(f'tipo_{n}', ''), 'titulo': request.form.get(f'titulo_{n}', '')}
        b = request.form.get(f'bici_{n}', '')
        if b in valores:
            bicis[n] = b
    try:
        hechas = IM.confirmar(lote, elegidas)
    except IM.ErrorFichero as e:
        return render_template('importar.html', error=str(e), extensiones=', '.join(e.upper()[1:] for e in IM.EXTENSIONES))
    cierres, activas = set(BI.cierres()), {b['id'] for b in BI.activas()}
    sumar = {}
    for aid, x in hechas:
        b = bicis.get(x['n'])
        if not b:
            continue
        BI.asignar(aid, b)
        mes = x['fecha'].strftime('%Y-%m')
        # en un mes ya cerrado, los km de las bicis no cambian solos: se ofrece sumarlos
        if mes in cierres and b.split('|')[0] in activas and x['tipo'] in D.BICI:
            sumar[(mes, b)] = sumar.get((mes, b), 0) + x['km']
    D._cache.clear()
    nombres = {o['valor']: o['texto'] for o in BI.opciones_bici()}
    ofertas = [{'mes': m, 'mes_txt': f'{D.MES[int(m[5:7]) - 1]} de {m[:4]}', 'bici': b, 'nombre': nombres.get(b, b), 'km': round(km)}
               for (m, b), km in sorted(sumar.items()) if round(km)]
    try:      # salidas largas importadas sin prueba registrada: se pregunta por cada una
        km_min = R.ajustes().get('km_aviso_prueba', 190)
        ids = {str(aid) for aid, _ in hechas}
        largas = [s for s in BR.sin_registrar(D.historico(), km_min) if str(s.id) in ids]
    except Exception:
        largas, km_min = [], 0
    return render_template('importar_hecho.html', hechas=hechas, ofertas=ofertas, nombres=nombres, bicis=bicis, largas=largas, km_min=km_min)


@app.post('/importar/<lote>/descartar')
def importar_descartar(lote):
    IM.descartar(lote)
    return redirect(url_for('importar'))


@app.post('/bicis/sumar')
def bicis_sumar():
    """Suma a un mes (normalmente cerrado) los km de actividades subidas después."""
    mes, valor = request.form.get('mes', ''), request.form.get('bici', '')
    try:
        datetime.strptime(mes, '%Y-%m')
        km = leer_km(request.form.get('km', ''))
    except ValueError:
        abort(400)
    if valor not in {o['valor'] for o in BI.opciones_bici()} or not 0 < km <= 20000:
        abort(400)
    bici, rod = valor.split('|', 1)
    actual = sum(r['km'] for r in BI.km_filas() if r['mes'] == mes and r['bici'] == bici and r['rodadura'] == rod)
    BI.anotar_km(mes, bici, actual + km, rod)
    return redirect(url_for('bicis', mes=f'{mes[5:7]}/{mes[:4]}', _anchor='mes'))


# ---------- Bicis de Garmin Connect ----------
@app.post('/bicis/garmin/leer')
def bicis_garmin_leer():
    error = D.actualizar_equipo_garmin()
    return redirect(url_for('bicis', error_equipo=error, _anchor='garmin') if error else url_for('bicis', _anchor='garmin'))


@app.post('/bicis/garmin/corresponder')
def bicis_garmin_corresponder():
    BI.corresponder({k[5:]: v for k, v in request.form.items() if k.startswith('gear_')})
    return redirect(url_for('bicis', _anchor='garmin'))


@app.post('/ajustes/garmin')
def garmin_usar():
    aviso = D.elegir_usar_garmin(request.form.get('usar_garmin') == 'si')
    return pagina_ajustes(error_garmin=aviso) if aviso else redirect(url_for('ajustes', _anchor='garmin'))


@app.route('/informes')
def informes():
    """Informes: el diario (escribir y leer notas), los informes y las revisiones."""
    notas = DI.todas()
    e = next((n for n in notas if n['id'] == request.args.get('editar')), None)
    return render_template('informes.html', informes=D.informes(), estados=D.estados(), notas=notas, e=e, hoy=fecha(date.today()))


@app.route('/informes/<carpeta>/<nombre>')
def informe_fichero(carpeta, nombre):
    if not nombre.endswith(('.pdf', '.svg')):
        abort(404)
    return send_from_directory(f'{D.INFORMES}/{carpeta}', nombre)


@app.route('/calendario')
def calendario():
    meses, error = D.proximos_eventos(14)
    return render_template('calendario.html', meses=meses, error=error, conectado=D.calendario_propio(), ver_defecto=R.ajustes().get('calendario_defecto_ver', True),
                           hoy=fecha(date.today()), origenes=D.ORIGENES, sin_ver=D.calendarios_ocultos(), ocultos=D.ocultos())


@app.post('/calendario/ver')
def calendario_ver():
    """Interruptor de un calendario en la página (Randonneurs, Mío, VenB, Fecha clave)."""
    try:
        D.ver_calendario(request.form.get('origen', ''), request.form.get('ver') == '1')
    except ValueError:
        abort(400)
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify(ok=True)
    return redirect(url_for('calendario'))


@app.post('/calendario/ocultar')
def calendario_ocultar():
    f = request.form
    if not f.get('uid'):
        abort(400)
    D.ocultar_evento(f['uid'][:300], f.get('nombre', '')[:150], f.get('fecha', '')[:10], f.get('origen', '')[:30])
    return redirect(url_for('calendario'))


@app.post('/calendario/mostrar')
def calendario_mostrar():
    D.mostrar_evento(request.form.get('uid', ''))
    return redirect(url_for('calendario', _anchor='ocultos'))


@app.post('/calendario/copiar')
def calendario_copiar():
    f = request.form
    try:
        d = date.fromisoformat(f.get('fecha', ''))
    except ValueError:
        abort(400)
    if not f.get('nombre'):
        abort(400)
    eid = D.copiar_evento(f.get('uid', '')[:300], d.isoformat(), f['nombre'][:150], f.get('notas', '')[:300], f.get('origen', '')[:30])
    return redirect(url_for('evento_editar', eid=eid))


def _evento(eid):
    e = D.evento_local(eid)
    if not e:
        abort(404)
    try:
        D.carpeta_evento(eid)
    except ValueError:
        abort(404)
    return e


EXT_ADJUNTO = {'gpx': PL.EXT_GPX, 'hoja': PL.EXT_HOJA}


@app.route('/calendario/evento/<eid>', methods=['GET', 'POST'])
def evento_editar(eid):
    e = _evento(eid)
    error = request.args.get('error')
    if request.method == 'POST':
        request.max_content_length = 100 * 1024 ** 2
        try:
            f = leer_fecha(request.form['fecha'])
            nombre = request.form['nombre'].strip()[:150]
        except (KeyError, ValueError):
            abort(400)
        if not nombre:
            abort(400)
        cambios = {'fecha': f.isoformat(), 'nombre': nombre, 'notas': request.form.get('notas', '').strip()[:300]}
        carpeta = D.carpeta_evento(eid)
        for tipo, exts in EXT_ADJUNTO.items():
            fs = request.files.get(tipo)
            if request.form.get(f'quitar_{tipo}') and e.get(tipo):
                ruta = os.path.join(carpeta, e[tipo])
                if os.path.exists(ruta):
                    os.remove(ruta)
                cambios[tipo] = ''
            if fs and fs.filename:
                ext = os.path.splitext(fs.filename)[1].lower()
                if ext not in exts:
                    error = f"El {'track' if tipo == 'gpx' else 'fichero de la hoja de ruta'} debe ser {', '.join(x.upper()[1:] for x in exts)}."
                    continue
                os.makedirs(carpeta, exist_ok=True)
                nombre_f = PL._nombre_seguro(fs.filename, ext)
                if e.get(tipo) and e[tipo] != nombre_f and os.path.exists(os.path.join(carpeta, e[tipo])):
                    os.remove(os.path.join(carpeta, e[tipo]))
                fs.save(os.path.join(carpeta, nombre_f))
                cambios[tipo] = nombre_f
        e = D.editar_evento(eid, **cambios)
        if not error:
            return redirect(url_for('evento_editar', eid=eid, guardado=1))
    plan = None
    if e.get('plan'):
        try:
            plan = PL.estado(e['plan'])
        except KeyError:
            plan = None
    return render_template('evento.html', e=e, fecha_txt=fecha(date.fromisoformat(e['fecha'])), error=error, guardado=request.args.get('guardado'),
                           plan=plan, planes=PL.lista(), ext_hoja=', '.join(PL.EXT_HOJA))


class _FicheroLocal:
    """Un fichero del disco con la interfaz mínima de los subidos (filename y save), para PL.crear."""
    def __init__(self, ruta):
        self.filename, self._ruta = os.path.basename(ruta), ruta

    def save(self, destino):
        shutil.copyfile(self._ruta, destino)


@app.post('/calendario/evento/<eid>/plan')
def evento_plan(eid):
    e = _evento(eid)
    accion = request.form.get('accion')
    if accion == 'crear':
        if not e.get('gpx'):
            abort(400)
        carpeta = D.carpeta_evento(eid)
        try:
            pid = PL.crear(_FicheroLocal(os.path.join(carpeta, e['gpx'])),
                           _FicheroLocal(os.path.join(carpeta, e['hoja'])) if e.get('hoja') else None, evento=eid)
        except (PL.ErrorPlan, OSError) as ex:
            return redirect(url_for('evento_editar', eid=eid, error=str(ex)))
        D.editar_evento(eid, plan=pid)
        return redirect(url_for('plan_ver', pid=pid))
    if accion == 'enlazar':
        pid = request.form.get('pid', '')
        try:
            PL.estado(pid)
        except KeyError:
            abort(400)
        if e.get('plan') and e['plan'] != pid:
            try:
                PL.enlazar_evento(e['plan'], None)
            except KeyError:
                pass
        PL.enlazar_evento(pid, eid)
        D.editar_evento(eid, plan=pid)
    elif accion == 'quitar' and e.get('plan'):
        try:
            PL.enlazar_evento(e['plan'], None)
        except KeyError:
            pass
        D.editar_evento(eid, plan='')
    return redirect(url_for('evento_editar', eid=eid))


@app.route('/calendario/evento/<eid>/fichero/<tipo>')
def evento_fichero(eid, tipo):
    e = _evento(eid)
    if tipo not in EXT_ADJUNTO or not e.get(tipo):
        abort(404)
    ruta = os.path.join(D.carpeta_evento(eid), e[tipo])
    if not os.path.exists(ruta):
        abort(404)
    return send_file(ruta, as_attachment=True)


@app.route('/calendario/venb.ics')
def calendario_ics():
    return Response(D.exportar_ics(), mimetype='text/calendar', headers={'Content-Disposition': 'attachment; filename="VenB.ics"'})


@app.post('/calendario/nuevo')
def evento_nuevo():
    try:
        f = leer_fecha(request.form['fecha'])
        nombre = request.form['nombre'].strip()[:150]
    except (KeyError, ValueError):
        abort(400)
    if not nombre:
        abort(400)
    D.anadir_evento(f.isoformat(), nombre, request.form.get('notas', '').strip()[:300])
    return redirect(url_for('calendario'))


@app.post('/calendario/fecha-clave')
def fecha_clave_nueva():
    try:
        f = leer_fecha(request.form['fecha'])
        dias = int(request.form.get('dias_antes') or 14)
        texto = request.form['texto'].strip()[:200]
    except (KeyError, ValueError):
        abort(400)
    if not texto or not 0 <= dias <= 365:
        abort(400)
    D.anadir_fecha_clave(f.isoformat(), texto, dias)
    return redirect(url_for('calendario'))


@app.post('/calendario/fecha-clave/borrar/<fid>')
def fecha_clave_borrar(fid):
    D.borrar_fecha_clave(fid)
    return redirect(url_for('calendario'))


@app.post('/calendario/borrar/<eid>')
def evento_borrar(eid):
    D.borrar_evento(eid)
    return redirect(url_for('calendario'))


@app.route('/bicis')
def bicis():
    bs = BI.cargar_bicis()
    hoy = date.today()
    try:
        mes = datetime.strptime(request.args.get('mes', ''), '%m/%Y').strftime('%Y-%m')
    except ValueError:
        mes = BI.mes_a_preguntar() or f'{hoy.year}-{hoy.month:02d}'
    a = R.ajustes()
    D.equipo_en_segundo_plano()
    activas = BI.activas()
    filas_km = BI.km_filas()
    cierres = BI.cierres()
    meses_hist = sorted({r['mes'] for r in filas_km} | set(cierres), reverse=True)[:24]
    hist_mes = [{'mes': m, 'txt': f'{m[5:7]}/{m[:4]}', 'cerrado': m in cierres, 'bicis': [sum(r['km'] for r in filas_km if r['mes'] == m and r['bici'] == b['id']) for b in activas]} for m in meses_hist]
    garmin = D.km_garmin_mes(mes)
    mes_km = {(r['bici'], r['rodadura']): f"{r['km']:g}" for r in filas_km if r['mes'] == mes}
    # Mientras el mes no tenga un dato guardado, cada casilla se rellena con los km de las actividades asignadas a esa
    # bici y, la del rodillo (elegida en Ajustes), con los de rodillo sin bici asignada
    rodillo = next((b for b in activas if b['id'] == a['bici_rodillo']), None)
    claves = [(b['id'], j) for b in activas for j in (b['juegos'] or [''])]
    clave_rod = (rodillo['id'], (rodillo['juegos'] or [''])[0]) if rodillo else None
    asig = D.km_asignados_mes(mes)
    fuera = asig['fuera'] + sum(km for c, km in asig['bicis'].items() if c not in claves)
    rodillo_nombre, auto = None, {}
    if mes >= (a['primer_mes_cierre'] or '') and mes not in cierres:
        for c in claves:
            km = asig['bicis'].get(c, 0) + (asig['libre_rod'] if c == clave_rod else 0)
            if c not in mes_km and km >= 0.5:
                mes_km[c] = auto[c] = f'{round(km)}'
                if c == clave_rod and asig['libre_rod']:
                    rodillo_nombre = rodillo['nombre']
    asignadas = [(n, round(asig['bicis'][c])) for b in activas for j in (b['juegos'] or [''])
                 for c, n in [((b['id'], j), b['nombre'] + (', ' + j if j else ''))] if asig['bicis'].get(c, 0) >= 0.5]
    propuesta = {f'{b}|{j}': km for (b, j), km in D.pesos_km_mes(mes, claves, clave_rod).items() if km}
    piezas = BI.piezas()
    return render_template('bicis.html', resumen=BI.resumen(), activas=activas, mes=mes, mes_txt=f'{D.MES[int(mes[5:7]) - 1]} de {mes[:4]}', mes_km=mes_km, garmin=garmin, rodillo_nombre=rodillo_nombre,
                           propuesta=propuesta, salidas=D.salidas_exterior_mes(mes), auto=auto, asignadas=asignadas, fuera=fuera,
                           libre_ext=asig['libre_ext'], opciones_bici=BI.opciones_bici(), equipo=BI.equipo_garmin(), usar_garmin=D.usar_garmin(),
                           garmin_listo=bool(D.usuario_garmin() and D._python_garmindb()), leyendo_equipo=D.leyendo_equipo(), error_equipo=request.args.get('error_equipo'),
                           cerrable=BI.admite_cierre(mes), cerrado=mes in cierres, hist_mes=hist_mes, sin_cerrar=[f'{m[5:7]}/{m[:4]}' for m in BI.sin_cerrar()], dia_inicio=a['cierre_dia_inicio'], dia_fin=a['cierre_dia_fin'],
                           hoy=fecha(hoy), piezas=piezas, nombres={b['id']: b['nombre'] for b in bs}, visitas=BI.VISITAS, desc_temporada=BI.descripcion_temporada(), hay_importados=any(p['origen'] == 'importado' for p in piezas))


def _lista_dientes(txt):
    return [int(x) for x in re.findall(r'\d+', txt or '')]


def _datos_bici():
    nombre = request.form.get('nombre', '').strip()[:60]
    try:
        km_base = leer_km(request.form.get('km_base') or '0')
    except ValueError:
        abort(400)
    if not nombre or not 0 <= km_base <= 1000000:
        abort(400)
    juegos = list(dict.fromkeys(j.strip()[:30] for j in request.form.get('juegos', '').split(',') if j.strip()))
    piezas = request.form.getlist('pieza') + [o.strip()[:60] for o in request.form.get('otras', '').split(',') if o.strip()]
    dientes = _lista_dientes(request.form.get('pinones'))
    return {'nombre': nombre, 'km_base': km_base, 'serie': request.form.get('serie', '').strip()[:40], 'juegos': juegos, 'piezas': list(dict.fromkeys(piezas)),
            'platos': _lista_dientes(request.form.get('platos')), 'pinones': [{'nombre': '', 'dientes': dientes}] if dientes else []}


@app.route('/bicis/nueva', methods=['GET', 'POST'])
def bici_nueva():
    if request.method == 'POST':
        BI.crear_bici(**_datos_bici())
        return redirect(url_for('bicis'))
    return render_template('bici_editar.html', b=None, piezas=R.ajustes()['piezas'], elegidas=[], otras='', pinones='')


@app.route('/bicis/editar/<bid>', methods=['GET', 'POST'])
def bici_editar(bid):
    b = BI.una_bici(bid)
    if not b:
        abort(404)
    if request.method == 'POST':
        d = _datos_bici()
        juegos = list(dict.fromkeys(b['juegos'] + d['juegos']))
        # Lo mostrado como «Cubiertas» agrupa las cubiertas de cada juego
        BI.editar_bici(bid, d['nombre'], d['km_base'], d['serie'], bool(request.form.get('activa')), juegos, d['piezas'], d['platos'],
                       d['pinones'] if len(b['pinones']) <= 1 else b['pinones'])
        return redirect(url_for('bicis'))
    predet = R.ajustes()['piezas']
    nombres = [c['nombre'] for c in b['componentes']]
    grupo = ['Cubiertas'] if any(c.get('rodadura') for c in b['componentes']) else []
    propias = [n for n in nombres if not any(c['nombre'] == n and c.get('rodadura') for c in b['componentes'])]
    otras = ', '.join(n for n in propias if n not in predet)
    pin = '-'.join(str(x) for x in b['pinones'][0]['dientes']) if len(b['pinones']) == 1 else ''
    return render_template('bici_editar.html', b=b, piezas=predet, elegidas=propias + grupo, otras=otras, pinones=pin)


@app.post('/bicis/borrar/<bid>')
def bici_borrar(bid):
    try:
        BI.borrar_bici(bid)
    except ValueError:
        abort(409, 'Esta bici tiene historial: desmarca «En uso» para retirarla.')
    return redirect(url_for('bicis'))


# Ajustes numéricos del formulario: (clave, mínimo, máximo)
AJUSTES_NUM = (('mes_inicio_temporada', 1, 12), ('cierre_dia_inicio', 15, 28), ('cierre_dia_fin', 1, 14), ('dias_sin_actividad', 1, 365),
               ('dias_sin_salud', 1, 365), ('dias_sin_peso', 1, 365), ('sensores_pct_aviso', 1, 100), ('sensores_dias_aviso', 1, 60),
               ('km_enlace_garmin', 0, 10000), ('km_aviso_prueba', 50, 2000), ('dias_aviso_prueba', 1, 3650), ('horas_descarga_garmin', 1, 48),
               ('plan_parada_min', 0, 600))
# Lo que «Valores por defecto» devuelve a predeterminados.json (no el calendario, el peso, Garmin ni las bicis)
AJUSTES_DEFECTO = [k for k, _, _ in AJUSTES_NUM if k != 'mes_inicio_temporada'] + ['sueno_referencia_h', 'sensores_vigilar', 'plan_mapa_base',
                                                                                'plan_salidas', 'calendario_defecto_ver']


@app.post('/ajustes/defecto')
def ajustes_defecto():
    R.quitar_ajustes(['plan_parada_min', 'plan_mapa_base', 'plan_salidas'] if RUTAS else AJUSTES_DEFECTO)
    return redirect(url_for('ajustes'))


# ---------- Perfiles de club (VenB Rutas) ----------
@app.post('/clubes/guardar')
def club_guardar():
    request.max_content_length = 30 * 1024 ** 2
    cid = request.form.get('id') or None
    try:
        CL.guardar(cid, request.form.get('nombre'), request.form.get('web'), request.form.get('texto'),
                   request.files.getlist('logos'), request.form.getlist('quitar_logo'))
    except CL.ErrorClub as e:
        return pagina_ajustes(error_club=str(e), club_editar=CL.club(cid) if cid else None)
    except KeyError:
        abort(404)
    return redirect(url_for('ajustes', _anchor='clubes'))


@app.post('/clubes/borrar/<cid>')
def club_borrar(cid):
    try:
        CL.borrar(cid)
    except KeyError:
        abort(404)
    return redirect(url_for('ajustes', _anchor='clubes'))


@app.route('/clubes/<cid>/logo/<nombre>')
def club_logo(cid, nombre):
    try:
        return send_file(CL.ruta_logo(cid, nombre))
    except KeyError:
        abort(404)


@app.route('/ajustes', methods=['GET', 'POST'])
def ajustes():
    if request.method == 'POST':
        cambios = {}
        try:
            for k, lo, hi in AJUSTES_NUM:
                if k not in request.form:     # apartado que no está en esta edición (VenB Rutas)
                    continue
                v = int(request.form[k])
                if not lo <= v <= hi:
                    abort(400)
                cambios[k] = v
            if 'sueno_referencia_h' in request.form:
                v = float(request.form['sueno_referencia_h'].replace(',', '.'))
                if not 1 <= v <= 12:
                    abort(400)
                cambios['sueno_referencia_h'] = v
        except (KeyError, ValueError):
            abort(400)
        cambios['plan_salidas'] = [k for k in request.form.getlist('plan_salidas') if k in PL.SALIDAS]
        base = request.form.get('plan_mapa_base', 'ign_mtn')
        if base not in PL.ESTILOS_INFOGRAFIA:
            abort(400)
        cambios['plan_mapa_base'] = base
        if not RUTAS:     # VenB Rutas solo tiene los apartados del Planificador (los ajustes se comparten con VenB)
            cambios['sensores_vigilar'] = [k for k in request.form.getlist('sensores_vigilar') if k in D.SENSORES]
            rod = request.form.get('bici_rodillo', '')
            if rod and not BI.una_bici(rod):
                abort(400)
            cambios['bici_rodillo'] = rod
            cambios['rodillo_manda'] = bool(request.form.get('rodillo_manda'))
            cambios['calendario_defecto_ver'] = bool(request.form.get('calendario_defecto_ver'))
        R.guardar_ajustes(cambios)
        url = request.form.get('calendario_url', '').strip()
        if url and not url.startswith('https://'):
            abort(400, 'La dirección del calendario debe empezar por https://')
        if url or request.form.get('calendario_quitar'):
            D.guardar_calendario(url)
        origen = request.form.get('origen_peso')  # no llega si garmindb no está configurado
        if origen not in (None, 'mano', 'garmin'):
            abort(400)
        if origen and not D.elegir_peso_desde_garmin(origen == 'garmin'):
            return redirect(url_for('ajustes', error_peso=1))
        return redirect(url_for('ajustes'))
    if RUTAS and request.args.get('club'):
        return pagina_ajustes(club_editar=CL.club(request.args['club']))
    return pagina_ajustes()


def pagina_ajustes(**extra):
    # el mensaje de un apartado de abajo no se vería al recargar la página: se salta a ese apartado
    saltar = next((s for claves, s in ((('error_club', 'club_editar'), 'clubes'), (('error_garmin', 'ok_garmin'), 'garmin'), (('error_copia', 'importado'), 'copia'), (('error_red',), 'red'))
                   if any(extra.get(k) for k in claves)), '')
    return render_template('ajustes.html', saltar=saltar, a=R.ajustes(), meses=[m.capitalize() for m in D.MES], bicis=BI.activas(), conectado=D.calendario_propio(),
                           garmindb=D.garmindb_configurado(), peso_garmin=D.peso_desde_garmin(), error_peso=request.args.get('error_peso'),
                           instalado=D._python_garmindb() is not None, usuario_garmin=D.usuario_garmin(), descarga=D.estado_descarga(), usar_garmin=D.usar_garmin(),
                           red=pagina_red(), sensores=D.SENSORES, estilos_infografia=PL.ESTILOS_INFOGRAFIA, salidas_plan=PL.SALIDAS,
                           clubes=CL.lista() if RUTAS else [], **extra)


def pagina_red():
    """Lo abierto ahora (al arrancar) y lo pedido en Ajustes pueden diferir hasta reiniciar VenB."""
    pedido = RED.activada()
    return {'pedido': bool(R.ajustes().get('red_local')), 'tiene_clave': RED.tiene_clave(), 'abierta': ESCUCHA == '0.0.0.0',
            'reiniciar': pedido != (ESCUCHA == '0.0.0.0'), 'direccion': RED.direccion(PUERTO), 'min': RED.MIN_CLAVE}


@app.post('/ajustes/red')
def red_ajustes():
    activar = request.form.get('red_local') == 'si'
    clave = request.form.get('clave', '')
    if clave or (activar and not RED.tiene_clave()):
        try:
            RED.guardar_clave(clave)
        except ValueError as e:
            return pagina_ajustes(error_red=str(e))
    R.guardar_ajustes({'red_local': activar})
    return redirect(url_for('ajustes', _anchor='red'))


@app.route('/garmin/cuenta', methods=['POST'])
def garmin_cuenta():
    usuario = request.form.get('usuario', '').strip()
    clave = request.form.get('clave', '')
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', usuario) or len(usuario) > 200 or len(clave) > 200:
        return pagina_ajustes(error_garmin='Escribe el correo con el que entras en Garmin Connect.')
    try:
        D.guardar_credenciales_garmin(usuario, clave)
    except ValueError as e:
        return pagina_ajustes(error_garmin=str(e))
    error, nombre = D.probar_garmin()
    if error:
        return pagina_ajustes(error_garmin=f'Datos guardados, pero no se ha podido conectar: {error}')
    return pagina_ajustes(ok_garmin=f'Conectado a Garmin Connect{" como " + nombre if nombre else ""}.')


@app.route('/garmin/probar', methods=['POST'])
def garmin_probar():
    error, nombre = D.probar_garmin()
    if error:
        return pagina_ajustes(error_garmin=error)
    return pagina_ajustes(ok_garmin=f'Conectado a Garmin Connect{" como " + nombre if nombre else ""}.')


@app.route('/garmin/descargar', methods=['POST'])
def garmin_descargar():
    error = D.descargar_todo()
    return pagina_ajustes(error_garmin=error) if error else redirect(url_for('ajustes', _anchor='garmin'))


@app.route('/copia/exportar', methods=['POST'])
def copia_exportar():
    carpeta = tempfile.mkdtemp(prefix='venb-copia-')
    ruta = CO.exportar(carpeta)

    @after_this_request
    def limpiar(r):
        r.call_on_close(lambda: shutil.rmtree(carpeta, ignore_errors=True))
        return r
    return send_file(ruta, as_attachment=True, download_name=os.path.basename(ruta), mimetype='application/zip')


@app.route('/copia/importar', methods=['POST'])
def copia_importar():
    request.max_content_length = 8 * 1024 ** 3  # una exportación de Garmin puede ocupar varios GB
    f = request.files.get('zip')
    if not f or not f.filename:
        return pagina_ajustes(error_copia='Elige un fichero ZIP.')
    with tempfile.TemporaryDirectory(prefix='venb-importar-') as d:
        ruta = os.path.join(d, 'subido.zip')
        f.save(ruta)
        try:
            r = CO.importar(ruta)
        except CO.ErrorCopia as e:
            return pagina_ajustes(error_copia=str(e))
    D._cache.clear()
    return pagina_ajustes(importado=r)


@app.route('/datos/bicis.json')
def datos_bicis():
    return jsonify(BI.series())


@app.post('/bicis/mes')
def bicis_mes():
    mes = request.form.get('mes', '')
    try:
        datetime.strptime(mes, '%Y-%m')
    except ValueError:
        abort(400)
    for b in BI.activas():
        for i, rod in enumerate(b['juegos'] or ['']):
            v = request.form.get(f"km|{b['id']}|{i if b['juegos'] else ''}")
            if v is None:
                continue
            if not v.strip():  # vaciar la casilla elimina el dato
                BI.borrar_km(mes, b['id'], rod)
                continue
            try:
                km = leer_km(v)
            except ValueError:
                abort(400)
            if not 0 <= km <= 20000:
                abort(400)
            BI.anotar_km(mes, b['id'], km, rod)
    if BI.admite_cierre(mes):
        BI.cerrar_mes(mes)
    return redirect(url_for('bicis', mes=f'{mes[5:7]}/{mes[:4]}'))


@app.post('/bicis/pieza')
def bicis_pieza():
    try:
        f = leer_fecha(request.form['fecha'])
        bici = request.form['bici']
    except (KeyError, ValueError):
        abort(400)
    if bici not in {b['id'] for b in BI.cargar_bicis()} or f > date.today():
        abort(400)
    trabajos = request.form.getlist('pieza')
    otra = request.form.get('otra', '').strip()[:120]
    if otra:
        trabajos.append(otra)
    if not trabajos:
        abort(400)
    visita = request.form.get('visita', '')
    for t in trabajos:
        BI.anotar_pieza(f.isoformat(), bici, t[:120], visita if visita in BI.VISITAS else '', request.form.get('taller', '').strip()[:80],
                        request.form.get('coste', '').strip()[:12], request.form.get('notas', '').strip()[:300])
    return redirect(url_for('bicis'))


@app.route('/bicis/pieza/editar/<pid>', methods=['GET', 'POST'])
def bicis_pieza_editar(pid):
    p = BI.una_pieza(pid)
    if not p:
        abort(404)
    if request.method == 'POST':
        try:
            f = leer_fecha(request.form['fecha'])
            bici = request.form.get('bici', '')
            pieza = request.form['pieza'].strip()[:120]
        except (KeyError, ValueError):
            abort(400)
        if not pieza or f > date.today() or (bici and bici not in {b['id'] for b in BI.cargar_bicis()}):
            abort(400)
        BI.editar_pieza(pid, fecha=f.isoformat(), bici=bici, pieza=pieza, visita=request.form.get('visita', '') if request.form.get('visita', '') in BI.VISITAS else '',
                        taller=request.form.get('taller', '').strip()[:80], coste=request.form.get('coste', '').strip()[:12], notas=request.form.get('notas', '').strip()[:300])
        return redirect(url_for('bicis'))
    bs = BI.cargar_bicis()
    lista = []
    for b in bs:
        lista += [c['nombre'] for c in b.get('componentes', []) if c['nombre'] not in lista]
    return render_template('pieza_editar.html', p=p, fecha=fecha(date.fromisoformat(p['fecha'])), bicis=[b for b in bs if b.get('componentes')], visitas=BI.VISITAS, lista_piezas=lista)


@app.route('/brevets')
def brevets():
    filas = BR.todos()
    e = next((b for b in filas if b['id'] == request.args.get('editar')), None)
    if e:
        e = {**e, 'fecha_txt': iso_fecha(e['fecha']) if e['fecha'] else '', 'tiempo_txt': BR.formato_tiempo(e['horas'])}
    aviso = None
    if request.args.get('duplicado'):
        b = next((x for x in filas if x['id'] == request.args['duplicado']), None)
        if b:
            aviso = f"No se ha guardado nada: ya está registrado «{b['nombre'] or b['tipo']}» del {iso_fecha(b['fecha'])} ({b['distancia']:g} km), con la misma actividad o la misma fecha y distancia. Si es otra prueba, cambia la fecha o la distancia; si quieres corregir la existente, pulsa su «Editar»."
    if e:
        pass
    elif request.args.get('actividad'):  # desde el aviso de Inicio o el Histórico: la prueba se rellena con la actividad
        h = D.historico()
        a = h[h.id.astype(str) == request.args['actividad']] if len(h) else h
        ya = BR.brevet_de_actividad(request.args['actividad'], h) if len(a) else None
        if ya:
            aviso = f"Esta actividad ya está en la lista de brevets: «{ya['nombre'] or ya['tipo']}» del {iso_fecha(ya['fecha'])} ({ya['distancia']:g} km), o es una etapa suya. No se ha añadido nada."
            a = a.iloc[0:0]
        if len(a):
            a = a.iloc[0]
            e = {'id': '', 'actividad': str(a.id), 'fecha_txt': fecha(a.fecha.date()), 'tipo': 'BRM', 'nombre': a.titulo, 'distancia': BR.distancia_nominal(float(a.km)), 'km_reales': float(a.km),
                 'tiempo_txt': BR.formato_tiempo(float(a.h_total if pd.notna(a.h_total) else a.h)), 'homologacion': '', 'organizador': '', 'inscripcion': '', 'r5000': '', 'r10000': ''}
    clubes = sorted({c for b in filas for c in (b['organizador'], b['inscripcion']) if c})
    try:
        hist = D.historico()
        enlaces = {k: BR.URL_GARMIN.format(v) for k, v in BR.actividades(filas, hist).items() if str(v).isdigit()}
    except Exception:  # sin historial de Garmin, la tabla se ve igual, sin enlaces
        hist, enlaces = None, {}
    from generador.datos import LIMITES_BRM
    # % del tiempo límite oficial (RM) empleado, para el filtro «Tiempo»; solo con distancia de BRM y tiempo anotado
    pct = {b['id']: round(100 * b['horas'] / LIMITES_BRM[int(b['distancia'])]) for b in filas
           if b['horas'] and b['distancia'] and int(b['distancia']) in LIMITES_BRM and b['distancia'] == int(b['distancia'])}
    return render_template('brevets.html', filas=filas, st=BR.estadisticas(hist), e=e, enlaces=enlaces, aviso=aviso, tipos=R.ajustes()['tipos_brevet'], clubes=clubes, hoy=fecha(date.today()),
                           pct=pct, tramos=R.ajustes()['tramos_brevet'],
                           organizadores=sorted({b['organizador'] for b in filas if b['organizador']}), inscripciones=sorted({b['inscripcion'] for b in filas if b['inscripcion']}),
                           tipos_hechos=sorted({b['tipo'] for b in filas if b['tipo']}),
                           temporadas=sorted({int(str(b['fecha'])[:4]) + (str(b['fecha'])[5:7] >= '11') for b in filas if b['fecha']}, reverse=True), anios=sorted({str(b['fecha'])[:4] for b in filas if b['fecha']}, reverse=True))


@app.route('/datos/brevets.json')
def datos_brevets():
    st = BR.estadisticas() or {'anios': [], 'series': []}
    return jsonify({'anios': st['anios'], 'series': st['series']})


@app.post('/brevets/guardar')
def brevet_guardar():
    try:
        f = leer_fecha(request.form['fecha'])
        distancia = leer_km(request.form['distancia'])
        horas = BR.leer_tiempo(request.form.get('tiempo', ''))
    except (KeyError, ValueError):
        abort(400)
    tipo = request.form.get('tipo', 'BRM')
    if tipo not in R.ajustes()['tipos_brevet'] or not 0 < distancia <= 10000:
        abort(400)
    datos = {'fecha': f.isoformat(), 'tipo': tipo, 'nombre': request.form.get('nombre', '').strip()[:100], 'distancia': distancia, 'homologacion': request.form.get('homologacion', '').strip()[:30],
             'organizador': request.form.get('organizador', '').strip()[:80], 'inscripcion': request.form.get('inscripcion', '').strip()[:80], 'horas': horas, 'r5000': '1' if request.form.get('r5000') else '',
             'r10000': '1' if request.form.get('r10000') else '', 'actividad': re.sub(r'\D', '', request.form.get('actividad', ''))[:20]}
    bid = request.form.get('id') or None
    if bid and not datos['actividad']:  # editar no debe soltar la actividad enlazada
        datos['actividad'] = next((x['actividad'] for x in BR.todos() if x['id'] == bid), '')
    otro = BR.duplicado(datos, bid)
    if otro:  # misma actividad o misma fecha y distancia: se avisa y no se guarda
        return redirect(url_for('brevets', duplicado=otro['id']) + '#aviso-brevet')
    try:
        BR.anotar(datos, bid)
    except KeyError:
        abort(404)
    return redirect(url_for('brevets'))


@app.post('/brevets/borrar/<bid>')
def brevet_borrar(bid):
    BR.borrar(bid)
    return redirect(url_for('brevets'))


@app.route('/brevets/por-clasificar')
def brevets_por_clasificar():
    """Todas las salidas largas sin prueba registrada ni marca «No es prueba», sin límite de días."""
    km = R.ajustes().get('km_aviso_prueba', 190)
    h = D.historico()
    return render_template('por_clasificar.html', km=km, filas=BR.sin_registrar(h, km), marcadas=BR.sin_registrar(h, km, marcadas=True),
                           url_garmin=BR.URL_GARMIN)


def _volver_seguro(defecto):
    v = request.form.get('volver', '')
    return v if v.startswith('/') and not v.startswith('//') else defecto


@app.post('/brevets/no-prueba')
def brevets_no_prueba():
    """Marca «No es prueba»: una (id), varias (ids) o todas las que quedan por clasificar (todas=1)."""
    if request.form.get('todas'):
        km = R.ajustes().get('km_aviso_prueba', 190)
        ids = [str(a.id) for a in BR.sin_registrar(D.historico(), km)]
    else:
        ids = [i for i in request.form.getlist('id') if i]
    if not ids:
        abort(400)
    BR.marcar_no_prueba(ids)
    return redirect(_volver_seguro(url_for('brevets_por_clasificar')))


@app.post('/brevets/recuperar')
def brevets_recuperar():
    aid = request.form.get('id', '')
    if not aid:
        abort(400)
    BR.recuperar(aid)
    return redirect(url_for('brevets_por_clasificar') + '#marcadas')


@app.post('/bicis/pieza/borrar/<pid>')
def bicis_pieza_borrar(pid):
    BI.borrar_pieza(pid)
    return redirect(url_for('bicis'))


@app.route('/planificador')
def planificador():
    if RUTAS:       # en VenB Rutas no hay Inicio: el aviso de versión nueva va aquí
        AC.en_segundo_plano()
    return render_template('planificador.html', planes=PL.lista(), error=request.args.get('error'), ext_hoja=', '.join(PL.EXT_HOJA), reglas=PL.reglas_rm())


@app.post('/planificador/nuevo')
def plan_nuevo():
    request.max_content_length = 100 * 1024 ** 2  # GPX de rutas largas y hojas en PDF
    gpx, hoja = request.files.get('gpx'), request.files.get('hoja')
    if not gpx or not gpx.filename:
        return redirect(url_for('planificador', error='Elige el track GPX.'))
    try:
        pid = PL.crear(gpx, hoja)
    except PL.ErrorPlan as e:
        return redirect(url_for('planificador', error=str(e)))
    return redirect(url_for('plan_ver', pid=pid))


def _plan(pid):
    try:
        return PL.estado(pid)
    except KeyError:
        abort(404)


@app.route('/planificador/<pid>')
def plan_ver(pid):
    e = _plan(pid)
    PL.asegurar_gpx(pid)
    return render_template('plan.html', e=e, a=PL.analisis(pid), p=PL.parametros(pid), ficheros=PL.ficheros(pid), documentos=PL.documentos(pid), reciente=PL.velocidad_reciente(),
                           reglas=PL.reglas_rm(), modalidades=PL.MODALIDADES, salidas=PL.SALIDAS, tipos=PL.TIPOS_PARADA, paletas=PL.PALETAS, estilos=PL.ESTILOS_INFOGRAFIA, aj=R.ajustes(),
                           clubes=CL.lista() if RUTAS else [])


@app.route('/planificador/<pid>/estado.json')
def plan_estado(pid):
    e = _plan(pid)
    return jsonify({k: e.get(k) for k in ('fase', 'error', 'registro', 'nombre')})


@app.post('/planificador/<pid>/generar')
def plan_generar(pid):
    _plan(pid)
    request.max_content_length = 2 * 1024 ** 2
    try:
        PL.generar(pid, request.get_json(force=True, silent=True) or {})
    except PL.ErrorPlan as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@app.post('/planificador/<pid>/puntos')
def plan_puntos(pid):
    _plan(pid)
    request.max_content_length = 2 * 1024 ** 2
    try:
        PL.editar_puntos(pid, request.get_json(force=True, silent=True) or {})
    except PL.ErrorPlan as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@app.post('/planificador/<pid>/puntos/hoja')
def plan_puntos_hoja(pid):
    _plan(pid)
    try:
        PL.quitar_edicion(pid)
    except PL.ErrorPlan as e:
        return redirect(url_for('plan_ver', pid=pid, error=str(e)))
    return redirect(url_for('plan_ver', pid=pid))


@app.route('/planificador/<pid>/f/<nombre>')
def plan_fichero(pid, nombre):
    _plan(pid)
    try:
        ruta = PL.fichero(pid, nombre)
    except KeyError:
        abort(404)
    return send_file(ruta, as_attachment=request.args.get('descargar') == '1' or nombre.endswith('.xlsx'))


@app.route('/planificador/<pid>/zip')
def plan_zip(pid):
    _plan(pid)
    if not PL.ficheros(pid):
        abort(404)
    ruta = PL.zip_salida(pid)
    return send_file(ruta, as_attachment=True, download_name=os.path.basename(ruta), mimetype='application/zip')


@app.post('/planificador/<pid>/borrar')
def plan_borrar(pid):
    _plan(pid)
    try:
        PL.borrar(pid)
    except PL.ErrorPlan as e:
        return redirect(url_for('planificador', error=str(e)))
    return redirect(url_for('planificador'))


@app.route('/ayuda', defaults={'capitulo': 'manual'})
@app.route('/ayuda/<capitulo>')
def ayuda(capitulo):
    """El manual está en venb/manual/, en Markdown, para poder leerlo también fuera de la aplicación."""
    if capitulo not in ('manual', 'garmin'):
        abort(404)
    if RUTAS and capitulo != 'manual':
        abort(404)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'manual', f'{capitulo}.md'), encoding='utf-8') as f:
        texto = f.read()
    if RUTAS:     # VenB Rutas: solo el capítulo del Planificador, como página propia
        i = texto.index('\n## Planificador')
        j = texto.find('\n## ', i + 5)
        texto = '# Manual del Planificador de VenB Rutas\n' + texto[i:j if j > 0 else None].replace('\n## Planificador', '', 1)
        texto = re.sub(r'\[([^\]]+)\]\((?:garmin\.md|manual\.md)?#[^)]*\)', r'\1', texto)   # enlaces a otros capítulos: solo el texto
    md = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc'], extension_configs={'toc': {'toc_depth': '2-2'}})
    html = md.convert(texto)
    html = html.replace('href="garmin.md', 'href="' + url_for('ayuda', capitulo='garmin')).replace('href="manual.md', 'href="' + url_for('ayuda'))
    html = html.replace('<table>', '<div class="tabla"><table>').replace('</table>', '</table></div>')
    html = html.replace('src="img/', 'src="' + url_for('ayuda_imagen', nombre=''))   # capturas de venb/manual/img/
    # cada captura con su texto como pie, igual que en el manual en PDF
    html = re.sub(r'<p><img alt="([^"]*)" (src="[^"]+")\s*/?></p>', r'<figure><img alt="\1" \2><figcaption>\1</figcaption></figure>', html)
    return render_template('ayuda.html', contenido=html, indice=md.toc if capitulo == 'manual' else '')


@app.route('/ayuda/img/<nombre>')
def ayuda_imagen(nombre):
    return send_from_directory(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'manual', 'img'), nombre)


@app.route('/acerca')
def acerca():
    return render_template('acerca.html', act=AC.estado(), fecha_hora=lambda t: datetime.fromtimestamp(t).strftime('%d/%m/%Y %H:%M'))


if __name__ == '__main__':
    app.run(host=ESCUCHA, port=PUERTO, debug=False)
