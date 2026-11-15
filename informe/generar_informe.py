"""Genera el informe escrito del taller (máximo 2 páginas) en PDF.

Uso:  pip install reportlab
      python informe/generar_informe.py

Edite INTEGRANTES y vuelva a ejecutar para regenerar el PDF.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INTEGRANTES = "Grupo B — Andersson Hincapie Amaya y Gelber Alberto Arias Guzman"
SALIDA = Path(__file__).with_name("informe_taller_regresion.pdf")

MORADO = colors.HexColor("#5b1a6b")
GRIS = colors.HexColor("#f4eef6")

titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=13.5, leading=16, textColor=MORADO)
sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))
h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=MORADO, spaceBefore=7, spaceAfter=3)
p = ParagraphStyle("p", fontName="Helvetica", fontSize=9, leading=11.4, alignment=TA_JUSTIFY, spaceAfter=3.5)
v = ParagraphStyle("v", parent=p, leftIndent=10, bulletIndent=2, spaceAfter=2)
celda = ParagraphStyle("celda", fontName="Helvetica", fontSize=8.3, leading=10)
nota = ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=7.8, leading=9.5, textColor=colors.HexColor("#555555"), spaceAfter=3)


def vineta(texto):
    return Paragraph(texto, v, bulletText="•")


def tabla(filas, anchos, resaltar=None):
    datos = [[Paragraph(str(c), celda) for c in f] for f in filas]
    t = Table(datos, colWidths=anchos, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), MORADO),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
    ]
    if resaltar is not None:
        estilo.append(("BACKGROUND", (0, resaltar), (-1, resaltar), colors.HexColor("#fde2ec")))
    t.setStyle(TableStyle(estilo))
    for c in datos[0]:
        c.style = ParagraphStyle("cab", parent=celda, textColor=colors.white, fontName="Helvetica-Bold")
    return t


c = []
c.append(Paragraph("Predicción del precio de venta de apartamentos en Bogotá — Parte II", titulo))
c.append(Paragraph("Taller de Regresión y Regularización · Machine Learning Probabilístico · Fundación Universitaria Konrad Lorenz<br/>"
                   + INTEGRANTES + " · Noviembre de 2026", sub))

# ---------------------------------------------------------------- 1. Métricas
c.append(Paragraph("1. Métricas de evaluación y su justificación", h))
c.append(Paragraph(
    "El modelo se pensó para un <b>iBuyer o asesor inmobiliario (tipo Habi)</b> que necesita un precio de referencia para "
    "ofertar por un inmueble u orientar a un propietario. Sobrevalorar significa pagar de más por un activo que no rota; "
    "subvalorar significa perder el negocio. Con ese usuario en mente se eligieron:", p))
c.append(vineta("<b>MAE en pesos (métrica principal).</b> Es el error típico por inmueble y se explica sin tecnicismos: "
                "«en promedio nos equivocamos por $X millones». Al no elevar al cuadrado, no queda dominado por unos pocos "
                "apartamentos de lujo y describe el error del inmueble típico, que es el grueso del negocio."))
c.append(vineta("<b>RMSE en pesos (riesgo).</b> Castiga los errores grandes: un solo error enorme en un apartamento costoso "
                "puede borrar el margen de varias operaciones. La brecha RMSE – MAE indica si hay errores extremos."))
c.append(vineta("<b>R² (complemento)</b> para comparar la variabilidad explicada, y <b>MAPE</b> como apoyo para comparar "
                "segmentos de precio. Ninguna reemplaza a una métrica de error en dinero."))
c.append(Paragraph(
    "Se modela <b>log(precio_venta)</b> —el precio tiene asimetría 2,5 y su logaritmo 0,1— pero <b>todas las métricas se "
    "reportan en pesos</b>, tras aplicar la exponencial dentro del propio Pipeline, porque es la unidad que entiende el negocio. "
    "Los hiperparámetros se eligen por MAE en pesos con validación cruzada de 5 pliegues sobre entrenamiento; el conjunto de "
    "prueba (20 %, 2.034 apartamentos) se usó una sola vez.", p))

# -------------------------------------------------------------- 2. Resultados
c.append(Paragraph("2. Análisis de resultados", h))
c.append(Paragraph(
    "<b>Datos.</b> 10.170 apartamentos en venta (Habi + Metrocuadrado) tras filtrar errores de captura y duplicados; 51 variables "
    "candidatas: 7 del inmueble, 20 comodidades binarias y 24 de ubicación. Cambios frente al EDA: las distancias a TransMilenio "
    "y a parque se recalcularon con <b>Haversine</b> para que producción aplique la misma transformación a un inmueble nuevo; "
    "la imputación, el escalado y el one-hot pasaron a un <b>Pipeline ajustado solo con entrenamiento</b> (sin fuga de "
    "información); y las comodidades de Habi se completaron desde el texto del anuncio.", p))
c.append(tabla([
    ["Modelo", "N.º var.", "MAE CV", "MAE train", "MAE test", "RMSE test", "R² test", "MAPE test"],
    ["Base (OLS)", "51", "$238,1 M", "$236,1 M", "$210,4 M", "$425,0 M", "0,877", "15,8 %"],
    ["<b>Forward (BIC) — final</b>", "<b>26</b>", "<b>$237,7 M</b>", "<b>$236,5 M</b>", "<b>$211,8 M</b>", "<b>$425,1 M</b>", "<b>0,877</b>", "<b>16,0 %</b>"],
    ["Backward (BIC)", "26", "$237,7 M", "$236,5 M", "$211,8 M", "$425,1 M", "0,877", "16,0 %"],
    ["Ridge (alfa = 100)", "51", "$241,5 M", "$238,9 M", "$212,4 M", "$434,2 M", "0,872", "15,9 %"],
    ["Lasso (alfa = 0,0033)", "36", "$242,1 M", "$240,6 M", "$214,1 M", "$434,9 M", "0,872", "16,0 %"],
], [4.3 * cm, 1.6 * cm, 2.0 * cm, 2.1 * cm, 2.0 * cm, 2.1 * cm, 1.6 * cm, 2.0 * cm], resaltar=2))
c.append(Paragraph("MAE CV: validación cruzada de 5 pliegues en entrenamiento. M = millones de pesos. Precio mediano en prueba: $795 M.", nota))
c.append(vineta("<b>Modelo base.</b> Explica el 94,6 % de la variabilidad en logaritmos. Los residuales son simétricos pero con colas "
                "pesadas (curtosis 5,8) y heterocedásticos (Breusch-Pagan p &lt; 0,001): los supuestos bastan para predecir, no para "
                "inferencia fina. El VIF supera 10 en cinco columnas, en dos focos —ubicación (localidad, latitud, longitud) y tamaño "
                "(área, baños, parqueaderos)—, por lo que esos coeficientes son inestables aunque la predicción no se afecte. "
                "25 de 71 coeficientes no son significativos."))
c.append(vineta("<b>Selección de variables (criterio de parada: BIC; categóricas en bloque).</b> Forward y Backward llegan "
                "<b>exactamente al mismo subconjunto de 26 variables</b>, señal de que es estable. Entran primero área, estrato, "
                "antigüedad, localidad y parqueaderos (94 % de la mejora de BIC). La antigüedad en rangos se trató como bloque: sus "
                "dummies entran o salen juntas, porque una categoría suelta cambia la referencia y en producción se diligencia la variable completa."))
c.append(vineta("<b>Ridge.</b> La curva de error es plana hasta alfa cercano a 100: la penalización no mejora la predicción, pero "
                "redistribuye el efecto entre variables colineales (área −10 %, baños +29 %) y no anula ningún coeficiente."))
c.append(vineta("<b>Lasso.</b> Con la regla de un error estándar conserva 36 de 51 variables. De las 20 comodidades sobreviven 13 "
                "(10 en Forward/Backward, todas contenidas en las de Lasso); hay consenso total en descartar ascensor, chimenea, "
                "jacuzzi, conjunto cerrado, salón comunal, zonas verdes y canchas. 25 variables son elegidas por los tres métodos. "
                "Las comodidades que más pesan son de zona común: piscina (+3,9 %), gimnasio (+2,3 %), terraza y BBQ."))
c.append(vineta("<b>Distancias Haversine.</b> La distancia a TransMilenio y a parque <b>sí aportan</b> (sobreviven en los tres "
                "métodos), aunque con efectos inferiores al 1 % por desviación estándar."))
c.append(vineta("<b>Comparación.</b> La diferencia entre el mejor y el peor modelo es de <b>$3,7 M de MAE (0,46 % del precio "
                "mediano)</b>, menor que el error estándar de la validación cruzada ($4,0 M): son equivalentes. <b>No hay "
                "sobreajuste</b>: el error en prueba no supera al de entrenamiento, y el MAPE es casi idéntico (16,3 % y 16,0 %); "
                "el menor MAE en prueba se debe a que la partición dejó allí apartamentos algo más económicos. Con 115 observaciones "
                "por parámetro, la regularización no tiene varianza que corregir. El RMSE duplica al MAE en todos los modelos: "
                "hay pocos errores muy grandes, concentrados en el segmento costoso."))

# ------------------------------------------------------------ 3. Conclusiones
c.append(Paragraph("3. Conclusiones y recomendaciones de modelado", h))
c.append(vineta("<b>Modelo elegido: regresión lineal con las 26 variables de Forward/Backward.</b> Tiene el mejor MAE de validación "
                "($237,7 M), iguala al modelo base en prueba ($211,8 M frente a $210,4 M) con la mitad de las variables, es "
                "interpretable y exige menos datos en producción: 18 campos que digita el usuario y 8 variables que se calculan "
                "con la dirección. Explica el 87,7 % de la variabilidad del precio en datos nuevos."))
c.append(vineta("<b>¿Suficiente para una aplicación real?</b> Sí como herramienta de orientación (precio de referencia, detección de "
                "anuncios fuera de mercado), siempre mostrando el rango: el 80 % de los precios reales cae entre 0,77 y 1,29 veces la "
                "estimación. No como tasador automático: un error típico de 16 % supera el margen de un iBuyer, y en el quintil más "
                "costoso el MAE llega a $587 M. Además se predicen precios de oferta, no de cierre."))
c.append(vineta("<b>¿Se requiere un modelo más complejo?</b> Vale la pena probarlo. El modelo sobrestima cerca de 5 % los segmentos "
                "económicos y subestima 5 % el de lujo (no linealidad), y asume que un parqueadero o un m² valen lo mismo en "
                "cualquier estrato y localidad (sin interacciones). Random Forest o Gradient Boosting capturan ambas cosas y "
                "particionan mejor el espacio geográfico. Se recomienda mantener este modelo como línea base explicable y adoptar "
                "un ensamble solo si reduce el MAE de validación en al menos $20–30 M, acompañado de explicaciones tipo SHAP."))
c.append(vineta("<b>Información adicional para producción.</b> Dirección exacta o manzana catastral (hoy la ubicación depende de "
                "coordenadas aproximadas en Metrocuadrado); fecha de publicación y precio de cierre (ajuste por mercado y descuento "
                "de negociación); piso y vista; antigüedad en años y estado de conservación; comodidades estructuradas para Habi; "
                "área privada frente a construida; y valor de referencia catastral por m² e indicadores de seguridad por UPZ."))
c.append(vineta("<b>Puesta en producción.</b> Se entrega el Pipeline serializado, las capas geográficas, los metadatos, un ejemplo de "
                "entrada y el notebook <i>02_produccion.ipynb</i>, que predice un apartamento nuevo sin reentrenar. Los mismos "
                "artefactos alimentan una aplicación web con formulario y mapa."))

doc = SimpleDocTemplate(str(SALIDA), pagesize=letter, leftMargin=1.9 * cm, rightMargin=1.9 * cm,
                        topMargin=1.5 * cm, bottomMargin=1.4 * cm, title="Informe Taller de Regresión — Grupo B")
doc.build(c)
print(f"{SALIDA.name}: {doc.page} página(s)")
