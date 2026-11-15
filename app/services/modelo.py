"""Carga del modelo entrenado y predicción del precio de un apartamento."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd

from modelado.src.geo_features import ETIQUETAS_CATEGORIA, GeoIndex
from modelado.src.preparacion import construir_registro

# Los artefactos se leen directamente de la carpeta de salida del modelado
DIR_OUTPUT = Path(__file__).resolve().parents[2] / "modelado" / "output"

ETIQUETAS_GEO = {
    "dist_estacion_m": "Distancia a estación de TransMilenio (m)",
    "dist_parque_m": "Distancia al parque más cercano (m)",
    "dist_via_principal_m": "Distancia a vía principal (m)",
    "latitud": "Latitud",
    "longitud": "Longitud",
    "tipo_via_principal_cercana": "Tipo de vía principal cercana",
    **{f"dist_{c}_m": f"Distancia a {e.lower()} (m)" for c, e in ETIQUETAS_CATEGORIA.items()},
    **{f"{c}_500m": f"{e} a 500 m" for c, e in ETIQUETAS_CATEGORIA.items()},
    "vias_principales_500m": "Vías principales a 500 m",
}


class ServicioModelo:
    """Mantiene en memoria el Pipeline, las capas geográficas y los metadatos."""

    def __init__(self, dir_output: Path = DIR_OUTPUT):
        self.modelo = joblib.load(dir_output / "modelo_final.joblib")
        self.geo = GeoIndex.cargar(dir_output / "capas_geo.joblib")
        self.metadata = json.loads((dir_output / "metadata.json").read_text(encoding="utf-8"))
        self.campos = {c["nombre"]: c for c in self.metadata["campos_formulario"]}

    # ------------------------------------------------------------------ #
    def configuracion(self) -> dict:
        """Lo que necesita el front para construir el formulario."""
        m = self.metadata
        return {
            "modelo": m["modelo"],
            "descripcion": m["descripcion"],
            "fecha_entrenamiento": m["fecha_entrenamiento"],
            "n_train": m["n_train"],
            "campos": m["campos_formulario"],
            "variables_automaticas": [
                {"nombre": v, "etiqueta": ETIQUETAS_GEO.get(v, v)}
                for v in m["variables_calculadas_con_la_direccion"]
            ],
            "metricas": m["metricas_test"],
        }

    def _validar(self, datos: dict) -> list[str]:
        """Revisa los datos obligatorios y devuelve advertencias por valores fuera de rango."""
        advertencias = []
        for nombre, campo in self.campos.items():
            if campo["tipo"] != "numero":
                continue
            valor = pd.to_numeric(datos.get(nombre), errors="coerce")
            if pd.isna(valor):
                if campo.get("opcional"):
                    continue
                raise ValueError(f"Falta el dato: {campo['etiqueta']}.")
            if valor <= 0 and nombre in ("area_m2", "banos", "habitaciones", "estrato"):
                raise ValueError(f"{campo['etiqueta']} debe ser mayor que cero.")
            if valor < campo["minimo"] or valor > campo["maximo"]:
                advertencias.append(
                    f"{campo['etiqueta']} ({valor:,.0f}) está fuera del rango con el que se entrenó "
                    f"el modelo ({campo['minimo']:,.0f} – {campo['maximo']:,.0f}); la estimación es menos confiable."
                )
        return advertencias

    def predecir(self, datos: dict) -> dict:
        """Precio estimado, rango del 80 %, variables calculadas y entorno para el mapa."""
        advertencias = self._validar(datos)
        registro = construir_registro(datos, self.geo)
        precio = float(self.modelo.predict(registro)[0])
        banda = self.metadata["banda_80"]
        fila = registro.iloc[0]
        lat, lon = float(fila["latitud"]), float(fila["longitud"])

        if pd.isna(fila["administracion"]) and "administracion" in self.campos:
            advertencias.append(
                "No se indicó una administración válida: se usó la mediana de los apartamentos de entrenamiento."
            )

        return {
            "precio": round(precio),
            "precio_min": round(precio * banda["factor_inferior"]),
            "precio_max": round(precio * banda["factor_superior"]),
            "precio_m2": round(precio / float(fila["area_m2"])),
            "localidad": fila["localidad"],
            "antiguedad_rango": fila["antiguedad_rango"],
            "latitud": lat,
            "longitud": lon,
            "variables_calculadas": [
                {
                    "nombre": v,
                    "etiqueta": ETIQUETAS_GEO.get(v, v),
                    "valor": fila[v] if isinstance(fila[v], str) else round(float(fila[v]), 5 if v in ("latitud", "longitud") else 1),
                }
                for v in self.metadata["variables_calculadas_con_la_direccion"]
            ],
            "entorno": self.geo.describir_entorno(lat, lon, radio_m=500),
            "advertencias": advertencias,
            "mape": self.metadata["metricas_test"]["MAPE"],
        }
