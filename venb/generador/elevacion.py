"""Altitudes desde un modelo digital del terreno (OpenTopoData), con caché en disco.

Los tracks exportados por Garmin Connect y similares traen la altitud muy
suavizada y subestiman el desnivel; el MDT europeo de 25 m da cifras más realistas.
"""
import hashlib
import sys
import time
from pathlib import Path

import numpy as np

from . import CACHE as _CACHE
import requests

CACHE = _CACHE / "altitudes"
URL = "https://api.opentopodata.org/v1/{dataset}"
AGENTE = {"User-Agent": "generador-mapas-bici/0.1 (uso personal)"}


def altitudes_mdt(lat, lon, dataset="eudem25m", lote=100, pausa=1.05):
    """Devuelve la altitud del MDT para cada coordenada (np.nan si no hay dato)."""
    clave = hashlib.sha1(np.round(np.c_[lat, lon], 6).tobytes() + dataset.encode()).hexdigest()[:16]
    fichero = CACHE / f"{dataset}_{clave}.npy"
    if fichero.exists():
        return np.load(fichero)

    CACHE.mkdir(parents=True, exist_ok=True)
    salida = np.full(len(lat), np.nan)
    n_lotes = (len(lat) + lote - 1) // lote
    for n, i in enumerate(range(0, len(lat), lote)):
        loc = "|".join(f"{a:.6f},{b:.6f}" for a, b in zip(lat[i:i + lote], lon[i:i + lote]))
        for intento in range(4):
            r = requests.post(URL.format(dataset=dataset), data={"locations": loc},
                              headers=AGENTE, timeout=60)
            if r.status_code == 429:
                time.sleep(5 * (intento + 1))
                continue
            r.raise_for_status()
            break
        datos = r.json()
        if datos.get("status") != "OK":
            raise RuntimeError(f"OpenTopoData: {datos}")
        salida[i:i + lote] = [np.nan if x["elevation"] is None else x["elevation"]
                              for x in datos["results"]]
        print(f"\r  altitudes MDT: lote {n + 1}/{n_lotes}", end="", file=sys.stderr, flush=True)
        time.sleep(pausa)
    print(file=sys.stderr)
    # puntos fuera de la cobertura del MDT (mar, otro país…): se interpolan
    ok = ~np.isnan(salida)
    if ok.any() and not ok.all():
        salida[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), salida[ok])
    np.save(fichero, salida)
    return salida
