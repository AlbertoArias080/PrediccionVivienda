# Predicción del precio de venta de apartamentos en Bogotá

Taller de Regresión y Regularización (Parte II) · Grupo B
Machine Learning Probabilístico · Especialización en Analítica Estratégica de Datos · Fundación Universitaria Konrad Lorenz

El proyecto tiene dos partes que comparten el mismo código de transformación:

1. **`modelado/`** — notebooks del taller: entrenan y comparan cinco modelos de regresión y exportan el modelo final.
2. **`app/`** — aplicación web (Flask) que recibe los datos de un apartamento, estima su precio con el modelo entrenado y muestra en un mapa la ubicación, la estación de TransMilenio y el parque más cercanos y las amenidades en un radio de hasta 500 m.

## Estructura

```
prediccion-vivienda-bogota/
├── modelado/
│   ├── input/                          datos de entrada
│   │   ├── base_depurada.csv               base depurada Habi + Metrocuadrado (salida del Taller de EDA)
│   │   ├── estaciones_transmilenio.geojson
│   │   ├── parques_bogota.geojson
│   │   ├── capas_osm_puntos.json           equipamientos (salud, educación, comercio…)
│   │   └── capas_osm_vias.geojson          vías principales
│   ├── output/                         artefactos que genera el notebook 01
│   │   ├── modelo_final.joblib             Pipeline entrenado (preprocesamiento + regresión)
│   │   ├── capas_geo.joblib                capas geográficas compactas para producción
│   │   ├── metadata.json                   campos del formulario, métricas, versiones
│   │   ├── ejemplo_entrada.json            ejemplo de datos de entrada
│   │   ├── tabla_comparativa.csv           métricas de los 5 modelos (train y test)
│   │   ├── coeficientes_modelo_final.csv
│   │   └── variables_seleccionadas.csv     Forward vs. Backward vs. Lasso
│   ├── src/                            código compartido con la app
│   │   ├── preparacion.py                  limpieza, armonización y `construir_registro`
│   │   └── geo_features.py                 distancias Haversine y conteos por radio
│   ├── respaldo_base_anterior/         notebook 01 y artefactos del modelo entrenado con la base anterior
│   ├── 01_modelado_regresion.ipynb     notebook del taller (modelado y evaluación)
│   ├── 02_produccion.ipynb             notebook de puesta en producción (no reentrena)
│   └── requirements.txt                librerías para los notebooks
├── app/
│   ├── app.py                          rutas Flask
│   ├── services/
│   │   ├── modelo.py                       carga del modelo y predicción
│   │   └── geocodificacion.py              dirección → latitud / longitud
│   ├── templates/index.html            página
│   └── static/
│       ├── css/estilos.css
│       └── js/app.js                       formulario dinámico y mapa (Leaflet)
├── informe/
│   ├── informe_taller_regresion.pdf    informe escrito (2 páginas)
│   └── generar_informe.py              script que genera el PDF (requiere reportlab)
├── requirements.txt                    librerías de la app (producción)
├── render.yaml                         configuración de despliegue en Render
└── README.md
```

## Resultados del modelado

| Modelo | Variables | MAE prueba | RMSE prueba | R² prueba |
|---|---|---|---|---|
| Base (OLS) | 42 | $241,0 M | $512,1 M | 0,859 |
| **Forward (BIC) — modelo final** | **19** | **$240,1 M** | **$508,2 M** | **0,861** |
| Backward (BIC) | 19 | $240,0 M | $508,5 M | 0,861 |
| Ridge | 42 | $247,4 M | $536,4 M | 0,845 |
| Lasso | 26 | $247,2 M | $534,5 M | 0,846 |

Los modelos se entrenan con la base depurada del Taller de EDA (10.224 apartamentos; 8.179 de entrenamiento y 2.045 de prueba, con la misma división del EDA). Los cinco predicen prácticamente igual; se eligió el de selección Forward (coincide con Backward en 18 de sus 19 variables) por usar menos de la mitad de las variables. La justificación completa está en el notebook `01_modelado_regresion.ipynb`.

**Variables del modelo final (19):**

- *Las digita el usuario (12):* área, administración, habitaciones, baños, parqueaderos, estrato, antigüedad, localidad y 4 comodidades (parqueadero cubierto, gimnasio, piscina, balcón o terraza).
- *Se calculan con la dirección (7):* latitud, longitud, distancia a TransMilenio, a hospital/clínica, a vía principal y a factores negativos, y farmacias a 500 m.

El formulario de la app se construye a partir de `output/metadata.json`, de modo que siempre pide exactamente las variables con las que se entrenó el modelo.

## Ejecutar los notebooks

```bash
pip install -r modelado/requirements.txt
jupyter notebook modelado/
```

- `01_modelado_regresion.ipynb` reentrena todo y regenera `output/` (≈ 4 minutos).
- `02_produccion.ipynb` solo carga los artefactos y predice un apartamento nuevo.

## Ejecutar la app en el computador

```bash
pip install -r requirements.txt
python -m app.app
```

Abrir http://localhost:5000

## Desplegar en Render con GitHub

1. Crear un repositorio vacío en GitHub y subir el proyecto (desde la carpeta `prediccion-vivienda-bogota`):

   ```bash
   git init
   git add .
   git commit -m "Taller de regresión: modelado y app"
   git branch -M main
   git remote add origin https://github.com/USUARIO/REPOSITORIO.git
   git push -u origin main
   ```

2. En [render.com](https://render.com): **New → Blueprint**, conectar la cuenta de GitHub y elegir el repositorio. Render lee `render.yaml` y crea el servicio web con:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app.app:app --workers 1 --threads 4 --timeout 120`
   - Python 3.13.3 (variable `PYTHON_VERSION`)

   (Alternativa manual: **New → Web Service**, mismo repositorio, y escribir esos dos comandos y la variable de entorno.)

3. Al terminar el despliegue Render entrega la URL pública (`https://<nombre>.onrender.com`). En el plan gratuito el servicio se duerme tras 15 minutos sin uso; la primera visita tarda cerca de un minuto en despertar.

Cada `git push` a `main` vuelve a desplegar. Si se reentrena el modelo, basta con subir la carpeta `modelado/output/` actualizada.

## Servicios externos que usa la app

| Servicio | Para qué | Si no responde |
|---|---|---|
| ArcGIS World Geocoder / Nominatim | Convertir la dirección en coordenadas | El usuario puede ubicar el punto con un clic en el mapa |
| routing.openstreetmap.de | Dibujar la ruta caminando a la estación y al parque | Se muestra la línea recta |
| Teselas de OpenStreetMap | Mapa base | — |

Ninguno requiere llave de acceso. La distancia que entra al modelo es siempre la de línea recta (Haversine), calculada en el servidor; la ruta caminando es solo informativa.

## Limitaciones

- El modelo predice **precios de oferta**, no de cierre, y no reemplaza un avalúo.
- Error típico de 16 %; el rango mostrado contiene el precio real en el 80 % de los casos.
- Solo aplica a apartamentos dentro de Bogotá.
