"""Busca cortes de potencia en los FIT de rodillo (ceros, valores congelados y huecos).
Uso: python cortes_potencia.py [AAAA-MM] [carpeta_con_json_y_fit]
Por defecto revisa todas las sesiones de la carpeta de Garmin configurada."""
import glob,json,os,sys,pandas as pd
from fitparse import FitFile
import rutas
DESDE=sys.argv[1] if len(sys.argv)>1 else ''
D=os.path.join(sys.argv[2] if len(sys.argv)>2 else rutas.ruta_garmin(),''); out=[]
for f in glob.glob(D+'activity_[0-9]*.json'):
    a=json.load(open(f))
    if (a.get('activityType') or {}).get('typeKey') not in('virtual_ride','indoor_cycling') or a['startTimeLocal']<DESDE: continue
    fit=glob.glob(D+f"{a['activityId']}*.fit")
    if not fit: out.append((a['startTimeLocal'][:10],a['activityName'][:34],'sinFIT')+(None,)*5); continue
    R=[{k:v for k,v in ((d.name,d.value) for d in m)} for m in FitFile(fit[0]).get_messages('record')]
    r=pd.DataFrame(R)
    if 'power' not in r or len(r)<300: out.append((a['startTimeLocal'][:10],a['activityName'][:34],'sinPot',len(r))+(None,)*4); continue
    t=pd.to_datetime(r.timestamp); gap=t.diff().dt.total_seconds().fillna(1)
    p=r.power; ini=len(r)//40; 
    c=(p==0)|p.isna()
    g=(c!=c.shift()).cumsum(); cortes=c.groupby(g).sum(); 
    n3=int((cortes>=3).sum()); seg=int(cortes[cortes>=3].sum())
    same=(p!=p.shift()).cumsum(); cong=p.groupby(same).transform('size'); frz=int(((cong>=8)&(p>0)).sum())
    out.append((a['startTimeLocal'][:10],a['activityName'][:34],round(len(r)/60),n3,seg,round(100*seg/len(r),1),frz,int((gap>3).sum())))
d=pd.DataFrame(out,columns=['fecha','titulo','min','cortes>=3s','seg_cero','%cero','seg_congelado','huecos>3s']).sort_values('fecha')
pd.set_option('display.width',200,'display.max_rows',100); print(d.to_string(index=False))
