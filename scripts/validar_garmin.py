"""Compara los datos descargados por garmindb con un CSV de referencia.
Uso: python3 validar_garmin.py fuente_garmin csv fecha"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from carga import cargar
import pandas as pd
if len(sys.argv) < 4:
    sys.exit(__doc__)
fuente, csv, fecha = sys.argv[1:4]
hasta = pd.Timestamp(fecha) + pd.Timedelta(days=1)
g, pg, dg = cargar(fuente, fecha)
c, pc, dc = cargar(csv, fecha)
g = g[g.Fecha < hasta]
print(f"{'':16}{'Garmin':>10}{'CSV':>10}")
for n, a, b in [('Actividades', len(g), len(c)), ('Duplicadas', len(dg), len(dc)),
                ('km bici', g[g.bici].Distancia.sum(), c[c.bici].Distancia.sum()),
                ('Horas bici', g[g.bici].h.sum(), c[c.bici].h.sum()),
                ('Con TSS real', int(g.tss_real.sum()), int(c.tss_real.sum())),
                ('Con pot. 20 min', int(g['Potencia media máxima (20 minutos)'].notna().sum()), int(c['Potencia media máxima (20 minutos)'].notna().sum())),
                ('CTL', pg.CTL.iloc[-1], pc.CTL.iloc[-1]), ('ATL', pg.ATL.iloc[-1], pc.ATL.iloc[-1]), ('TSB', pg.TSB.iloc[-1], pc.TSB.iloc[-1])]:
    print(f"{n:16}{a:10.1f}{b:10.1f}")
print('\nActividades por tipo (Garmin - CSV):')
t = pd.concat([g['Tipo de actividad'].value_counts().rename('G'), c['Tipo de actividad'].value_counts().rename('C')], axis=1).fillna(0)
print(t[t.G != t.C].astype(int).to_string() if (t.G != t.C).any() else 'sin diferencias')
fg, fc = set(g.Fecha), set(c.Fecha)
print('\nSolo en Garmin:', g[g.Fecha.isin(fg - fc)][['Fecha', 'Título', 'Distancia']].to_string(index=False) if fg - fc else 'ninguna')
print('Solo en CSV:', c[c.Fecha.isin(fc - fg)][['Fecha', 'Título', 'Distancia']].to_string(index=False) if fc - fg else 'ninguna')
print('\nÚltima actividad en Garmin:', cargar(fuente)[0].Fecha.max())
