"""Manual de usuario de VenB en ODT y PDF, con el mismo texto e imágenes que la Ayuda de la aplicación
(venb/manual/manual.md, garmin.md e img/). Lo llama empaquetar.py en cada versión, que además borra los manuales
de versiones anteriores; también a mano:
    python scripts/manual.py X.YZ [carpeta_de_salida]
Portada con el logotipo y sin encabezado ni pie; índice en la página 2; desde ella, encabezado («Vivir en bici»,
la web enlazada y el logotipo) y pie (autor y correo enlazado, de manual_autor y manual_correo en
VenB-datos/config/ajustes.json, y Pág/Total). Los capítulos van seguidos; los títulos no quedan al pie de una página.
Tras maquetar se revisa el PDF: si una captura salta de página dejando mucho blanco en la anterior, se desplaza tras
el párrafo siguiente (sin salir de su apartado) para que el texto llene el hueco y, si no se puede, se reduce para que
quepa allí; después se maqueta de nuevo.
La maquetación la hace LibreOffice por UNO, con el Python del sistema (paquete python3-uno): este mismo fichero se
relanza con /usr/bin/python3 --uno."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL = os.path.join(RAIZ, 'venb', 'manual')
LOGO = os.path.join(RAIZ, 'venb', 'static', 'logo.png')
WEB = 'https://www.vivirenbici.es'
MARCADOR_INDICE = '%%INDICE%%'
# documentos: título de portada, nombre del fichero ({v}: versión) y fuentes; solo el manual lleva índice
DOCUMENTOS = {
    'usuario': {'titulo': 'Manual de usuario', 'fichero': 'Manual_VenB-{v}', 'fuentes': ['manual.md', 'garmin.md'], 'indice': True},
    # guías cortas de instalación y actualización, una por edición (se publican con cada versión en GitHub)
    'instalar': {'titulo': 'Instalar y actualizar VenB', 'fichero': 'Instalar_VenB-{v}', 'fuentes': ['instalar.md'], 'indice': False},
    'instalar_rutas': {'titulo': 'Instalar y actualizar VenB Rutas', 'fichero': 'Instalar_VenB_Rutas-{v}', 'fuentes': ['instalar_rutas.md'], 'indice': False},
}
ANCHO_IMG = {'infografia.jpg': 470}     # px a 96 ppp en el HTML; el resto, 640 (16,9 cm)
ANCHO_CM = {'infografia.jpg': 12000}   # ancho final en el documento (1/100 mm); el resto, 16,5 cm
ALTO_MAX = 21000                       # ninguna imagen pasa de 21 cm de alto
# Análisis del PDF (puntos; A4 = 595 × 842): cuerpo de la página entre el pie y el encabezado
CUERPO_ABAJO, CUERPO_ARRIBA = 70, 765
HUECO_MIN = 110          # blanco (pt) al pie de una página a partir del cual se recoloca la captura siguiente
REDUCCION_MAX = 0.45     # una captura no se reduce por debajo de esta fracción de su alto
PT = 35.278              # 1/100 mm por punto


# ------------------------------------------------------------------ 1. HTML (Python de VenB, con markdown)

def _listas(t):
    """Línea en blanco antes de un elemento de lista que sigue a texto sangrado o de una sublista (por si acaso)."""
    salida = []
    for l in t.split('\n'):
        ant = salida[-1] if salida else ''
        if ant.strip() and ((re.match(r'^\d+\. ', l) and ant.startswith('    ')) or (re.match(r'^    - ', l) and re.match(r'^\d+\. ', ant))):
            salida.append('')
        salida.append(l)
    return '\n'.join(salida)


def _bloques(h):
    """Divide el HTML en sus elementos de primer nivel (párrafos, listas, tablas, títulos…)."""
    from html.parser import HTMLParser
    VACIOS = {'br', 'img', 'hr', 'input', 'meta'}

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.nivel, self.cortes = 0, []

        def _pos(self):
            linea, col = self.getpos()
            return sum(len(l) for l in lineas[:linea - 1]) + col

        def handle_starttag(self, tag, attrs):
            if tag in VACIOS:
                return
            if self.nivel == 0:
                self.cortes.append(self._pos())
            self.nivel += 1

        def handle_endtag(self, tag):
            if tag not in VACIOS:
                self.nivel -= 1
    lineas = h.splitlines(keepends=True)
    p = P()
    p.feed(h)
    cortes = p.cortes + [len(h)]
    return [h[a:b].strip() for a, b in zip(cortes, cortes[1:]) if h[a:b].strip()]


def html(version, fecha, carpeta, desplazar=None, doc='usuario'):
    """Escribe manual.html (con img/ y logo.png al lado). desplazar: {imagen: nº de bloques que se mueve hacia abajo}.
    Devuelve (ruta, imágenes en orden, títulos de capítulo, {imagen: máximo que se puede desplazar})."""
    import markdown
    desplazar = desplazar or {}

    def conv(t):
        return markdown.Markdown(extensions=['tables', 'fenced_code', 'toc', 'sane_lists']).convert(_listas(t))
    d = DOCUMENTOS[doc]
    man, *otros = (open(os.path.join(MANUAL, f), encoding='utf-8').read() for f in d['fuentes'])
    gar = otros[0] if otros else ''
    # el título del manual va en la portada; lo que hay antes del primer apartado, como «Introducción».
    # ## pasa a capítulo y ### a apartado; el capítulo de Garmin conserva sus niveles
    cuerpo = '## Introducción\n' + man.split('\n', 1)[1]
    cuerpo = re.sub(r'^## ', '\x00# ', cuerpo, flags=re.M)
    cuerpo = re.sub(r'^### ', '## ', cuerpo, flags=re.M).replace('\x00', '')
    gar = re.sub(r'\n\[Volver al manual\]\(manual\.md\)\s*$', '\n', gar)
    h = conv(cuerpo) + (conv(gar) if gar else '')
    h = h.replace('href="garmin.md#', 'href="#').replace('href="garmin.md"', 'href="#importar-tus-datos-de-garmin"').replace('href="manual.md#', 'href="#')
    sueltos = re.findall(r'href="[^"#]*\.md[^"]*"', h)
    if sueltos:
        raise SystemExit(f'Enlaces a ficheros .md sin resolver en el manual: {sueltos}')
    # destinos de los enlaces internos (LibreOffice los convierte en marcadores); la introducción, tras el índice
    h = re.sub(r'<(h[123]) id="([^"]+)">', r'<\1><a name="\2"></a>', h)
    capitulos = [re.sub(r'<[^>]+>', '', t) for t in re.findall(r'<h1>(.*?)</h1>', h)]
    h = h.replace('<h1><a name="introduccion">', '<h1 class="salto"><a name="introduccion">', 1)
    h = h.replace('<table>', '<table border="1" cellpadding="4" cellspacing="0">')
    # imágenes: copiadas junto al HTML, centradas, con su texto alternativo como pie
    os.makedirs(os.path.join(carpeta, 'img'), exist_ok=True)
    imagenes = []

    def img(m):
        texto, nombre = m.group(1), os.path.basename(m.group(2))
        shutil.copy(os.path.join(MANUAL, 'img', nombre), os.path.join(carpeta, 'img', nombre))
        imagenes.append(nombre)
        return (f'<p class="figura"><img src="img/{nombre}" alt="{texto}" width="{ANCHO_IMG.get(nombre, 640)}"></p>'
                f'<p class="pie">{texto}</p>')
    h = re.sub(r'<p><img alt="([^"]*)" src="([^"]+)"\s*/?></p>', img, h)
    # capturas desplazadas hacia abajo, sin pasar de un título (no salen de su apartado)
    bloques = []
    for b in _bloques(h):                          # cada captura con su pie, como una sola unidad
        if b.startswith('<p class="pie">') and bloques and bloques[-1].startswith('<p class="figura">'):
            bloques[-1] += '\n' + b
        else:
            bloques.append(b)
    movibles = {}
    for nombre in imagenes:
        i = next(k for k, b in enumerate(bloques) if f'src="img/{nombre}"' in b)
        figura, resto = bloques[i], bloques[i + 1:]
        libres = next((k for k, b in enumerate(resto) if re.match(r'<h[123]', b)), len(resto))
        movibles[nombre] = libres
        n = min(desplazar.get(nombre, 0), libres)
        bloques = bloques[:i] + resto[:n] + [figura] + resto[n:]
    h = '\n'.join(bloques)
    imagenes = [re.search(r'src="img/([^"]+)"', b).group(1) for b in bloques if b.startswith('<p class="figura">')]
    shutil.copy(LOGO, os.path.join(carpeta, 'logo.png'))
    pagina = f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>{d['titulo']} - VenB {version}</title>
<style>
body {{ font-family: "Liberation Sans"; font-size: 10.5pt; color: #000; }}
h1, h2, h3 {{ font-family: "Liberation Sans"; font-weight: bold; }}
h1 {{ font-size: 16pt; margin-top: 24pt; }}
h1.salto {{ page-break-before: always; margin-top: 0; }}
h2 {{ font-size: 13pt; margin-top: 14pt; }}
h3 {{ font-size: 11pt; margin-top: 10pt; }}
p, li {{ text-align: justify; }}
code, pre {{ font-family: "Liberation Mono"; font-size: 9pt; }}
th, td {{ font-size: 9.5pt; vertical-align: top; }}
p.figura {{ text-align: center; margin-top: 8pt; margin-bottom: 0; }}
p.pie {{ text-align: center; font-size: 9pt; font-style: italic; margin-top: 2pt; }}
p.portada {{ text-align: center; }}
p.titulo-indice {{ page-break-before: always; font-size: 16pt; font-weight: bold; }}
a {{ color: #000; }}
</style></head><body>
<p class="portada" style="margin-top: 70pt;"><img src="logo.png" alt="VenB" width="230"></p>
<p class="portada" style="font-size: 18pt; margin-top: 40pt;">Vivir en bici</p>
<p class="portada" style="font-size: 22pt; font-weight: bold; margin-top: 24pt;">{d['titulo']}</p>
{f'<p class="portada" style="font-size: 14pt; margin-top: 12pt;">{d["subtitulo"]}</p>' if d.get('subtitulo') else ''}
<p class="portada" style="font-size: 12pt; margin-top: 24pt;">{'Versión ' + version + ' · ' if d['indice'] else ''}{fecha}</p>
<p class="portada" style="font-size: 10pt; margin-top: 150pt;"><a href="{WEB}">{WEB}</a><br>Licencia Creative Commons BY-NC-SA 4.0</p>
{f'<p class="titulo-indice">Índice</p>{chr(10)}<p>{MARCADOR_INDICE}</p>' if d['indice'] else ''}
{h}
</body></html>'''
    ruta = os.path.join(carpeta, 'manual.html')
    open(ruta, 'w', encoding='utf-8').write(pagina)
    return ruta, imagenes, capitulos, movibles


# ------------------------------------------------------------------ 2. Maquetación (Python del sistema, con uno)

def maquetar(ruta_html, odt, pdf, autor, correo, limites_json):
    """limites_json: {imagen: alto máximo en 1/100 mm} para las capturas que hay que reducir."""
    import uno
    from com.sun.star.beans import PropertyValue
    from com.sun.star.awt import Size
    from com.sun.star.style import TabStop

    def P(n, v):
        p = PropertyValue()
        p.Name, p.Value = n, v
        return p
    C = uno.getConstantByName
    limites = json.loads(limites_json)
    perfil = tempfile.mkdtemp(prefix='venb_lo_')
    tubo = f'venbmanual{os.getpid()}'
    lo = subprocess.Popen(['soffice', '--headless', '--invisible', '--nologo', '--norestore', '--nodefault',
                           f'-env:UserInstallation={uno.systemPathToFileUrl(perfil)}', f'--accept=pipe,name={tubo};urp;'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    escritorio = None
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver', local)
        for _ in range(120):
            try:
                ctx = resolver.resolve(f'uno:pipe,name={tubo};urp;StarOffice.ComponentContext')
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise SystemExit('No se ha podido arrancar LibreOffice.')
        smgr = ctx.ServiceManager
        escritorio = smgr.createInstanceWithContext('com.sun.star.frame.Desktop', ctx)
        doc = escritorio.loadComponentFromURL(uno.systemPathToFileUrl(ruta_html), '_blank', 0,
                                              (P('FilterName', 'HTML (StarWriter)'), P('Hidden', True)))
        proveedor = smgr.createInstanceWithContext('com.sun.star.graphic.GraphicProvider', ctx)

        def grafico(ruta):
            return proveedor.queryGraphic((P('URL', uno.systemPathToFileUrl(ruta)),))

        # imágenes: incrustadas en el ODT (el HTML solo las enlaza) y a un tamaño que quepa en la página
        # (1/100 mm; la página útil mide 17 cm de ancho), sin deformarlas
        carpeta = os.path.dirname(ruta_html)
        objetos = doc.GraphicObjects
        for i in range(objetos.Count):
            g = objetos.getByIndex(i)
            url = g.Graphic.queryInterface(uno.getTypeByName('com.sun.star.beans.XPropertySet'))
            origen = url.getPropertyValue('OriginURL') if url and url.getPropertySetInfo().hasPropertyByName('OriginURL') else ''
            if not origen.startswith('file://'):
                continue
            ruta = uno.fileUrlToSystemPath(origen)
            g.Graphic = grafico(ruta)
            px = g.Graphic.SizePixel
            nombre = os.path.basename(ruta)
            ancho = 7000 if nombre == 'logo.png' else ANCHO_CM.get(nombre, 16500)
            alto = ancho * px.Height / px.Width
            tope = min(ALTO_MAX, limites.get(nombre, ALTO_MAX))
            if alto > tope:
                ancho, alto = ancho * tope / alto, tope
            t = Size()
            t.Width, t.Height = int(ancho), int(alto)
            g.Size = t
        # párrafos: sin líneas viudas ni huérfanas; títulos y capturas, siempre con lo que les sigue
        par = doc.Text.createEnumeration()
        while par.hasMoreElements():
            p = par.nextElement()
            if not p.supportsService('com.sun.star.text.Paragraph'):
                continue
            p.ParaOrphans = p.ParaWidows = 2
            if p.OutlineLevel:
                p.ParaKeepTogether = True
        for i in range(objetos.Count):           # la captura no se separa de su pie
            try:
                objetos.getByIndex(i).Anchor.ParaKeepTogether = True
            except Exception:
                pass
        # estilos de página: «Portada» sin encabezado ni pie; el resto, A4 con encabezado y pie
        estilos = doc.StyleFamilies.getByName('PageStyles')
        primero = doc.Text.createEnumeration().nextElement()
        base = estilos.getByName(primero.PageStyleName)
        base.Width, base.Height = 21000, 29700
        base.LeftMargin = base.RightMargin = 2000
        base.TopMargin, base.BottomMargin = 1500, 1500
        portada = doc.createInstance('com.sun.star.style.PageStyle')
        estilos.insertByName('Portada', portada)
        for k in ('Width', 'Height', 'LeftMargin', 'RightMargin', 'TopMargin', 'BottomMargin'):
            setattr(portada, k, getattr(base, k))
        portada.HeaderIsOn = portada.FooterIsOn = False
        portada.FollowStyle = base.Name
        primero.PageDescName = 'Portada'
        ancho = base.Width - base.LeftMargin - base.RightMargin
        tab = TabStop()
        tab.Position, tab.Alignment = ancho, uno.Enum('com.sun.star.style.TabAlign', 'RIGHT')
        linea = uno.createUnoStruct('com.sun.star.table.BorderLine2')
        linea.OuterLineWidth, linea.LineWidth, linea.Color = 18, 18, 0x808080

        def enlace(texto, cursor, url, destino):
            """Inserta texto con hiperenlace (en el ODT y en el PDF)."""
            texto.insertString(cursor, destino, False)
            cursor.goLeft(len(destino), True)
            cursor.HyperLinkURL = url
            cursor.collapseToEnd()
            cursor.HyperLinkURL = ''
        # encabezado: «Vivir en bici - web» a la izquierda y el logotipo a la derecha, con una línea debajo
        base.HeaderIsOn = True
        base.HeaderBodyDistance = 400
        t = base.HeaderText
        t.setString('')
        c = t.createTextCursor()
        c.CharFontName, c.CharHeight, c.ParaTabStops = 'Liberation Sans', 9, (tab,)
        c.BottomBorder, c.BottomBorderDistance = linea, 80
        t.insertString(c, 'Vivir en bici - ', False)
        enlace(t, c, WEB, WEB)
        t.insertString(c, '\t', False)
        logo = doc.createInstance('com.sun.star.text.TextGraphicObject')
        logo.Graphic = grafico(os.path.join(carpeta, 'logo.png'))
        logo.AnchorType = uno.Enum('com.sun.star.text.TextContentAnchorType', 'AS_CHARACTER')
        tam = Size()
        tam.Width = tam.Height = 1000
        logo.Size = tam
        logo.VertOrient = C('com.sun.star.text.VertOrientation.LINE_CENTER')
        t.insertTextContent(c, logo, False)
        # pie: autor y correo (enlazado) a la izquierda, Pág/Total a la derecha
        base.FooterIsOn = True
        base.FooterBodyDistance = 400
        t = base.FooterText
        t.setString('')
        c = t.createTextCursor()
        c.CharFontName, c.CharHeight, c.ParaTabStops = 'Liberation Sans', 9, (tab,)
        c.TopBorder, c.TopBorderDistance = linea, 80
        if autor:
            t.insertString(c, autor + (' · ' if correo else ''), False)
        if correo:
            enlace(t, c, f'mailto:{correo}', correo)
        t.insertString(c, '\t', False)
        num = doc.createInstance('com.sun.star.text.TextField.PageNumber')
        num.NumberingType = C('com.sun.star.style.NumberingType.ARABIC')
        num.SubType = uno.Enum('com.sun.star.text.PageNumberType', 'CURRENT')
        t.insertTextContent(c, num, False)
        t.insertString(c, '/', False)
        total = doc.createInstance('com.sun.star.text.TextField.PageCount')
        total.NumberingType = C('com.sun.star.style.NumberingType.ARABIC')
        t.insertTextContent(c, total, False)
        # tabla de contenidos (capítulos y apartados) en lugar del marcador
        busca = doc.createSearchDescriptor()
        busca.SearchString = MARCADOR_INDICE
        sitio = doc.findFirst(busca)
        if sitio is not None:        # los documentos breves no llevan índice
            indice = doc.createInstance('com.sun.star.text.ContentIndex')
            indice.CreateFromOutline = True
            indice.Level = 2
            indice.Title = ''
            sitio.setString('')
            sitio.Text.insertTextContent(sitio, indice, False)
            for _ in range(2):           # la segunda, ya con el índice ocupando su sitio
                doc.refresh()
                indice.update()
        doc.storeToURL(uno.systemPathToFileUrl(odt), (P('FilterName', 'writer8'),))
        datos_pdf = uno.Any('[]com.sun.star.beans.PropertyValue', (P('ExportBookmarks', True), P('ExportLinksRelativeFsys', False),
                                                                           P('ReduceImageResolution', True), P('MaxImageResolution', 150),
                                                                           P('UseLosslessCompression', False), P('Quality', 80)))
        doc.storeToURL(uno.systemPathToFileUrl(pdf), (P('FilterName', 'writer_pdf_Export'), P('FilterData', datos_pdf)))
        doc.close(True)
    finally:
        try:
            if escritorio is not None:
                escritorio.terminate()
        except Exception:
            pass
        try:
            lo.wait(20)
        except subprocess.TimeoutExpired:
            lo.kill()
        shutil.rmtree(perfil, ignore_errors=True)


# ------------------------------------------------------------------ 3. Revisión del PDF (Python de VenB)

def revisar(pdf, imagenes, movibles, desplazar, limites):
    """Busca capturas que abren página dejando un hueco grande al pie de la anterior. Cada una se desplaza un bloque
    hacia abajo (desplazar) mientras pueda; si ya no puede, se reduce para caber en el hueco (limites).
    Devuelve (cambiado, avisos)."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    doc = pdfium.PdfDocument(pdf)
    paginas = []
    for n in range(len(doc)):
        cuerpo = []
        for o in doc[n].get_objects(max_depth=3):
            if o.type not in (raw.FPDF_PAGEOBJ_TEXT, raw.FPDF_PAGEOBJ_IMAGE):
                continue
            x0, y0, x1, y1 = o.get_bounds()
            if y0 >= CUERPO_ABAJO and y1 <= CUERPO_ARRIBA:
                cuerpo.append((o.type == raw.FPDF_PAGEOBJ_IMAGE and y1 - y0 > 60, y0, y1))
        paginas.append(cuerpo)
    # capturas en orden de aparición (de arriba abajo en cada página; la portada no cuenta)
    vistas = [(n, y0, y1) for n, cuerpo in enumerate(paginas) if n > 0
              for es, y0, y1 in sorted(cuerpo, key=lambda c: -c[2]) if es]
    if len(vistas) != len(imagenes):
        return False, [f'No cuadran las capturas del PDF ({len(vistas)}) con las del manual ({len(imagenes)}): no se recolocan.']
    avisos, cambiado = [], False
    for nombre, (n, y0, y1) in zip(imagenes, vistas):
        if n < 3 or y1 < max(c[2] for c in paginas[n]) - 2:
            continue                              # la captura no abre la página: no ha saltado
        anterior = paginas[n - 1]
        hueco = min(c[1] for c in anterior) - CUERPO_ABAJO if anterior else 0
        if hueco < HUECO_MIN:
            continue
        if desplazar.get(nombre, 0) < movibles.get(nombre, 0):
            desplazar[nombre] = desplazar.get(nombre, 0) + 1       # el texto siguiente sube a llenar el hueco
            cambiado = True
        elif hueco - 40 >= (y1 - y0) * REDUCCION_MAX and nombre not in limites:
            limites[nombre] = int((hueco - 40) * PT)              # 40 pt para el pie de la captura
            cambiado = True
        else:
            avisos.append(f'La captura {nombre} deja un hueco de {hueco:.0f} pt en la página {n}.')
    return cambiado, avisos


# ------------------------------------------------------------------

def generar(version, salida, borrar_anteriores=False, doc='usuario'):
    """Crea el documento (Manual_VenB-<versión>, Instalar_VenB-<versión>…) en ODT y PDF en la carpeta salida.
    Devuelve sus rutas y escribe los avisos."""
    from datetime import date
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import rutas
    a = rutas.ajustes()
    salida = os.path.abspath(salida)
    nombre = DOCUMENTOS[doc]['fichero'].format(v=version)
    odt, pdf = (os.path.join(salida, f'{nombre}.{e}') for e in ('odt', 'pdf'))
    desplazar, limites, avisos = {}, {}, []
    for _ in range(8):
        tmp = tempfile.mkdtemp(prefix='venb_manual_')
        try:
            ruta_html, imagenes, _, movibles = html(version, date.today().strftime('%d/%m/%Y'), tmp, desplazar, doc)
            subprocess.run(['/usr/bin/python3', os.path.abspath(__file__), '--uno', ruta_html, odt, pdf,
                            a.get('manual_autor', ''), a.get('manual_correo', ''), json.dumps(limites)], check=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        cambiado, avisos = revisar(pdf, imagenes, movibles, desplazar, limites)
        if not cambiado:
            break
    for x in avisos:
        print('Aviso del manual:', x, file=sys.stderr)
    if desplazar or limites:
        print(f'Capturas recolocadas: {desplazar or "ninguna"}; reducidas: {sorted(limites) or "ninguna"}', file=sys.stderr)
    if borrar_anteriores:
        for f in os.listdir(salida):
            if re.fullmatch(re.escape(DOCUMENTOS[doc]['fichero'].format(v='@')).replace('@', r'[\d.]+') + r'\.(odt|pdf)', f) and f not in (os.path.basename(odt), os.path.basename(pdf)):
                os.remove(os.path.join(salida, f))
    return odt, pdf


if __name__ == '__main__':
    if len(sys.argv) == 8 and sys.argv[1] == '--uno':
        maquetar(*sys.argv[2:])
    elif len(sys.argv) in (2, 3):
        for r in generar(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else os.path.dirname(RAIZ)):
            print(r)
    else:
        sys.exit(__doc__)
