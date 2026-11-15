"""Preparación de datos compartida por el modelado, el notebook de producción y la app.

Contiene las reglas de armonización (antigüedad, comodidades, administración) y la
función `construir_registro`, que convierte los datos que digita un usuario en la
fila exacta que espera el Pipeline entrenado.
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

from .geo_features import BBOX_BOGOTA, VARIABLES_CONTEO, VARIABLES_DISTANCIA, GeoIndex

OBJETIVO = "precio_venta"

# --------------------------------------------------------------------------- #
# Grupos de variables candidatas (cada variable = un bloque en la selección)
# --------------------------------------------------------------------------- #
# Numéricas con cola larga -> log1p + estandarización
VARS_LOG = ["area_m2", "administracion"] + VARIABLES_DISTANCIA
# Numéricas -> estandarización
VARS_NUM = ["habitaciones", "banos", "parqueaderos", "estrato", "latitud", "longitud"] + VARIABLES_CONTEO
# Categóricas -> one-hot (todas sus dummies entran o salen juntas)
VARS_CAT = ["antiguedad_rango", "localidad", "tipo_via_principal_cercana"]

RANGOS_ANTIGUEDAD = [
    "Nuevo / sobre planos",
    "Entre 0 y 5 años",
    "Entre 5 y 10 años",
    "Entre 10 y 20 años",
    "Más de 20 años",
    "Remodelado",
]

# Comodidades binarias: nombre -> (etiqueta para el formulario, patrón en texto normalizado)
COMODIDADES = {
    "tiene_ascensor": ("Ascensor", r"(?<!sin )ascensor"),
    "parqueadero_cubierto": ("Parqueadero cubierto", r"(?:parqueadero|garaje)[^.;]{0,40}cubierto"),
    "tiene_deposito": ("Depósito", r"deposito|cuarto util"),
    "tiene_balcon": ("Balcón", r"balcon"),
    "tiene_terraza": ("Terraza", r"terraza"),
    "tiene_chimenea": ("Chimenea", r"chimenea"),
    "tiene_estudio": ("Estudio o biblioteca", r"\bestudio\b|biblioteca"),
    "tiene_cuarto_servicio": ("Cuarto de servicio", r"(?:cuarto|alcoba|habitacion|bano) del? servicio"),
    "tiene_jacuzzi": ("Jacuzzi", r"jacuzzi"),
    "tiene_tina": ("Tina", r"\btina\b"),
    "tiene_vigilancia": ("Vigilancia / portería", r"vigilancia|porteria|celaduria"),
    "conjunto_cerrado": ("Conjunto cerrado", r"conjunto cerrado"),
    "tiene_piscina": ("Piscina", r"piscina"),
    "tiene_gimnasio": ("Gimnasio", r"gimnasio|\bgym\b"),
    "tiene_salon_comunal": ("Salón comunal", r"salon\s+comunal|salon social"),
    "tiene_bbq": ("Zona BBQ", r"bbq|barbacoa|asador"),
    "tiene_zona_infantil": ("Zona infantil", r"zona para ninos|parque infantil|zona infantil|juegos infantiles"),
    "tiene_zonas_verdes": ("Zonas verdes", r"zonas? verdes?"),
    "tiene_sauna_turco": ("Sauna / turco", r"sauna|turco"),
    "tiene_canchas": ("Canchas deportivas", r"cancha"),
}
VARS_BIN = list(COMODIDADES)

# Comodidades que ya venían estructuradas desde el EDA (se respetan cuando existen)
_BIN_DEL_EDA = ["tiene_jacuzzi", "tiene_tina", "parqueadero_cubierto"]
# Columnas de texto donde se buscan las comodidades
_COLS_TEXTO = [
    "titulo", "descripcion", "caracteristicas_interior",
    "caracteristicas_exterior", "caracteristicas_zona_comun",
]

VARIABLES_CANDIDATAS = VARS_LOG + VARS_NUM + VARS_BIN + VARS_CAT

ADMIN_MIN, ADMIN_MAX = 20_000, 8_000_000   # fuera de este rango la cuota se trata como error

ETIQUETAS = {
    "area_m2": "Área (m²)",
    "administracion": "Administración mensual ($)",
    "habitaciones": "Habitaciones",
    "banos": "Baños",
    "parqueaderos": "Parqueaderos",
    "estrato": "Estrato",
    "antiguedad_rango": "Antigüedad",
    "localidad": "Localidad",
    "latitud": "Latitud",
    "longitud": "Longitud",
    **{k: v[0] for k, v in COMODIDADES.items()},
}


def _normalizar(texto) -> str:
    """Minúsculas y sin tildes, para comparar textos de forma robusta."""
    if not isinstance(texto, str):
        return ""
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# --------------------------------------------------------------------------- #
# Armonizaciones
# --------------------------------------------------------------------------- #
def armonizar_antiguedad(valor):
    """Lleva la antigüedad a rangos categóricos comunes a Habi y Metrocuadrado.

    - Habi reporta años (número) -> se ubica en el rango correspondiente.
    - Metrocuadrado reporta rangos de texto -> se conservan.
    - 'Sobre planos', 'En construcción' y 'Para estrenar' -> 'Nuevo / sobre planos'.
    """
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return np.nan
    s = _normalizar(str(valor)).strip()
    if s in ("", "nan"):
        return np.nan
    try:
        anios = float(s)
    except ValueError:
        anios = None
    if anios is not None:
        if anios <= 5:
            return "Entre 0 y 5 años"
        if anios <= 10:
            return "Entre 5 y 10 años"
        if anios <= 20:
            return "Entre 10 y 20 años"
        return "Más de 20 años"
    if "remodel" in s:
        return "Remodelado"
    if "plano" in s or "construc" in s or "estrenar" in s or "nuevo" in s:
        return "Nuevo / sobre planos"
    if "mas de 20" in s:
        return "Más de 20 años"
    if "10 y 20" in s:
        return "Entre 10 y 20 años"
    if "5 y 10" in s:
        return "Entre 5 y 10 años"
    if "0 y 5" in s:
        return "Entre 0 y 5 años"
    return np.nan


def limpiar_administracion(valor):
    """Administración no positiva o absurda -> NaN (el Pipeline la imputa con la mediana)."""
    v = pd.to_numeric(valor, errors="coerce")
    if isinstance(v, pd.Series):
        return v.where((v >= ADMIN_MIN) & (v <= ADMIN_MAX))
    return v if (pd.notna(v) and ADMIN_MIN <= v <= ADMIN_MAX) else np.nan


def extraer_comodidades(df: pd.DataFrame) -> pd.DataFrame:
    """Crea las comodidades binarias a partir del texto del anuncio.

    Para jacuzzi, tina y parqueadero cubierto se respeta la columna estructurada del
    EDA cuando existe (Metrocuadrado) y se completa con el texto cuando falta (Habi).
    """
    texto = pd.Series("", index=df.index)
    for col in _COLS_TEXTO:
        if col in df.columns:
            texto = texto + " ; " + df[col].fillna("").astype(str)
    texto = texto.map(_normalizar)

    out = pd.DataFrame(index=df.index)
    for nombre, (_, patron) in COMODIDADES.items():
        desde_texto = texto.str.contains(patron, regex=True)
        if nombre in _BIN_DEL_EDA and nombre in df.columns:
            original = df[nombre].map({True: True, False: False, "True": True, "False": False})
            desde_texto = original.where(original.notna(), desde_texto).astype(bool)
        out[nombre] = desde_texto.astype(int)
    return out


def preparar_base(df: pd.DataFrame, geo: GeoIndex, verbose: bool = True) -> pd.DataFrame:
    """Aplica los filtros de calidad y construye todas las variables candidatas."""
    pasos = [("Base original", len(df))]
    d = df.copy()

    # 1) Solo apartamentos en venta (Habi no trae tipo_operacion: todo es venta)
    oper = d["tipo_operacion"].fillna("venta").str.strip().str.lower()
    d = d[(d["tipo_propiedad"] == "Apartamento") & (oper == "venta")]
    pasos.append(("Apartamentos en venta", len(d)))

    # 2) Coordenadas dentro de Bogotá
    la0, la1, lo0, lo1 = BBOX_BOGOTA
    d = d[d["latitud"].between(la0, la1) & d["longitud"].between(lo0, lo1)]
    pasos.append(("Coordenadas válidas", len(d)))

    # 3) Reglas de negocio contra errores de captura
    pm2 = d["precio_venta"] / d["area_m2"].where(d["area_m2"] > 0)
    d = d[
        d["area_m2"].between(15, 600)
        & d["precio_venta"].between(50e6, 15e9)
        & pm2.between(1e6, 30e6)
        & d["estrato"].between(1, 6)
        & (d["banos"] >= 1)
        & d["habitaciones"].between(1, 6)
    ]
    pasos.append(("Rangos plausibles de precio, área, estrato", len(d)))

    # 4) Anuncios duplicados (evita que el mismo inmueble quede en train y en test)
    d = d.drop_duplicates(subset=["descripcion", "precio_venta", "area_m2", "latitud", "longitud"])
    pasos.append(("Sin duplicados", len(d)))
    d = d.reset_index(drop=True)

    base = d[["fuente", "precio_venta", "area_m2", "habitaciones", "banos", "parqueaderos",
              "estrato", "latitud", "longitud"]].copy()
    base["administracion"] = limpiar_administracion(d["administracion"])
    base["antiguedad_rango"] = d["antiguedad"].map(armonizar_antiguedad)
    base["localidad"] = d["localidad"].str.strip().str.upper()
    base = pd.concat([base, extraer_comodidades(d)], axis=1)

    # 5) Variables de ubicación con la MISMA función que usa producción
    geo_vars = geo.calcular_variables(base["latitud"].to_numpy(), base["longitud"].to_numpy())
    base = pd.concat([base, geo_vars], axis=1)

    if verbose:
        for nombre, n in pasos:
            print(f"{nombre:<45} {n:>7,}")
    return base


# --------------------------------------------------------------------------- #
# Producción: de los datos del usuario a la fila que espera el Pipeline
# --------------------------------------------------------------------------- #
def construir_registro(datos: dict, geo: GeoIndex) -> pd.DataFrame:
    """Convierte los datos de un apartamento nuevo en una fila lista para `modelo.predict`.

    `datos` debe traer latitud y longitud (la app las obtiene de la dirección) y las
    características del inmueble. Lo que falte queda como NaN (lo imputa el Pipeline)
    o como 0 en el caso de las comodidades.
    """
    lat, lon = float(datos["latitud"]), float(datos["longitud"])
    la0, la1, lo0, lo1 = BBOX_BOGOTA
    if not (la0 <= lat <= la1 and lo0 <= lon <= lo1):
        raise ValueError("La ubicación está fuera de Bogotá.")

    fila = {"latitud": lat, "longitud": lon}
    for var in ["area_m2", "habitaciones", "banos", "parqueaderos", "estrato"]:
        fila[var] = pd.to_numeric(datos.get(var), errors="coerce")
    fila["administracion"] = limpiar_administracion(datos.get("administracion"))
    fila["antiguedad_rango"] = armonizar_antiguedad(
        datos.get("antiguedad_rango", datos.get("antiguedad"))
    )
    localidad = datos.get("localidad")
    if not localidad or str(localidad).lower() in ("auto", "nan", "none"):
        localidad = geo.localidad_probable(lat, lon)
    fila["localidad"] = str(localidad).strip().upper() if localidad else np.nan
    for var in VARS_BIN:
        v = datos.get(var, 0)
        fila[var] = int(str(v).strip().lower() in ("1", "true", "si", "sí", "on", "yes"))

    registro = pd.concat([pd.DataFrame([fila]), geo.calcular_variables(lat, lon)], axis=1)
    return registro
