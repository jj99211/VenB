"""Genera los gráficos SVG/PNG de carga y volumen.
Uso: python3 graficos.py <garmin|Activities.csv> <carpeta_salida> [fecha_hasta]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from carga import cargar
import pandas as pd
csv, out = sys.argv[1], sys.argv[2]; hasta = sys.argv[3] if len(sys.argv)>3 else None
os.makedirs(out, exist_ok=True)
df, pmc, dups = cargar(csv, hasta)
inicio_pmc = (pmc.index[-1]-pd.DateOffset(months=15)).strftime('%Y-%m-%d')
inicio_sem = (pmc.index[-1]-pd.DateOffset(weeks=17)).strftime('%Y-%m-%d')
import matplotlib, matplotlib.ticker; matplotlib.use('Agg')
import matplotlib.pyplot as plt, matplotlib.dates as md
plt.rcParams.update({'axes.axisbelow':True,'font.family':'DejaVu Sans','font.size':9,'axes.edgecolor':'#9a9994','axes.labelcolor':'#52514e',
 'xtick.color':'#52514e','ytick.color':'#52514e','axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
MES=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']
fm=matplotlib.ticker.FuncFormatter(lambda x,_: f"{MES[md.num2date(x).month-1]} {md.num2date(x).strftime('%y')}")
fd=matplotlib.ticker.FuncFormatter(lambda x,_: md.num2date(x).strftime('%d/%m/%Y'))
B,O,G='#2a78d6','#eb6834','#8a8984'
# 1 PMC
p=pmc.loc[inicio_pmc:]
fig,(a1,a2)=plt.subplots(2,1,figsize=(8,4.6),sharex=True,gridspec_kw={'height_ratios':[2,1]})
a1.plot(p.index,p.CTL,color=B,lw=2); a1.plot(p.index,p.ATL,color=O,lw=1.2,alpha=.85)
a1.text(p.index[-1]+pd.Timedelta(days=4),p.CTL.iloc[-1]+6,f'Forma\n(CTL) {p.CTL.iloc[-1]:.0f}',color='#0b0b0b',ha='left',fontsize=8)
a1.text(p.index[-1]+pd.Timedelta(days=4),p.ATL.iloc[-1]-22,f'Fatiga\n(ATL) {p.ATL.iloc[-1]:.0f}',color='#0b0b0b',ha='left',fontsize=8)
a1.set_xlim(p.index[0],p.index[-1]+pd.Timedelta(days=45))
import rutas
TOPE=max(float(p.ATL.max()),float(p.CTL.max()))*1.05 or 1
for f,t in rutas.ajustes()['marcas_graficos']:
    a1.axvline(pd.Timestamp(f),color=G,lw=.6,ls=':'); a1.text(pd.Timestamp(f),TOPE*.95,t,fontsize=7,color='#52514e',rotation=90,va='top',ha='right')
a1.set_ylim(0,TOPE); a1.set_ylabel('TSS/día'); a1.grid(axis='y',color='#e6e5e0',lw=.6)
a1.set_title('Carga de entrenamiento (TSS estimado) — últimos 15 meses',loc='left',fontsize=10,color='#0b0b0b')
a2.fill_between(p.index,p.TSB,0,color=B,alpha=.35,lw=0); a2.plot(p.index,p.TSB,color=B,lw=.8)
for y in (-30,0,25): a2.axhline(y,color=G,lw=.6,ls='--' if y else '-')
a2.set_ylim(min(float(p.TSB.min())*1.1,-40),45); a2.set_ylabel('Frescura (TSB)'); a2.text(p.index[5],27,'+25 fresco',fontsize=7,color='#52514e'); a2.text(p.index[5],-45,'−30 sobrecarga',fontsize=7,color='#52514e')
a2.xaxis.set_major_formatter(fm); fig.tight_layout()
for e in ('svg','png'): fig.savefig(f'{out}/carga_ctl_atl_tsb.{e}',dpi=200)
# 2 volumen mensual horas por año
b=df[df.bici].copy(); b['y']=b.Fecha.dt.year; b['m']=b.Fecha.dt.month
t=b.pivot_table(index='m',columns='y',values='h',aggfunc='sum').reindex(range(1,13)).fillna(0)
fig,ax=plt.subplots(figsize=(8,3.2)); w=.27; yy=sorted(t.columns)[-3:]; cols=dict(zip(yy,['#b9b8b2','#86b6ef',B]))
for k,y in enumerate(yy):
    ax.bar(t.index+(k-1)*w,t[y],w-.03,color=cols[y],label=str(y))
ax.set_xticks(range(1,13),['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'])
ax.set_ylabel('horas'); ax.legend(frameon=False,ncol=3,loc='upper left'); ax.grid(axis='y',color='#e6e5e0',lw=.6)
ax.set_title('Horas de ciclismo por mes y año',loc='left',fontsize=10,color='#0b0b0b'); fig.tight_layout()
for e in ('svg','png'): fig.savefig(f'{out}/horas_mensuales.{e}',dpi=200)
# 3 semanas recientes
w2=b.set_index('Fecha').resample('W-SUN').agg({'h':'sum'}).loc[inicio_sem:]
fig,ax=plt.subplots(figsize=(8,2.8))
ax.bar(w2.index,w2.h,width=5,color=B)
for x,v in zip(w2.index,w2.h): ax.text(x,v+.8,f'{v:.0f}',ha='center',fontsize=7,color='#52514e')
ax.set_ylabel('horas'); ax.xaxis.set_major_formatter(fd); ax.grid(axis='y',color='#e6e5e0',lw=.6)
ax.set_title('Horas de ciclismo por semana (lun–dom) — últimas 17 semanas',loc='left',fontsize=10,color='#0b0b0b'); fig.tight_layout()
for e in ('svg','png'): fig.savefig(f'{out}/horas_semanales.{e}',dpi=200)
