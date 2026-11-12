"""Arranca VenB en primer plano y espera hasta que se cierre. Sirve en Linux y Windows.
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import logging
import os
import sys
import threading
import time
import urllib.request
import webbrowser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import rutas  # noqa: E402

PUERTO = rutas.puerto()
URL = f'http://127.0.0.1:{PUERTO}'


def activa():
    try:
        urllib.request.urlopen(f'{URL}/acerca', timeout=2).close()
        return True
    except OSError:
        return False


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    from version import VERSION
    print(f"{'VenB Rutas' if rutas.RUTAS else 'VenB'} {VERSION}: {URL}")
    print('Para cerrarla, usa el botón «Cerrar VenB» o pulsa Ctrl+C aquí.', flush=True)
    if activa():
        # Otra terminal ya la tiene abierta: se abre el navegador y se espera igualmente a su cierre.
        webbrowser.open(URL)
        try:
            while activa():
                time.sleep(2)
        except KeyboardInterrupt:
            print('VenB sigue abierta en la otra terminal.')
            return
    else:
        import flask.cli
        from app import ESCUCHA, app
        import red
        flask.cli.show_server_banner = lambda *a: None
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        if ESCUCHA != '127.0.0.1':
            otra = red.direccion(PUERTO)
            print(f'Abierta a la red local, con clave: {otra or "no se ha encontrado la IP de este ordenador"}', flush=True)
        if not os.environ.pop('VENB_SIN_NAVEGADOR', ''):   # tras «Actualizar», la pestaña abierta se recarga sola
            threading.Timer(1, webbrowser.open, [URL]).start()
        import datos_venb
        threading.Timer(2, datos_venb.descargar_recientes).start()  # lo nuevo de Garmin, sin esperar a la descarga diaria
        try:
            app.run(host=ESCUCHA, port=PUERTO, debug=False)
        except KeyboardInterrupt:
            pass
    print('VenB cerrada.')


if __name__ == '__main__':
    main()
