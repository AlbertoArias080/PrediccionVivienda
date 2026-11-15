"""Genera el informe escrito del taller (PDF de 2 páginas). Requiere reportlab.

Uso (desde la raíz del proyecto):   python informe/generar_informe.py

La tabla comparativa se lee de `modelado/output/tabla_comparativa.csv`; el texto resume
los resultados del notebook `modelado/01_modelado_regresion.ipynb` con la base depurada del EDA.
"""
from __future__ import annotations

import csv
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

RAIZ = Path(__file__).resolve().parent.parent
TABLA = RAIZ / "modelado" / "output" / "tabla_comparativa.csv"
SALIDA = Path(__file__).resolve().parent / "informe_taller_regresion.pdf"

MORADO = colors.HexColor("#5B1F6E")
ROSA = colors.HexColor("#FBE3EE")
LILA = colors.HexColor("#F4EEF7")
GRIS = colors.HexColor("#777777")

TITULO = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=14.5, leading=17, textColor=MORADO)
SUBTITULO = ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=GRIS)
SECCION = ParagraphStyle("seccion", fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=MORADO,
                         spaceBefore=9, spaceAfter=3)
TEXTO = ParagraphStyle("texto", fontName="Helvetica", fontSize=8.8, leading=10.6, alignment=TA_JUSTIFY, spaceAfter=2)
VINETA = ParagraphStyle("vineta", parent=TEXTO, leftIndent=12, bulletIndent=2, spaceBefore=1.5)
NOTA = ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=7.3, leading=9, textColor=GRIS, spaceAfter=3)

NOMBRES = {"Ridge": "Ridge (alfa = 203)", "Lasso": "Lasso (alfa = 0,0049)", "Forward (BIC)": "Forward (BIC) — final"}


def es(valor: float, decimales: int = 1) -> str:
    """Número con coma decimal."""
    return f"{valor:.{decimales}f}".replace(".", ",")


def tabla_comparativa() -> Table:
    with open(TABLA, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    datos = [["Modelo", "N.º var.", "MAE CV", "MAE train", "MAE test", "RMSE test", "R² test", "MAPE test"]]
    fila_final = None
    for i, r in enumerate(filas, 1):
        nombre = r[""]
        if nombre == "Forward (BIC)":
            fila_final = i
        datos.append([
            NOMBRES.get(nombre, nombre), r["Variables"],
            f"${es(float(r['MAE CV (M$)']))} M", f"${es(float(r['MAE train (M$)']))} M",
            f"${es(float(r['MAE test (M$)']))} M", f"${es(float(r['RMSE test (M$)']))} M",
            es(float(r["R² test"]), 3), f"{es(float(r['MAPE test (%)']))} %",
        ])
    t = Table(datos, colWidths=[4.6 * cm, 1.6 * cm, 2.15 * cm, 2.15 * cm, 2.15 * cm, 2.25 * cm, 1.6 * cm, 2.0 * cm])
    estilo = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), MORADO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LILA]),
    ]
    if fila_final:
        estilo += [("BACKGROUND", (0, fila_final), (-1, fila_final), ROSA),
                   ("FONT", (0, fila_final), (-1, fila_final), "Helvetica-Bold", 8.5)]
    t.setStyle(TableStyle(estilo))
    return t


def p(texto: str) -> Paragraph:
    return Paragraph(texto, TEXTO)


def v(texto: str) -> Paragraph:
    return Paragraph(texto, VINETA, bulletText="•")


def construir() -> None:
    doc = SimpleDocTemplate(str(SALIDA), pagesize=letter, leftMargin=2.1 * cm, rightMargin=2.1 * cm,
                            topMargin=1.4 * cm, bottomMargin=1.2 * cm,
                            title="Predicción del precio de venta de apartamentos en Bogotá — Parte II",
                            author="Grupo B")
    h = [
        Paragraph("Predicción del precio de venta de apartamentos en Bogotá — Parte II", TITULO),
        Paragraph("Taller de Regresión y Regularización · Machine Learning Probabilístico · "
                  "Fundación Universitaria Konrad Lorenz", SUBTITULO),
        Paragraph("Grupo B — Andersson Hincapie Amaya y Gelber Alberto Arias Guzman · Noviembre de 2026", SUBTITULO),

        Paragraph("1. Métricas de evaluación y su justificación", SECCION),
        p("El modelo se pensó para un <b>iBuyer o asesor inmobiliario (tipo Habi)</b> que necesita un precio de "
          "referencia para ofertar por un inmueble u orientar a un propietario. Sobrevalorar significa pagar de más "
          "por un activo que no rota; subvalorar significa perder el negocio. Con ese usuario en mente se eligieron:"),
        v("<b>MAE en pesos (métrica principal).</b> Es el error típico por inmueble y se explica sin tecnicismos: "
          "«en promedio nos equivocamos por $X millones». Al no elevar al cuadrado, no queda dominado por unos pocos "
          "apartamentos de lujo y describe el error del inmueble típico, que es el grueso del negocio."),
        v("<b>RMSE en pesos (riesgo).</b> Castiga los errores grandes: un solo error enorme en un apartamento costoso "
          "puede borrar el margen de varias operaciones. La brecha RMSE – MAE indica si hay errores extremos."),
        v("<b>R² (complemento)</b> para comparar la variabilidad explicada, y <b>MAPE</b> como apoyo para comparar "
          "segmentos de precio. Ninguna reemplaza a una métrica de error en dinero."),
        p("Se modela <b>log(precio_venta)</b> —el precio tiene asimetría 2,6 y su logaritmo 0,1— pero <b>todas las "
          "métricas se reportan en pesos</b>, tras aplicar la exponencial dentro del propio Pipeline, porque es la "
          "unidad que entiende el negocio. Los hiperparámetros se eligen por MAE en pesos con validación cruzada de "
          "5 pliegues sobre entrenamiento; el conjunto de prueba (20 %, 2.045 apartamentos) se usó una sola vez."),

        Paragraph("2. Análisis de resultados", SECCION),
        p("<b>Datos.</b> 10.224 apartamentos en venta (Habi + Metrocuadrado) de la base depurada del Taller de EDA, ya "
          "filtrada, sin duplicados y con la división 80/20 (8.179 de entrenamiento y 2.045 de prueba); 42 variables "
          "candidatas: 7 del inmueble, 11 comodidades binarias y 24 de ubicación. Cambios frente al EDA: las "
          "distancias y conteos de entorno se recalcularon con <b>Haversine</b> desde las capas geográficas, para que "
          "producción aplique la misma transformación a un inmueble nuevo; y la imputación (incluida la de la "
          "administración), el escalado y el one-hot pasaron a un <b>Pipeline ajustado solo con entrenamiento</b> "
          "(sin fuga de información)."),
        Spacer(1, 2),
        tabla_comparativa(),
        Paragraph("MAE CV: validación cruzada de 5 pliegues en entrenamiento. M = millones de pesos. "
                  "Precio mediano en prueba: $828 M.", NOTA),
        v("<b>Modelo base.</b> Explica el 94,7 % de la variabilidad en logaritmos. Los residuales son casi simétricos "
          "pero con colas pesadas (curtosis 4,7) y heterocedásticos (Breusch-Pagan p &lt; 0,001): los supuestos "
          "bastan para predecir, no para inferencia fina. El VIF supera 10 en seis columnas, en dos focos —ubicación "
          "(localidad, latitud, longitud) y tamaño (área, baños, parqueaderos)—, por lo que esos coeficientes son "
          "inestables aunque la predicción no se afecte. 20 de 62 coeficientes no son significativos."),
        v("<b>Selección de variables (criterio de parada: BIC; categóricas en bloque).</b> Forward y Backward llegan "
          "a subconjuntos de <b>19 variables que coinciden en 18</b> y tienen el mismo BIC; solo difieren en una "
          "variable de entorno, señal de que el núcleo es estable. Entran primero área, estrato, antigüedad, "
          "localidad y parqueaderos (94 % de la mejora de BIC). La antigüedad en rangos se trató como bloque: sus "
          "dummies entran o salen juntas, porque una categoría suelta cambia la referencia y en producción se "
          "diligencia la variable completa."),
        v("<b>Ridge.</b> La curva de error es plana hasta alfa cercano a 100: la penalización no mejora la predicción, "
          "pero redistribuye el efecto entre variables colineales (área −18 %, baños +73 %) y no anula ningún "
          "coeficiente."),
        v("<b>Lasso.</b> Con la regla de un error estándar conserva 26 de 42 variables, entre ellas las 19 de Forward. "
          "De las 11 comodidades sobreviven 5 (4 en Forward/Backward, todas contenidas en las de Lasso); hay consenso "
          "total en descartar jacuzzi, ascensor, conjunto cerrado, vigilancia, chimenea y depósito. 18 variables son "
          "elegidas por los tres métodos. Las comodidades que más pesan son de zona común: gimnasio (+3,8 %) y "
          "piscina (+3,7 %), seguidas de balcón o terraza (+1,7 %)."),
        v("<b>Distancias Haversine.</b> La distancia a TransMilenio <b>sí aporta</b> (sobrevive en los tres métodos), "
          "con un efecto cercano al −2 % por desviación estándar. La distancia a parque <b>no</b>: los tres métodos "
          "la descartan, porque casi todos los apartamentos tienen un parque a pocos metros."),
        v("<b>Comparación.</b> La diferencia entre el mejor y el peor modelo es de <b>$7,4 M de MAE (0,89 % del "
          "precio mediano)</b>, del orden del error estándar de la validación cruzada ($6,7 M): son equivalentes. "
          "<b>No hay sobreajuste</b>: el MAE de prueba es apenas entre 0,7 % y 2,1 % mayor que el de entrenamiento, y "
          "el MAPE es casi idéntico (16,3 % y 16,0 %). Con 132 observaciones por parámetro, la regularización no "
          "tiene varianza que corregir. El RMSE duplica al MAE en todos los modelos: hay pocos errores muy grandes, "
          "concentrados en el segmento costoso."),
        PageBreak(),

        Paragraph("3. Conclusiones y recomendaciones de modelado", SECCION),
        v("<b>Modelo elegido: regresión lineal con las 19 variables de Forward.</b> Empata con el modelo base en "
          "validación cruzada ($238,9 M) y lo iguala en prueba ($240,1 M frente a $241,0 M) con menos de la mitad de "
          "las variables, es interpretable y exige menos datos en producción: 12 campos que digita el usuario y 7 "
          "variables que se calculan con la dirección. Explica el 86,1 % de la variabilidad del precio en datos "
          "nuevos."),
        v("<b>¿Suficiente para una aplicación real?</b> Sí como herramienta de orientación (precio de referencia, "
          "detección de anuncios fuera de mercado), siempre mostrando el rango: el 80 % de los precios reales cae "
          "entre 0,77 y 1,29 veces la estimación. No como tasador automático: un error típico de 16 % supera el "
          "margen de un iBuyer, y en el quintil más costoso el MAE llega a $714 M. Además se predicen precios de "
          "oferta, no de cierre."),
        v("<b>¿Se requiere un modelo más complejo?</b> Vale la pena probarlo. El modelo sobrestima entre 2 % y 5 % "
          "los segmentos económicos y medios y subestima cerca de 8 % el de lujo (no linealidad), y asume que un "
          "parqueadero o un m² valen lo mismo en cualquier estrato y localidad (sin interacciones). Random Forest o "
          "Gradient Boosting capturan ambas cosas y particionan mejor el espacio geográfico. Se recomienda mantener "
          "este modelo como línea base explicable y adoptar un ensamble solo si reduce el MAE de validación en al "
          "menos $20–30 M, acompañado de explicaciones tipo SHAP."),
        v("<b>Información adicional para producción.</b> Dirección exacta o manzana catastral (hoy la ubicación "
          "depende de coordenadas aproximadas en Metrocuadrado); fecha de publicación y precio de cierre (ajuste por "
          "mercado y descuento de negociación); piso y vista; antigüedad en años y estado de conservación; "
          "comodidades estructuradas para Habi y más detalladas (la base solo trae 11); área privada frente a "
          "construida; y valor de referencia catastral por m² e indicadores de seguridad por UPZ."),
        v("<b>Puesta en producción.</b> Se entrega el Pipeline serializado, las capas geográficas, los metadatos, un "
          "ejemplo de entrada y el notebook <i>02_produccion.ipynb</i>, que predice un apartamento nuevo sin "
          "reentrenar. Los mismos artefactos alimentan una aplicación web con formulario y mapa."),
    ]
    doc.build(h)
    print("Informe generado:", SALIDA)


if __name__ == "__main__":
    construir()
