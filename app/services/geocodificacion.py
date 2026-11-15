"""Convierte una dirección de Bogotá en latitud/longitud.

Se consulta primero el geocodificador mundial de ArcGIS (entiende bien la
nomenclatura colombiana "Calle 94 # 18 - 65") y, si falla, Nominatim (OpenStreetMap).
Ninguno requiere llave de acceso.
"""
from __future__ import annotations

import re

import requests

from modelado.src.geo_features import BBOX_BOGOTA

LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = BBOX_BOGOTA
CABECERAS = {"User-Agent": "prediccion-vivienda-bogota/1.0 (aplicacion academica)"}
TIEMPO_MAX = 8  # segundos


def _dentro_de_bogota(lat: float, lon: float) -> bool:
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX


def _normalizar(direccion: str) -> str:
    """Limpia la dirección y le agrega la ciudad si el usuario no la escribió."""
    d = re.sub(r"\s+", " ", direccion).strip()
    d = re.sub(r"\bN[o°º]\.?\s*", "# ", d, flags=re.IGNORECASE)
    if "bogot" not in d.lower():
        d += ", Bogotá"
    return d + ", Colombia"


def _arcgis(direccion: str):
    r = requests.get(
        "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
        params={
            "f": "json", "SingleLine": direccion, "countryCode": "COL", "maxLocations": 5,
            "outFields": "Match_addr,Addr_type",
            "searchExtent": f"{LON_MIN},{LAT_MIN},{LON_MAX},{LAT_MAX}",
        },
        headers=CABECERAS, timeout=TIEMPO_MAX,
    )
    r.raise_for_status()
    for c in r.json().get("candidates", []):
        lat, lon = c["location"]["y"], c["location"]["x"]
        if c.get("score", 0) >= 70 and _dentro_de_bogota(lat, lon):
            return {
                "latitud": lat, "longitud": lon, "direccion_encontrada": c.get("address", direccion),
                "precision": c.get("attributes", {}).get("Addr_type", ""), "fuente": "ArcGIS",
            }
    return None


def _nominatim(direccion: str):
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": direccion, "format": "jsonv2", "limit": 5, "countrycodes": "co",
            "viewbox": f"{LON_MIN},{LAT_MAX},{LON_MAX},{LAT_MIN}", "bounded": 1,
        },
        headers=CABECERAS, timeout=TIEMPO_MAX,
    )
    r.raise_for_status()
    for c in r.json():
        lat, lon = float(c["lat"]), float(c["lon"])
        if _dentro_de_bogota(lat, lon):
            return {
                "latitud": lat, "longitud": lon, "direccion_encontrada": c.get("display_name", direccion),
                "precision": c.get("type", ""), "fuente": "OpenStreetMap",
            }
    return None


def geocodificar(direccion: str) -> dict | None:
    """Devuelve la mejor coincidencia dentro de Bogotá, o None si no se encuentra."""
    if not direccion or len(direccion.strip()) < 4:
        return None
    consulta = _normalizar(direccion)
    for servicio in (_arcgis, _nominatim):
        try:
            resultado = servicio(consulta)
        except (requests.RequestException, ValueError, KeyError):
            resultado = None
        if resultado:
            return resultado
    return None
