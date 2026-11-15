
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

R_TIERRA_M = 6_371_008.8          # radio medio de la Tierra (m)
RADIO_CONTEO_M = 500              # radio de los conteos de equipamientos
PASO_DENSIFICAR_M = 20            # separación de puntos sobre bordes de parques y vías
BBOX_BOGOTA = (4.40, 4.95, -74.30, -73.90)   # lat_min, lat_max, lon_min, lon_max

# Categorías de puntos OSM -> subtipos de la capa original (None = toda la capa)
CATEGORIAS_OSM = {
    "hospitales_clinicas": ("salud", {"hospital", "clinic", "doctors"}),
    "farmacias": ("salud", {"pharmacy"}),
    "educacion": ("educacion", None),
    "comercio": ("comercio", None),
    "transporte": ("transporte", None),
    "recreacion": ("recreacion", None),
    "religion": ("religion", None),
    "factores_negativos": ("factores_negativos", None),
}

ETIQUETAS_CATEGORIA = {
    "hospitales_clinicas": "Hospitales y clínicas",
    "farmacias": "Farmacias",
    "educacion": "Educación",
    "comercio": "Comercio",
    "transporte": "Paraderos de transporte",
    "recreacion": "Recreación y deporte",
    "religion": "Iglesias",
    "factores_negativos": "Factores negativos",
}

# Nombres de las variables numéricas que produce `calcular_variables`
VARIABLES_DISTANCIA = (
    ["dist_estacion_m", "dist_parque_m"]
    + [f"dist_{c}_m" for c in CATEGORIAS_OSM]
    + ["dist_via_principal_m"]
)
VARIABLES_CONTEO = [f"{c}_{RADIO_CONTEO_M}m" for c in CATEGORIAS_OSM] + [
    f"vias_principales_{RADIO_CONTEO_M}m"
]


# --------------------------------------------------------------------------- #
# Utilidades geométricas
# --------------------------------------------------------------------------- #
def haversine_m(lat1, lon1, lat2, lon2):
    """Distancia Haversine en metros entre pares de coordenadas (grados)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * R_TIERRA_M * np.arcsin(np.sqrt(a))


def _a_radianes(lat, lon):
    return np.radians(np.column_stack([np.asarray(lat, float), np.asarray(lon, float)]))


def _densificar(coords, paso_m=PASO_DENSIFICAR_M):
    """Agrega puntos intermedios cada `paso_m` metros a una línea [(lat, lon), ...].

    Permite aproximar la distancia a un borde de parque o a una vía con la
    distancia al punto más cercano de la línea (error máximo ~ paso_m / 2).
    """
    coords = np.asarray(coords, float)
    if len(coords) < 2:
        return coords
    largo = haversine_m(coords[:-1, 0], coords[:-1, 1], coords[1:, 0], coords[1:, 1])
    n = np.maximum(1, np.ceil(largo / paso_m).astype(int))
    idx = np.repeat(np.arange(len(n)), n)
    inicio = np.cumsum(n) - n
    t = (np.arange(n.sum()) - inicio[idx]) / n[idx]
    puntos = coords[:-1][idx] + (coords[1:] - coords[:-1])[idx] * t[:, None]
    return np.vstack([puntos, coords[-1:]])


_MARCAS_MOJIBAKE = set("µ¢‚Ãöÿ\x90\xa0ãÖà")


def _corregir_texto(s):
    """Repara nombres de parques con caracteres dañados por una codificación antigua."""
    if not isinstance(s, str):
        return "Parque sin nombre"
    if not any(ch in _MARCAS_MOJIBAKE for ch in s):
        return s
    try:
        arreglado = s.encode("cp1252").decode("cp850")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
    return s if any(ord(c) < 32 for c in arreglado) else arreglado


def _en_bbox(lat, lon, margen=0.0):
    la0, la1, lo0, lo1 = BBOX_BOGOTA
    return (la0 - margen <= lat <= la1 + margen) and (lo0 - margen <= lon <= lo1 + margen)


# --------------------------------------------------------------------------- #
# Lectura de las capas crudas (carpeta modelado/input)
# --------------------------------------------------------------------------- #
def cargar_capas_crudas(dir_input) -> dict:
    """Lee los archivos geográficos de `modelado/input` y los deja en arreglos compactos."""
    dir_input = Path(dir_input)

    # --- Estaciones de TransMilenio (puntos)
    with open(dir_input / "estaciones_transmilenio.geojson", encoding="utf-8") as f:
        est = json.load(f)["features"]
    estaciones = {
        "nombre": [e["properties"].get("nom_est") or "Estación" for e in est],
        "lat": np.array([e["geometry"]["coordinates"][1] for e in est], float),
        "lon": np.array([e["geometry"]["coordinates"][0] for e in est], float),
    }

    # --- Parques (polígonos): borde densificado para medir + anillos para dibujar
    with open(dir_input / "parques_bogota.geojson", encoding="utf-8") as f:
        parques_raw = json.load(f)["features"]
    nombres, anillos, anillo_parque, pts, pts_parque = [], [], [], [], []
    for feat in parques_raw:
        geom = feat.get("geometry")
        if not geom:
            continue
        poligonos = geom["coordinates"] if geom["type"] == "Polygon" else [
            p for p in geom["coordinates"]
        ]
        if geom["type"] == "Polygon":
            poligonos = [poligonos]
        lon0, lat0 = poligonos[0][0][0][:2]
        if not _en_bbox(lat0, lon0):
            continue
        k = len(nombres)
        nombres.append(_corregir_texto(feat["properties"].get("Nombre_Par")))
        for poligono in poligonos:
            for j, anillo in enumerate(poligono):
                c = np.array([[p[1], p[0]] for p in anillo], float)   # (lat, lon)
                d = _densificar(c)
                pts.append(d)
                pts_parque.append(np.full(len(d), k, dtype=np.int32))
                if j == 0:   # solo el anillo exterior se dibuja en el mapa
                    anillos.append(np.round(c, 5).astype(np.float32))
                    anillo_parque.append(k)
    pts = np.vstack(pts)
    parques = {
        "nombre": nombres,
        "pt_lat": pts[:, 0].astype(np.float32),
        "pt_lon": pts[:, 1].astype(np.float32),
        "pt_parque": np.concatenate(pts_parque),
        "anillos": anillos,
        "anillo_parque": np.array(anillo_parque, dtype=np.int32),
    }

    # --- Equipamientos OSM (puntos)
    with open(dir_input / "capas_osm_puntos.json", encoding="utf-8") as f:
        osm = json.load(f)
    puntos = {}
    for cat, (capa, subtipos) in CATEGORIAS_OSM.items():
        elems = [p for p in osm.get(capa, []) if subtipos is None or p.get("subtipo") in subtipos]
        puntos[cat] = {
            "lat": np.array([p["lat"] for p in elems], float),
            "lon": np.array([p["lon"] for p in elems], float),
            "nombre": [p.get("nombre") or "Sin nombre" for p in elems],
            "subtipo": [p.get("subtipo") or "" for p in elems],
        }

    # --- Vías principales (líneas densificadas)
    with open(dir_input / "capas_osm_vias.geojson", encoding="utf-8") as f:
        vias_raw = json.load(f)["features"]
    nombres_via, idx_nombre = [], {}
    tipos_via = ["trunk", "primary", "secondary", "motorway", "sin_clasificar"]
    v_pts, v_nombre, v_tipo = [], [], []
    for feat in vias_raw:
        geom = feat.get("geometry")
        if not geom:
            continue
        lineas = [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
        nombre = feat["properties"].get("nombre") or "Sin nombre"
        tipo = feat["properties"].get("tipo") or "sin_clasificar"
        tipo = tipo if tipo in tipos_via else "sin_clasificar"
        k = idx_nombre.setdefault(nombre, len(nombres_via))
        if k == len(nombres_via):
            nombres_via.append(nombre)
        for linea in lineas:
            d = _densificar(np.array([[p[1], p[0]] for p in linea], float))
            v_pts.append(d)
            v_nombre.append(np.full(len(d), k, dtype=np.int32))
            v_tipo.append(np.full(len(d), tipos_via.index(tipo), dtype=np.int8))
    v_pts = np.vstack(v_pts)
    vias = {
        "nombres": nombres_via,
        "tipos": tipos_via,
        "pt_lat": v_pts[:, 0].astype(np.float32),
        "pt_lon": v_pts[:, 1].astype(np.float32),
        "pt_nombre": np.concatenate(v_nombre),
        "pt_tipo": np.concatenate(v_tipo),
    }
    return {"estaciones": estaciones, "parques": parques, "puntos": puntos, "vias": vias}


# --------------------------------------------------------------------------- #
# Índice espacial
# --------------------------------------------------------------------------- #
class GeoIndex:
    """Índice espacial (BallTree Haversine) sobre estaciones, parques, equipamientos y vías."""

    def __init__(self, capas: dict):
        self.capas = capas
        e, p, v = capas["estaciones"], capas["parques"], capas["vias"]
        self._arbol_est = BallTree(_a_radianes(e["lat"], e["lon"]), metric="haversine")
        self._arbol_parq = BallTree(_a_radianes(p["pt_lat"], p["pt_lon"]), metric="haversine")
        self._arbol_vias = BallTree(_a_radianes(v["pt_lat"], v["pt_lon"]), metric="haversine")
        self._arbol_cat = {
            c: BallTree(_a_radianes(d["lat"], d["lon"]), metric="haversine")
            for c, d in capas["puntos"].items()
        }
        self._arbol_loc = None
        if capas.get("referencia_localidad"):
            r = capas["referencia_localidad"]
            self._arbol_loc = BallTree(_a_radianes(r["lat"], r["lon"]), metric="haversine")

    # ---- construcción / persistencia
    @classmethod
    def desde_archivos_crudos(cls, dir_input):
        return cls(cargar_capas_crudas(dir_input))

    @classmethod
    def cargar(cls, ruta):
        return cls(joblib.load(ruta))

    def guardar(self, ruta):
        joblib.dump(self.capas, ruta, compress=3)

    def registrar_referencia_localidad(self, lat, lon, localidad):
        """Guarda viviendas de referencia para inferir la localidad de un punto nuevo."""
        self.capas["referencia_localidad"] = {
            "lat": np.asarray(lat, np.float32),
            "lon": np.asarray(lon, np.float32),
            "localidad": list(localidad),
        }
        r = self.capas["referencia_localidad"]
        self._arbol_loc = BallTree(_a_radianes(r["lat"], r["lon"]), metric="haversine")

    # ---- variables del modelo
    def calcular_variables(self, lat, lon) -> pd.DataFrame:
        """Calcula las variables de ubicación para uno o varios puntos (vectorizado)."""
        lat = np.atleast_1d(np.asarray(lat, float))
        lon = np.atleast_1d(np.asarray(lon, float))
        X = _a_radianes(lat, lon)
        r = RADIO_CONTEO_M / R_TIERRA_M
        out = {}

        d, i = self._arbol_est.query(X, k=1)
        out["estacion"] = [self.capas["estaciones"]["nombre"][k] for k in i[:, 0]]
        out["dist_estacion_m"] = np.round(d[:, 0] * R_TIERRA_M, 1)

        d, i = self._arbol_parq.query(X, k=1)
        parq = self.capas["parques"]
        out["parque"] = [parq["nombre"][k] for k in parq["pt_parque"][i[:, 0]]]
        out["dist_parque_m"] = np.round(d[:, 0] * R_TIERRA_M, 1)

        for cat, arbol in self._arbol_cat.items():
            d, _ = arbol.query(X, k=1)
            out[f"dist_{cat}_m"] = np.round(d[:, 0] * R_TIERRA_M, 1)
            out[f"{cat}_{RADIO_CONTEO_M}m"] = arbol.query_radius(X, r=r, count_only=True)

        vias = self.capas["vias"]
        d, i = self._arbol_vias.query(X, k=1)
        out["via_principal_cercana"] = [vias["nombres"][k] for k in vias["pt_nombre"][i[:, 0]]]
        out["tipo_via_principal_cercana"] = [vias["tipos"][k] for k in vias["pt_tipo"][i[:, 0]]]
        out["dist_via_principal_m"] = np.round(d[:, 0] * R_TIERRA_M, 1)
        cercanas = self._arbol_vias.query_radius(X, r=r)
        # número de vías principales distintas (por nombre) dentro del radio
        out[f"vias_principales_{RADIO_CONTEO_M}m"] = [
            len(np.unique(vias["pt_nombre"][idx])) for idx in cercanas
        ]
        return pd.DataFrame(out)

    def localidad_probable(self, lat, lon, k=15):
        """Localidad más frecuente entre las k viviendas de referencia más cercanas."""
        if self._arbol_loc is None:
            return None
        _, i = self._arbol_loc.query(_a_radianes([lat], [lon]), k=k)
        loc = pd.Series([self.capas["referencia_localidad"]["localidad"][j] for j in i[0]])
        return loc.mode().iloc[0]

    # ---- detalle del entorno para dibujar el mapa
    def describir_entorno(self, lat, lon, radio_m=RADIO_CONTEO_M) -> dict:
        """Estación y parque más cercanos, vía principal y equipamientos dentro del radio."""
        X = _a_radianes([lat], [lon])
        r = radio_m / R_TIERRA_M
        est, parq, vias = self.capas["estaciones"], self.capas["parques"], self.capas["vias"]

        d, i = self._arbol_est.query(X, k=1)
        k = int(i[0, 0])
        estacion = {
            "nombre": est["nombre"][k], "lat": float(est["lat"][k]), "lon": float(est["lon"][k]),
            "dist_m": round(float(d[0, 0] * R_TIERRA_M), 1),
        }

        d, i = self._arbol_parq.query(X, k=1)
        j = int(i[0, 0])
        k_parque = int(parq["pt_parque"][j])
        parque = {
            "nombre": parq["nombre"][k_parque],
            "lat": float(parq["pt_lat"][j]), "lon": float(parq["pt_lon"][j]),
            "dist_m": round(float(d[0, 0] * R_TIERRA_M), 1),
        }

        # polígonos de los parques que tocan el radio (más el parque más cercano)
        dentro = self._arbol_parq.query_radius(X, r=r)[0]
        ids = set(np.unique(parq["pt_parque"][dentro]).tolist()) | {k_parque}
        poligonos = []
        for a, kp in zip(parq["anillos"], parq["anillo_parque"]):
            if int(kp) in ids:
                poligonos.append({
                    "nombre": parq["nombre"][int(kp)],
                    "cercano": int(kp) == k_parque,
                    "coords": a[:: max(1, len(a) // 400)].tolist(),
                })

        d, i = self._arbol_vias.query(X, k=1)
        j = int(i[0, 0])
        via = {
            "nombre": vias["nombres"][int(vias["pt_nombre"][j])],
            "tipo": vias["tipos"][int(vias["pt_tipo"][j])],
            "lat": float(vias["pt_lat"][j]), "lon": float(vias["pt_lon"][j]),
            "dist_m": round(float(d[0, 0] * R_TIERRA_M), 1),
        }

        amenidades = {}
        for cat, arbol in self._arbol_cat.items():
            idx, dist = arbol.query_radius(X, r=r, return_distance=True, sort_results=True)
            datos = self.capas["puntos"][cat]
            amenidades[cat] = {
                "etiqueta": ETIQUETAS_CATEGORIA[cat],
                "elementos": [
                    {
                        "nombre": datos["nombre"][int(m)], "subtipo": datos["subtipo"][int(m)],
                        "lat": float(datos["lat"][m]), "lon": float(datos["lon"][m]),
                        "dist_m": round(float(dm * R_TIERRA_M)),
                    }
                    for m, dm in zip(idx[0], dist[0])
                ],
            }
        return {
            "radio_m": radio_m, "estacion": estacion, "parque": parque, "via": via,
            "parques_poligonos": poligonos, "amenidades": amenidades,
        }
