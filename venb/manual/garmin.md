# Importar tus datos de Garmin

Este capítulo explica cómo incorporar tus datos a una instalación vacía. Tus datos no salen de tu ordenador salvo hacia tu propia cuenta de Garmin. Hay dos vías, y lo normal es usar las dos: la primera mantiene la aplicación al día y la segunda añade tu historial antiguo.

| Vía | Qué aporta | Dónde se ve |
|---|---|---|
| 1. Descarga automática (garmindb) | Hasta 1.000 actividades recientes y las nuevas de cada día, con carga, potencia, sueño, VFC y FC en reposo | Todas las páginas |
| 2. Exportación de tu cuenta de Garmin | Todo tu historial de actividades y de peso, una sola vez | Histórico y gráficas anuales. No calcula la carga (CTL, ATL, TSB) |

Si alguna actividad no está en Garmin Connect, o no usas Garmin, súbela como fichero GPX, FIT o TCX: consulta [Importar actividades de ficheros](manual.md#importar-actividades-de-ficheros).

En las órdenes siguientes, `VenB-X.YZ` es la carpeta de la versión que tienes instalada. Las órdenes están escritas para ejecutarlas desde ella: abre allí una terminal.

## Vía 1. Descarga automática

### 1. Instalar la descarga

Ejecuta de nuevo el instalador de tu versión y responde **s** a la pregunta sobre la descarga automática de Garmin. Si ya lo hiciste al instalar, pasa al punto siguiente.

- Linux: `bash instalar-en-linux.sh`
- Windows: doble clic en `INSTALAR-EN-WINDOWS`

### 2. Conectar tu cuenta

En **Ajustes**, apartado **Garmin Connect** (con **Usar Garmin Connect** marcada), escribe el correo y la contraseña con los que entras en Garmin Connect y pulsa **Guardar y conectar**. VenB comprueba la conexión y te dice si ha funcionado. **Comprobar la conexión** hace lo mismo más adelante: la respuesta («Conectado a Garmin Connect como…» o el motivo del fallo) aparece en ese mismo apartado.

Se guardan sin cifrar y solo en tu ordenador, en `.venb/garmin/GarminConnectConfig.json` de tu carpeta personal, fuera de las copias de seguridad. Para cambiar la contraseña, escribe la nueva; en blanco, se conserva.

Los datos de salud se piden desde la fecha indicada en ese mismo fichero (`sleep_start_date`, `rhr_start_date` y `hrv_start_date`). Cámbiala antes de la primera descarga si quieres más historial.

Si tu cuenta de Garmin pide un código de verificación al iniciar sesión, VenB no puede pedírtelo: haz la primera descarga desde una terminal con la orden del punto siguiente, que sí lo pregunta.

### 3. Hacer la primera descarga

En el mismo apartado, pulsa **Descargar todo ahora**. Puede tardar horas: puedes seguir usando VenB, y Ajustes te indica cuándo termina. Si cierras VenB, la descarga sigue.

También se puede hacer desde una terminal (la primera orden, en Linux; la segunda, en Windows):

```
cd ~/.venb/garmin && ~/.venb/python/garmindb/bin/python ~/.venb/python/garmindb/bin/garmindb_cli.py -f ~/.venb/garmin --all --download --import --analyze
cd /d "%USERPROFILE%\.venb\garmin" && "%USERPROFILE%\.venb\python\garmindb\Scripts\python.exe" "%USERPROFILE%\.venb\python\garmindb\Scripts\garmindb_cli.py" -f "%USERPROFILE%\.venb\garmin" --all --download --import --analyze
```

### 4. Abrir VenB

Las actividades aparecen solas. Después, VenB trae lo nuevo de Garmin Connect cada vez que se abre y cada pocas horas mientras sigue abierta. Para no esperar, por ejemplo al volver de una salida, pulsa **Traer lo nuevo de Garmin** en Inicio, junto a las últimas actividades. Mientras se descarga, Inicio lo indica (suele tardar menos de un minuto, y puedes seguir usando VenB); al terminar, la página se actualiza sola y dice cuántas actividades nuevas ha traído o que no hay ninguna. Si falla, lo dice también.

Además, el instalador programa una descarga al día que funciona aunque VenB esté cerrada, para que los datos estén al día al abrirla. En Linux, si el ordenador estaba apagado a esa hora, se hace al encenderlo.

## Vía 2. Historial completo

### 1. Solicitar la exportación

En [la gestión de datos de tu cuenta de Garmin](https://www.garmin.com/account/datamanagement/), solicita la exportación de tus datos. Garmin te enviará por correo un enlace a un ZIP, normalmente en unos días.

### 2. Importar el ZIP

Guarda el ZIP en tu ordenador, sin descomprimirlo. En **Ajustes**, apartado **Copia de seguridad e importación**, elígelo y pulsa **Importar**. Con un ZIP grande puede tardar varios minutos. Antes de importar, VenB guarda una copia de tus datos actuales en `VenB-datos/copias/`.

También se puede importar desde una terminal abierta en la carpeta `VenB-X.YZ`, con la ruta real del ZIP al final (en Linux y en Windows):

```
~/.venb/python/venb/bin/python venb/importar_historico.py RUTA_DEL_ZIP
"%USERPROFILE%\.venb\python\venb\Scripts\python.exe" venb\importar_historico.py RUTA_DEL_ZIP
```

Solo se guardan las actividades y el peso, en `VenB-datos/datos/`. Importar otra exportación sustituye a la anterior, y las actividades de las dos vías no se duplican. Después ya no necesitas el ZIP: tus copias de seguridad de VenB incluyen ese historial.

## Traer el peso de Garmin

Por defecto, el peso se anota a mano en Inicio. Para traerlo de Garmin, necesitas la vía 1 y que tu peso llegue a Garmin Connect, con una báscula conectada o anotándolo allí. Después, en **Ajustes**, elige **Garmin** en **Origen del peso**.

- La siguiente descarga trae el peso de los últimos 90 días. Para traer más, cambia `weight_start_date` en el fichero de configuración, con el formato mes/día/año, antes de esa descarga.
- Si un día tiene un peso anotado a mano, ese es el que se usa, así que puedes corregir un valor erróneo desde Inicio.
- Mientras no llegue ningún peso, cada descarga vuelve a pedir esos días a Garmin. Si no registras tu peso allí, deja **A mano**.
- Volver a **A mano** detiene la descarga del peso, pero no borra lo ya descargado.

## Comprobar que ha funcionado

**Inicio** muestra la carga de entrenamiento y las últimas actividades (con la vía 1), y **Histórico**, tus actividades desde la más antigua. Si una descarga falla (contraseña cambiada o incorrecta, cuenta sin configurar, verificación en dos pasos o sin internet), Inicio lo dice con su motivo y VenB no lo vuelve a intentar sola hasta que la abras de nuevo, para no insistir ante Garmin con una contraseña mala; tus datos anteriores siguen disponibles. Corrige el usuario o la contraseña en Ajustes y pulsa **Traer lo nuevo de Garmin**. Si la conexión funciona y la descarga sigue fallando, repite la primera descarga desde una terminal: sus mensajes indican la causa. Sin cuenta de Garmin, o con **Usar Garmin Connect** desmarcada, VenB no intenta ninguna descarga.


## Si Garmin bloquea el acceso

Garmin bloquea durante unas horas la conexión desde la que se inicia sesión demasiadas veces seguidas. Se nota porque VenB no puede conectarse y porque, en el navegador, connect.garmin.com muestra «Error 1015» o «You are being rate limited». El bloqueo afecta a toda la conexión de casa, también al navegador, y se quita solo si se deja de intentar.

Para no provocarlo, cuando falla un inicio de sesión VenB espera antes de volver a intentarlo sola: 30 minutos tras el primer fallo, 2 horas tras el segundo, 6 tras el tercero y 24 a partir de ahí, aunque cierres y vuelvas a abrir VenB. Lo mismo hace la descarga diaria. Los botones (**Traer lo nuevo de Garmin**, **Comprobar la conexión**, **Descargar todo ahora**) admiten como mucho 3 intentos por hora y se desactivan mientras Garmin tenga bloqueada la conexión. Inicio y Ajustes explican qué ha pasado y a qué hora se podrá volver a intentar. Un inicio de sesión correcto lo pone todo a cero, y guardar otro usuario o contraseña permite probar en el momento (salvo durante un bloqueo).

Qué hacer:

- **Bloqueo por demasiados intentos:** espera unas horas sin intentarlo, tampoco desde el navegador. Después, entra en connect.garmin.com, mejor desde el móvil con datos móviles, para comprobar el correo y la contraseña.
- **Usuario o contraseña no aceptados:** corrígelos en **Ajustes**. Si no los recuerdas, cámbialos en la web de Garmin y escríbelos de nuevo en VenB.
- **Verificación en dos pasos:** VenB no puede conectarse con ella activada. Desactívala en la configuración de seguridad de tu cuenta de Garmin o sube tus actividades con **Importar**.

[Volver al manual](manual.md)
