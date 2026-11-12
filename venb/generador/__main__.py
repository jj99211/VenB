"""Uso:  python -m generador proyecto.toml [tabla] [infografia] [mapa] [web]

Sin argumentos tras el .toml genera todo.
"""
import sys

from .proyecto import Proyecto, exportar_excel, fmt_dur, fmt_hora


def main(args):
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    proyecto = Proyecto(args[0])
    que = set(args[1:]) or {"tabla", "infografia", "mapa", "web"}

    from . import __version__
    print(f"== {proyecto.nombre}  (generador {__version__})")
    plan = proyecto.calcular()
    print(f"  {plan.total_km:.1f} km · +{plan.total_asc:.0f} m · llegada "
          f"{plan.llegada_final:%d/%m %H:%M} · margen en meta {fmt_dur(plan.puntos[-1].margen, True)}")
    for aviso in plan.avisos:
        print(f"  aviso: {aviso}")
    if plan.anclas:
        print(f"  km de la hoja ajustados al GPX con {plan.anclas} waypoints de control")
    for p in plan.controles:
        aviso = "  <-- FUERA DE CIERRE" if p.margen.total_seconds() < 0 else ""
        if p.antes_de_apertura:
            aviso += f"  <-- llega antes de la apertura ({fmt_hora(p.apertura_hoja)})"
        print(f"  {p.control:>4} {p.nombre[:24]:24} km {p.km:6.1f}  {p.llegada:%d} {fmt_hora(p.llegada)}"
              f"  cierre {fmt_hora(p.cierre)}  margen {fmt_dur(p.margen, True):>6}{aviso}")

    hechos = []
    if "tabla" in que:
        ruta = proyecto.salida_dir / "tabla_tiempos.xlsx"
        exportar_excel(plan, ruta)
        hechos.append(ruta)
    osm = None
    if que & {"infografia", "mapa"}:
        from .osm import elementos
        tr = plan.track
        try:
            osm = elementos(tr, (tr.lat.min() - 0.4, tr.lon.min() - 0.6,
                                 tr.lat.max() + 0.4, tr.lon.max() + 0.6))
        except Exception as e:
            print(f"  aviso: sin datos de Overpass ({e})")
    if "infografia" in que:
        from .infografia import generar
        hechos += generar(proyecto, plan, osm)
    if "mapa" in que:
        from .ilustrado import generar as generar_mapa
        hechos += generar_mapa(proyecto, plan, osm)
    if "web" in que:
        from .web import generar as generar_web
        hechos.append(generar_web(proyecto, plan))
    print("Ficheros generados:")
    for h in hechos:
        print(f"  {h}")


if __name__ == "__main__":
    main(sys.argv[1:])
