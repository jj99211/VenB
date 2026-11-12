"""Generador de infografías y mapas de rutas en bici (motor del Planificador de VenB).
Procede del proyecto GENERADOR_MAPAS, versión 3.2."""
import os
from pathlib import Path

__version__ = "3.2"
# Caché de teselas, altitudes y OpenStreetMap: VenB la pone en ~/.venb/mapas/cache
CACHE = Path(os.environ.get("GENERADOR_CACHE") or Path(__file__).parent / "cache")
