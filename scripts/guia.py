"""Guías rápidas de instalación y actualización (una página por edición): Instalar_VenB-X.YZ.pdf e
Instalar_VenB_Rutas-X.YZ.pdf. Lo imprescindible para instalar de cero o actualizar; los detalles (Python paso a paso,
problemas, cada página) están en el manual de usuario y en la Ayuda, y aquí solo se remite a ellos.
HTML maquetado con Chrome sin ventana (google-chrome o chromium). Lo llama empaquetar.py; también a mano:
    python scripts/guia.py X.YZ [carpeta_de_salida]
Fuera del ZIP (export-ignore).
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import base64
import os
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESCARGAS = 'github.com/jj99211/VenB/releases/latest'
CORREO = 'jj99211@gmail.com'

ESTILO = '''
@page { size: A4; margin: 14mm 16mm 12mm; }
body { font-family: "Liberation Sans", Arial, sans-serif; font-size: 10.3pt; color: #000; line-height: 1.38; margin: 0; }
.cab { display: flex; align-items: center; gap: 12px; border-bottom: 2px solid #000; padding-bottom: 7px; margin-bottom: 9px; }
.cab img { width: 52px; height: auto; }
h1 { font-size: 17pt; margin: 0; }
.sub { color: #444; font-size: 9.5pt; margin-top: 2px; }
h2 { font-size: 11.2pt; margin: 11px 0 4px; padding: 2px 0 2px 7px; border-left: 4px solid #000; background: #eee; }
p { margin: 4px 0; }
ol, ul { margin: 3px 0; padding-left: 21px; }
li { margin: 2px 0; }
code { font-family: "Liberation Mono", monospace; font-size: 9.2pt; background: #eee; padding: 0 3px; }
.pie { border-top: 1px solid #999; margin-top: 12px; padding-top: 5px; font-size: 8.5pt; color: #444; text-align: center; }
'''

COMUN_INSTALAR = '''
<h2>1. Qué necesitas</h2>
<ul>
<li><b>Windows 10 u 11</b> o <b>Linux</b>, con conexión a internet durante la instalación.</li>
<li><b>Python 3.10 o posterior</b>. El instalador lo comprueba: si falta, en Windows ofrece instalarlo (responde <b>S</b>)
y en Linux te da la orden exacta. Si se complica, el manual de usuario de la página de descargas lo explica paso a paso («Antes de instalar: Python»).</li>
</ul>
<h2>2. Descargar e instalar</h2>
<ol>
<li>Entra en <b>{descargas}</b> y descarga <code>{zip}</code> (no el «Source code»).</li>
<li><b>Descomprímelo</b>, por ejemplo en Descargas. En Windows: botón derecho → <b>«Extraer todo»</b>.</li>
<li>Ejecuta el instalador: doble clic en <code>INSTALAR-EN-WINDOWS</code> (Windows) o, en una terminal abierta en esa
carpeta, <code>bash instalar-en-linux.sh</code> (Linux). La primera vez propone instalar en <code>Documentos\\VenB</code>
o <code>~/VenB</code>: pulsa <b>Intro</b>.</li>
<li>Se crea el icono <b>«{nombre}»</b> en el escritorio. La carpeta descomprimida y el ZIP ya se pueden borrar.</li>
</ol>
'''

COMUN_FINAL = '''
<h2>{n}. Actualizaciones</h2>
<ul>
<li>Cuando hay una versión nueva, {nombre} lo avisa en <b>{donde}</b>. Pulsa <b>«Actualizar ahora»</b>: se descarga,
se instala y se vuelve a abrir sola. <b>Tus datos no se tocan</b> (están en la carpeta <code>VenB-datos</code>).</li>
<li><b>Si tienes la versión 3.39 o anterior</b>, que no tiene ese botón: instala esta versión una vez como en el
apartado 2. El instalador encuentra tu instalación y tus datos.</li>
</ul>
<h2>{n2}. Copia de seguridad y ayuda</h2>
<ul>
<li><b>Ajustes → Copia de seguridad → Exportar</b> guarda tus datos en un fichero. Guárdalo fuera del ordenador de vez en cuando.</li>
<li>La página <b>Ayuda</b> de la aplicación explica cada pantalla; el manual completo está en la misma página de descargas.</li>
<li>Dudas o errores: <b>{correo}</b> (indica tu sistema, la versión y, si puedes, una captura de la terminal).</li>
</ul>
'''

EDICIONES = {
    'normal': {
        'fichero': 'Instalar_VenB-{v}.pdf', 'nombre': 'VenB', 'zip': 'VenB-{v}.zip', 'donde': 'Inicio', 'puerto': 8877,
        'sub': 'Vivir en Bici · entrenamiento, bicis, brevets, calendario y planificador de rutas · Windows y Linux',
        'intro': 'VenB funciona en tu ordenador: se abre en el navegador y tus datos no salen de él. '
                 'Para clubes y organizadores que solo necesitan el Planificador existe <b>VenB Rutas</b> (<code>VenB-{v}-Rutas.zip</code>).',
        'uso': '''
<h2>3. Primeros pasos</h2>
<ol>
<li>Abre VenB con su icono. <b>No cierres la ventana de la terminal</b> mientras la uses; para terminar, botón <b>«Cerrar VenB»</b>.</li>
<li>En <b>Ajustes</b>, indica el mes en que empieza tu temporada. En <b>Análisis → Bicis</b>, da de alta tus bicis.</li>
<li>Trae tus actividades: desde Garmin Connect (<b>Ajustes → Cuenta de Garmin</b>, y <b>«Descargar todo ahora»</b>) o
subiendo ficheros GPX, FIT o TCX en <b>Análisis → Importar</b>.</li>
</ol>'''},
    'rutas': {
        'fichero': 'Instalar_VenB_Rutas-{v}.pdf', 'nombre': 'VenB Rutas', 'zip': 'VenB-{v}-Rutas.zip', 'donde': 'el Planificador', 'puerto': 8878,
        'sub': 'Planificador de rutas para clubes y organizadores · Windows y Linux',
        'intro': 'A partir del track y la hoja de ruta de una prueba, VenB Rutas calcula los horarios de paso y los cierres '
                 'de cada control y genera la tabla de tiempos, infografías, mapas, una página interactiva y el GPX con '
                 'waypoints, con la marca de tu club. Si ya tienes VenB completo, se instala a su lado y comparten los datos.',
        'uso': '''
<h2>3. Primeros pasos</h2>
<ol>
<li>Abre VenB Rutas con su icono. <b>No cierres la ventana de la terminal</b> mientras la uses; para terminar, botón <b>«Cerrar VenB»</b>.</li>
<li>En <b>Ajustes → Perfiles de club u organizador</b>, crea el de tu club con su nombre, su web y sus logotipos (mejor PNG con fondo transparente).</li>
<li>En <b>Planificador</b>, sube el track y la hoja de ruta, revisa puntos y tiempos, elige el club y pulsa <b>Generar</b>.
La primera vez en una zona nueva tarda de 10 a 15 minutos (descarga mapas); después, segundos.</li>
</ol>'''},
}


def html(edicion, version):
    e = EDICIONES[edicion]
    v = version
    with open(os.path.join(RAIZ, 'venb', 'static', 'logo.png'), 'rb') as f:
        logo = base64.b64encode(f.read()).decode()
    cuerpo = (COMUN_INSTALAR.format(descargas=DESCARGAS, zip=e['zip'].format(v=v), nombre=e['nombre'])
              + e['uso'] + COMUN_FINAL.format(n=4, n2=5, nombre=e['nombre'], donde=e['donde'], correo=CORREO))
    return f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>{e['nombre']} {v} · Instalación</title>
<style>{ESTILO}</style></head><body>
<div class="cab"><img src="data:image/png;base64,{logo}" alt=""><div><h1>{e['nombre']} {v} · Guía rápida de instalación</h1>
<div class="sub">{e['sub']}</div></div></div>
<p>{e['intro'].format(v=v)}</p>
{cuerpo}
<div class="pie">{e['nombre']} © José A. Jiménez · www.vivirenbici.es · Licencia CC BY-NC-SA 4.0 · Abre en el navegador en http://127.0.0.1:{e['puerto']}</div>
</body></html>'''


def navegador():
    for n in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'):
        if shutil.which(n):
            return shutil.which(n)
    sys.exit('Hace falta Google Chrome o Chromium para maquetar las guías.')


def generar(version, salida):
    """Crea las dos guías en salida y devuelve sus rutas."""
    hechas = []
    with tempfile.TemporaryDirectory(prefix='venb_guia_') as tmp:
        for ed, e in EDICIONES.items():
            h = os.path.join(tmp, f'{ed}.html')
            with open(h, 'w', encoding='utf-8') as f:
                f.write(html(ed, version))
            pdf = os.path.join(os.path.abspath(salida), e['fichero'].format(v=version))
            subprocess.run([navegador(), '--headless=new', '--disable-gpu', '--no-sandbox', f'--user-data-dir={tmp}/perfil',
                            '--no-pdf-header-footer', f'--print-to-pdf={pdf}', f'file://{h}'],
                           check=True, capture_output=True, timeout=120)
            hechas.append(pdf)
    for f in os.listdir(salida):   # guías de versiones anteriores
        if f.startswith(('Instalar_VenB-', 'Instalar_VenB_Rutas-')) and f.endswith(('.pdf', '.odt')) \
                and os.path.join(os.path.abspath(salida), f) not in hechas:
            os.remove(os.path.join(salida, f))
    return hechas


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    for r in generar(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else os.path.dirname(RAIZ)):
        print(r)
