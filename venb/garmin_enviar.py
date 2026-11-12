"""Envía cambios a Garmin Connect con la sesión guardada por garmindb.
Se ejecuta con el Python de garmindb (VenB lo llama así), no con el de VenB: así las credenciales no pasan por la app.
Uso: python garmin_enviar.py probar
     python garmin_enviar.py nombre ID_ACTIVIDAD "Nombre nuevo"
     python garmin_enviar.py peso AAAA-MM-DDTHH:MM:SS KILOS
     python garmin_enviar.py equipo     (bicis de Garmin Connect y sus actividades, en JSON por la salida estándar)
Sale con 0 si Garmin lo acepta; si no, escribe el motivo en la salida de errores."""
import json
import re
import os
import sys
from datetime import datetime


def _sin_mfa():
    raise RuntimeError('Tu cuenta de Garmin pide un código de verificación: inicia sesión una vez desde una terminal (ver Ayuda).')


def _equipo(c):
    """Bicis del equipo de Garmin Connect (no las zapatillas) con los identificadores de sus actividades."""
    perfil = c.connectapi('/userprofile-service/socialProfile') or {}
    equipo = c.connectapi('/gear-service/gear/filterGear', params={'userProfilePk': perfil.get('profileId') or perfil.get('id')}) or []
    salida = []
    for x in equipo:
        if (x.get('gearTypeName') or '').lower() != 'bike':
            continue
        ids, rodillo, inicio = [], [], 0
        while True:
            pagina = c.connectapi(f"/activitylist-service/activities/{x['uuid']}/gear", params={'start': inicio, 'limit': 500}) or []
            ids += [str(a['activityId']) for a in pagina if a.get('activityId')]
            rodillo += [str(a['activityId']) for a in pagina if a.get('activityId')
                        and (a.get('activityType') or {}).get('typeKey') in ('virtual_ride', 'indoor_cycling')]
            if len(pagina) < 500:
                break
            inicio += 500
        nombre = (x.get('displayName') or '').strip()
        modelo = (x.get('customMakeModel') or '').strip()
        nombre, modelo = (nombre, modelo) if nombre else (modelo, '')
        salida.append({'uuid': x['uuid'], 'nombre': nombre or 'Bici sin nombre', 'modelo': modelo if modelo != nombre else '',
                       'retirada': (x.get('gearStatusName') or '') == 'retired', 'actividades': ids, 'rodillo': rodillo})
    return salida


def _argumentos():
    a = sys.argv[1:]
    if a in (['probar'], ['equipo']):
        return a[0], None, None
    if len(a) == 3 and a[0] == 'nombre' and a[1].isdigit() and a[2].strip():
        return a
    if len(a) == 3 and a[0] == 'peso':
        try:
            datetime.fromisoformat(a[1])
            if 30 <= float(a[2]) <= 200:
                return a
        except ValueError:
            pass
    sys.exit(__doc__.split('\n', 2)[2].split('\nSale')[0])


def main():
    orden, x, y = _argumentos()
    from garmindb import GarminConnectConfigManager
    from garmindb.garmin_connect_auth_adapter import GarminConnectAuthAdapter
    config = os.path.join(os.path.expanduser('~'), '.venb', 'garmin')  # rutas.GARMIN_CONFIG: aquí no se importa rutas
    g = GarminConnectAuthAdapter(GarminConnectConfigManager(config), mfa_prompt=_sin_mfa)
    try:
        g.login()
        if orden == 'probar':
            perfil = g.client.connectapi('/userprofile-service/socialProfile') or {}
            print(perfil.get('fullName') or perfil.get('displayName') or '')
        elif orden == 'nombre':
            g.client.set_activity_name(x, y.strip())
        elif orden == 'equipo':
            print(json.dumps(_equipo(g.client)))
        else:
            g.client.add_weigh_in(float(y), unitKey='kg', timestamp=x)
    except Exception as e:  # cualquier fallo de Garmin se comunica a VenB
        tipo = type(e).__name__
        if 'TooManyRequests' in tipo or re.search(r'\b(429|1015)\b|rate.?limit|Too Many Requests', str(e), re.I):
            sys.exit('Garmin ha bloqueado temporalmente el acceso desde tu conexión por demasiados intentos (429).')
        if re.search(r'MFA|two.?factor', f'{tipo} {e}', re.I):
            sys.exit('Tu cuenta de Garmin pide la verificación en dos pasos (MFA): VenB no puede conectarse así.')
        if 'NotFound' in tipo:
            sys.exit('Garmin Connect no encuentra esa actividad: quizá se ha borrado.')
        if 'Auth' in tipo:
            sys.exit('No se ha podido iniciar sesión en Garmin Connect: revisa el usuario y la contraseña en Ajustes.')
        if 'Connection' in tipo:
            sys.exit('Garmin Connect no responde. Inténtalo más tarde.')
        sys.exit(f'{tipo}: {e}')


if __name__ == '__main__':
    main()
