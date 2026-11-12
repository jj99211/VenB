"""Carga actividades de Garmin, elimina grabaciones solapadas y calcula TSS, CTL, ATL y TSB.
Fuentes: un Activities.csv de Garmin Connect, o los JSON que descarga garmindb (fuente "garmin"), a los que se suman
las actividades subidas a mano en GPX, FIT o TCX (VenB-datos/datos/actividades_locales.csv, ver venb/importar.py).
Los JSON se usan porque la base SQLite de garmindb no guarda TSS, NP ni potencia de 20 min.
Uso: from carga import cargar; df, pmc, dups = cargar("garmin", hasta="AAAA-MM-DD")
     df, pmc, dups = cargar("datos/Activities.csv", hasta="AAAA-MM-DD")
"""
import glob, json, os
import pandas as pd, numpy as np

import rutas
DIR_GARMIN = rutas.ruta_garmin()

def num(s): return pd.to_numeric(s.astype(str).str.replace(",","").str.replace("'","").replace("--",np.nan),errors="coerce")
def hms(s):
    def f(x):
        try:
            p=[float(v) for v in str(x).split(":")]
            return p[0]+p[1]/60+p[2]/3600 if len(p)==3 else p[0]/60+p[1]/3600
        except Exception: return np.nan
    return s.map(f)

def leer_csv(ruta):
    df=pd.read_csv(ruta)
    df['Fecha']=pd.to_datetime(df['Fecha'])
    for c in ['Distancia','Calorías','Frecuencia cardiaca media','FC máxima','TE aeróbico','Velocidad media','Ascenso total','Normalized Power® (NP®)','Training Stress Score®','Potencia media máxima (20 minutos)','Potencia media','Potencia máxima']:
        df[c]=num(df[c])
    df['h']=hms(df['Tiempo en movimiento']); df['h']=df['h'].fillna(hms(df['Tiempo']))
    df['h_total']=hms(df['Tiempo transcurrido'])
    return df

def tipo_garmin(clave):
    """Traduce activityType.typeKey de Garmin a los nombres del CSV, que son los que usa el método."""
    clave=clave or ''
    if clave=='virtual_ride': return 'Ciclismo virtual'
    if clave=='indoor_cycling': return 'Ciclismo en sala'
    if clave=='road_biking': return 'Ciclismo en ruta'
    if clave=='mountain_biking': return 'Ciclismo de montaña'
    if 'cycling' in clave or 'biking' in clave: return 'Ciclismo'
    if clave=='running': return 'Carrera'
    if clave=='walking': return 'Caminar'
    if clave=='other': return 'Otros'
    return clave

def leer_garmin(directorio=DIR_GARMIN):
    """Lee los resúmenes activity_<id>.json de garmindb (no los activity_details_*)."""
    filas=[]
    for f in glob.glob(os.path.join(directorio,'activity_[0-9]*.json')):
        with open(f,encoding='utf-8') as fh: a=json.load(fh)
        filas.append({'id':a.get('activityId'),'Tipo de actividad':tipo_garmin((a.get('activityType') or {}).get('typeKey')),
            'Fecha':a.get('startTimeLocal'),'Título':a.get('activityName'),'Distancia':(a.get('distance') or 0)/1000,
            'Calorías':a.get('calories'),'Frecuencia cardiaca media':a.get('averageHR'),'FC máxima':a.get('maxHR'),
            'TE aeróbico':a.get('aerobicTrainingEffect'),'Ascenso total':a.get('elevationGain'),
            'Normalized Power® (NP®)':a.get('normPower'),'Training Stress Score®':a.get('trainingStressScore'),
            'Potencia media máxima (20 minutos)':a.get('max20MinPower'),'Potencia media':a.get('avgPower'),'Potencia máxima':a.get('maxPower'),
            'h':a.get('movingDuration') or a.get('duration'),'h_total':a.get('elapsedDuration') or a.get('duration')})
    if not filas: raise FileNotFoundError(f'No hay actividades de garmindb en {directorio}')
    df=pd.DataFrame(filas)
    df['Fecha']=pd.to_datetime(df['Fecha'])
    for c in ['Normalized Power® (NP®)','Training Stress Score®','Potencia media máxima (20 minutos)','Potencia media','Potencia máxima','h','h_total']:
        df[c]=pd.to_numeric(df[c],errors='coerce')
    df['h']=df['h']/3600; df['h_total']=df['h_total']/3600
    return df

def leer_locales(ruta=None):
    """Actividades subidas a mano, con las mismas columnas que leer_garmin; vacío si no hay."""
    ruta=ruta or os.path.join(rutas.DATOS,'actividades_locales.csv')
    if not os.path.exists(ruta): return pd.DataFrame()
    e=pd.read_csv(ruta,dtype={'id':str})
    if e.empty: return pd.DataFrame()
    df=pd.DataFrame({'id':e.id,'Tipo de actividad':e.tipo,'Fecha':pd.to_datetime(e.fecha),'Título':e.titulo,'Distancia':e.km,
        'Calorías':e.calorias,'Frecuencia cardiaca media':e.fc_media,'FC máxima':e.fc_max,'TE aeróbico':np.nan,'Ascenso total':e.desnivel,
        'Normalized Power® (NP®)':e.np,'Training Stress Score®':e.tss,'Potencia media máxima (20 minutos)':e.p20,
        'Potencia media':e.potencia_media,'Potencia máxima':e.potencia_max,'h':e.h,'h_total':e.h_total})
    return df

def leer_todo():
    """Garmin (garmindb) y actividades subidas a mano."""
    partes=[]
    try: partes.append(leer_garmin())
    except FileNotFoundError: pass
    loc=leer_locales()
    if len(loc): partes.append(loc)
    if not partes: raise FileNotFoundError('No hay actividades de Garmin ni subidas a mano')
    return pd.concat(partes,ignore_index=True) if len(partes)>1 else partes[0]

def cargar(ruta="garmin", hasta=None):
    df=leer_todo() if ruta=="garmin" else leer_garmin(ruta) if os.path.isdir(ruta) else leer_csv(ruta)
    df['bici']=df['Tipo de actividad'].str.contains('Ciclismo')
    df['virtual']=df['Tipo de actividad'].isin(['Ciclismo virtual','Ciclismo en sala'])
    # fin de actividad y deduplicado (grabaciones solapadas: se conserva la más larga)
    df['fin']=df['Fecha']+pd.to_timedelta(df['h_total'].fillna(df['h']),unit='h')
    df=df.sort_values('Fecha').reset_index(drop=True)
    drop=set()
    b=df[df.bici]
    idx,ini,fin,dist=list(b.index),list(b.Fecha),list(b.fin),list(b.Distancia)
    for x,i in enumerate(idx):
        for y in range(x+1,len(idx)):
            if not ini[y]<fin[x]: break  # ordenadas por inicio: las siguientes tampoco solapan
            j=idx[y]
            if i in drop: break
            if j not in drop and ini[x]<fin[y]:
                drop.add(i if dist[x]<dist[y] else j)
    dups=df.loc[sorted(drop),['Fecha','Título','Distancia']]
    df=df.drop(index=list(drop))
    # TSS: real (potencia) en rodillo; estimado en exterior por duración (IF supuesto)
    def est(r):
        t=r['Training Stress Score®']
        if pd.notna(t) and t>0: return t
        h=r.h if pd.notna(r.h) else 0
        tipo=r['Tipo de actividad']
        if tipo=='Caminar' or tipo=='Otros': return 0
        if tipo=='Carrera': IF=0.75
        elif r.bici:
            IF=0.72 if h<5 else (0.66 if h<12 else 0.60)
        else: return 0
        return h*100*IF**2
    df['tss']=df.apply(est,axis=1)
    df['tss_real']=(df['Training Stress Score®']>0)
    # Correcciones a mano (p. ej. TSS de Garmin calculado con un FTP equivocado): datos/tss_corregido.csv (id,tss,motivo)
    rc=os.path.join(rutas.DATOS,'tss_corregido.csv')
    if os.path.exists(rc):
        corr=pd.read_csv(rc,dtype={'id':str}).set_index('id')['tss']
        m=df['id'].astype(str).isin(corr.index)
        df.loc[m,'tss']=df.loc[m,'id'].astype(str).map(corr)
    rows=[]
    for _,r in df.iterrows():
        el=(r.fin-r.Fecha).total_seconds()/86400
        n=max(1,int(np.ceil(el))) if el>1 else 1
        for k in range(n): rows.append((r.Fecha.normalize()+pd.Timedelta(days=k), r.tss/n))
    d=pd.DataFrame(rows,columns=['f','t']).groupby('f').t.sum()
    d=d.reindex(pd.date_range(d.index.min(),(hasta or pd.Timestamp.today().normalize())),fill_value=0)
    ctl=d.ewm(alpha=1/42,adjust=False).mean(); atl=d.ewm(alpha=1/7,adjust=False).mean()
    pmc=pd.DataFrame({'tss':d,'CTL':ctl,'ATL':atl}); pmc['TSB']=pmc.CTL.shift(1)-pmc.ATL.shift(1)

    return df, pmc, dups