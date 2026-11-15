"""Aplicación web: estimador del precio de apartamentos en Bogotá.

Rutas
-----
GET  /                    página con el formulario y el mapa
GET  /api/config          campos del formulario (salen de los metadatos del modelo)
GET  /api/geocodificar    dirección -> latitud / longitud
POST /api/predecir        datos del inmueble -> precio estimado + entorno para el mapa
GET  /salud               verificación de que el servicio está arriba (Render)

Ejecución local:   python -m app.app
Producción:        gunicorn app.app:app
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Permite importar el paquete `modelado` (código compartido con los notebooks)
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.services.geocodificacion import geocodificar  # noqa: E402
from app.services.modelo import ServicioModelo  # noqa: E402

app = Flask(__name__)
app.json.ensure_ascii = False
servicio = ServicioModelo()   # carga el modelo y las capas geográficas una sola vez


@app.get("/")
def inicio():
    return render_template("index.html")


@app.get("/salud")
def salud():
    return jsonify(estado="ok", modelo=servicio.metadata["modelo"])


@app.get("/api/config")
def config():
    return jsonify(servicio.configuracion())


@app.get("/api/geocodificar")
def api_geocodificar():
    resultado = geocodificar(request.args.get("direccion", ""))
    if resultado is None:
        return jsonify(error="No se encontró la dirección en Bogotá. Revísela o ubique el punto "
                             "haciendo clic en el mapa."), 404
    resultado["localidad"] = servicio.geo.localidad_probable(resultado["latitud"], resultado["longitud"])
    return jsonify(resultado)


@app.post("/api/predecir")
def api_predecir():
    datos = request.get_json(silent=True) or {}
    if datos.get("latitud") in (None, "") or datos.get("longitud") in (None, ""):
        return jsonify(error="Primero ubique el inmueble: escriba la dirección o haga clic en el mapa."), 400
    try:
        return jsonify(servicio.predecir(datos))
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
