"""Gráficos SVG/PNG de carga y volumen para los informes.
Uso: python3 graficos.py <garmin|Activities.csv> <carpeta_salida> [fecha_hasta]
VenB los genera también, con generar(), para el informe semanal automático (scripts/informe_semanal.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402

import rutas  # noqa: E402

MES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
B, O, G = '#2a78d6', '#eb6834', '#8a8984'
FICHEROS = ('carga_ctl_atl_tsb', 'horas_semanales', 'horas_mensuales')


def _estilo():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'axes.axisbelow': True, 'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.edgecolor': '#9a9994',
                         'axes.labelcolor': '#52514e', 'xtick.color': '#52514e', 'ytick.color': '#52514e',
                         'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'none'})
    return plt


def _guardar(fig, out, nombre):
    for e in ('svg', 'png'):
        fig.savefig(os.path.join(out, f'{nombre}.{e}'), dpi=200)


def generar(out, df, pmc):
    """Tres gráficas en `out` (SVG y PNG) con las actividades y la carga hasta el último día de `pmc`."""
    import matplotlib.dates as md
    import matplotlib.ticker as mt
    plt = _estilo()
    os.makedirs(out, exist_ok=True)
    fm = mt.FuncFormatter(lambda x, _: f"{MES[md.num2date(x).month - 1]} {md.num2date(x).strftime('%y')}")
    fd = mt.FuncFormatter(lambda x, _: md.num2date(x).strftime('%d/%m/%Y'))
    fin = pmc.index[-1]
    try:
        # 1 Carga: forma, fatiga y frescura de los últimos 15 meses
        p = pmc.loc[(fin - pd.DateOffset(months=15)).strftime('%Y-%m-%d'):]
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4.6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
        a1.plot(p.index, p.CTL, color=B, lw=2)
        a1.plot(p.index, p.ATL, color=O, lw=1.2, alpha=.85)
        a1.text(p.index[-1] + pd.Timedelta(days=4), p.CTL.iloc[-1] + 6, f'Forma\n(CTL) {p.CTL.iloc[-1]:.0f}', color='#0b0b0b', ha='left', fontsize=8)
        a1.text(p.index[-1] + pd.Timedelta(days=4), p.ATL.iloc[-1] - 22, f'Fatiga\n(ATL) {p.ATL.iloc[-1]:.0f}', color='#0b0b0b', ha='left', fontsize=8)
        a1.set_xlim(p.index[0], p.index[-1] + pd.Timedelta(days=45))
        tope = max(float(p.ATL.max()), float(p.CTL.max())) * 1.05 or 1
        for f, t in rutas.ajustes().get('marcas_graficos', []):
            if p.index[0] <= pd.Timestamp(f) <= fin:
                a1.axvline(pd.Timestamp(f), color=G, lw=.6, ls=':')
                a1.text(pd.Timestamp(f), tope * .95, t, fontsize=7, color='#52514e', rotation=90, va='top', ha='right')
        a1.set_ylim(0, tope)
        a1.set_ylabel('TSS/día')
        a1.grid(axis='y', color='#e6e5e0', lw=.6)
        a1.set_title('Carga de entrenamiento (TSS) — últimos 15 meses', loc='left', fontsize=10, color='#0b0b0b')
        a2.fill_between(p.index, p.TSB, 0, color=B, alpha=.35, lw=0)
        a2.plot(p.index, p.TSB, color=B, lw=.8)
        for y in (-30, 0, 25):
            a2.axhline(y, color=G, lw=.6, ls='--' if y else '-')
        a2.set_ylim(min(float(p.TSB.min()) * 1.1, -40), 45)
        a2.set_ylabel('Frescura (TSB)')
        x0 = p.index[min(5, len(p) - 1)]
        a2.text(x0, 27, '+25 fresco', fontsize=7, color='#52514e')
        a2.text(x0, -45, '−30 sobrecarga', fontsize=7, color='#52514e')
        a2.xaxis.set_major_formatter(fm)
        fig.tight_layout()
        _guardar(fig, out, FICHEROS[0])
        plt.close(fig)
        b = df[df.bici & (df.Fecha < fin + pd.Timedelta(days=1))].copy()
        # 2 Horas por semana (lunes a domingo) de las últimas 17 semanas
        w2 = b.set_index('Fecha').resample('W-SUN').agg({'h': 'sum'}).reindex(pd.date_range(fin - pd.Timedelta(weeks=16), fin, freq='W-SUN'), fill_value=0)
        fig, ax = plt.subplots(figsize=(8, 2.8))
        ax.bar(w2.index, w2.h, width=5, color=B)
        for x, v in zip(w2.index, w2.h):
            ax.text(x, v + .3, f'{v:.0f}', ha='center', fontsize=7, color='#52514e')
        ax.set_ylabel('horas')
        ax.xaxis.set_major_formatter(fd)
        ax.grid(axis='y', color='#e6e5e0', lw=.6)
        ax.set_title('Horas de ciclismo por semana (lun–dom) — últimas 17 semanas', loc='left', fontsize=10, color='#0b0b0b')
        fig.tight_layout()
        _guardar(fig, out, FICHEROS[1])
        plt.close(fig)
        # 3 Horas por mes de los tres últimos años
        b['y'], b['m'] = b.Fecha.dt.year, b.Fecha.dt.month
        t = b.pivot_table(index='m', columns='y', values='h', aggfunc='sum').reindex(range(1, 13)).fillna(0)
        fig, ax = plt.subplots(figsize=(8, 3.2))
        w, yy = .27, sorted(t.columns)[-3:]
        for k, (y, c) in enumerate(zip(yy, ['#b9b8b2', '#86b6ef', B][-len(yy):])):
            ax.bar(t.index + (k - (len(yy) - 1) / 2) * w, t[y], w - .03, color=c, label=str(y))
        ax.set_xticks(range(1, 13), MES)
        ax.set_ylabel('horas')
        if yy:
            ax.legend(frameon=False, ncol=3, loc='upper left')
        ax.grid(axis='y', color='#e6e5e0', lw=.6)
        ax.set_title('Horas de ciclismo por mes y año', loc='left', fontsize=10, color='#0b0b0b')
        fig.tight_layout()
        _guardar(fig, out, FICHEROS[2])
    finally:
        plt.close('all')


if __name__ == '__main__':
    from carga import cargar
    hasta = sys.argv[3] if len(sys.argv) > 3 else None
    df, pmc, _ = cargar(sys.argv[1], hasta)
    generar(sys.argv[2], df, pmc)
