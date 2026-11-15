/* Estimador de precio de apartamentos · lógica del front
   1) Construye el formulario con los campos que usa el modelo (/api/config)
   2) Ubica la dirección en el mapa (/api/geocodificar) o con un clic
   3) Envía los datos (/api/predecir) y dibuja precio, distancias y amenidades */

const $ = (id) => document.getElementById(id);
const pesos = (v) => "$" + Math.round(v).toLocaleString("es-CO");
const millones = (v) => "$" + (v / 1e6).toLocaleString("es-CO", { maximumFractionDigits: 0 }) + " M";
const metros = (v) => Math.round(v).toLocaleString("es-CO") + " m";
const VELOCIDAD_A_PIE = 80; // metros por minuto (~4,8 km/h)

const COLORES = {
  hospitales_clinicas: ["#d32f2f", "H"],
  farmacias: ["#f06292", "F"],
  educacion: ["#1976d2", "E"],
  comercio: ["#f57c00", "C"],
  transporte: ["#455a64", "T"],
  recreacion: ["#388e3c", "R"],
  religion: ["#7b1fa2", "I"],
  factores_negativos: ["#5d4037", "!"],
};

const estado = { lat: null, lon: null, resultado: null, ocultas: new Set() };

/* ------------------------------------------------------------------ Mapa */
const mapa = L.map("mapa", { zoomControl: true }).setView([4.676, -74.07], 12);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', maxZoom: 19,
}).addTo(mapa);

const capaEntorno = L.layerGroup().addTo(mapa);   // todo lo que se recalcula con cada predicción
const capaAmenidades = L.layerGroup().addTo(mapa);
let marcador = null;
let circulo = null;

function icono(color, letra) {
  return L.divIcon({
    className: "", iconSize: [20, 20], iconAnchor: [10, 10],
    html: `<span class="punto" style="background:${color}">${letra}</span>`,
  });
}

function fijarUbicacion(lat, lon, centrar = true) {
  estado.lat = lat; estado.lon = lon;
  if (!marcador) {
    marcador = L.marker([lat, lon], {
      draggable: true, zIndexOffset: 1000,
      icon: L.divIcon({ className: "", iconSize: [22, 22], iconAnchor: [11, 22], html: '<div class="marcador-casa"></div>' }),
    }).addTo(mapa);
    marcador.on("dragend", () => {
      const p = marcador.getLatLng();
      fijarUbicacion(p.lat, p.lng, false);
      mensajeUbicacion("Punto ajustado manualmente. Pulse “Calcular precio” para actualizar.", true);
    });
  } else {
    marcador.setLatLng([lat, lon]);
  }
  if (centrar) mapa.setView([lat, lon], 16);
}

mapa.on("click", (e) => {
  fijarUbicacion(e.latlng.lat, e.latlng.lng, false);
  mensajeUbicacion("Punto seleccionado en el mapa. Pulse “Calcular precio”.", true);
});

function mensajeUbicacion(texto, ok = false) {
  const el = $("estado-ubicacion");
  el.textContent = texto;
  el.classList.toggle("ok", ok);
}

/* ------------------------------------------------------------ Formulario */
function crear(etiqueta, atributos = {}, texto = null) {
  const el = document.createElement(etiqueta);
  Object.entries(atributos).forEach(([k, v]) => el.setAttribute(k, v));
  if (texto !== null) el.textContent = texto;
  return el;
}

function construirFormulario(config) {
  $("info-modelo").textContent =
    `Modelo: ${config.modelo} · ${config.n_train.toLocaleString("es-CO")} apartamentos de entrenamiento · ` +
    `error medio ${millones(config.metricas.MAE)} (${config.metricas.MAPE.toFixed(0)} %)`;

  config.campos.forEach((c) => {
    if (c.tipo === "numero") {
      const caja = crear("div");
      caja.append(crear("label", { for: c.nombre }, c.etiqueta + (c.opcional ? " (opcional)" : "")));
      caja.append(crear("input", {
        id: c.nombre, name: c.nombre, type: "number", inputmode: "decimal",
        min: c.entero ? Math.floor(c.minimo) : c.minimo, max: c.maximo,
        step: c.entero ? 1 : "any", placeholder: c.entero ? Math.round(c.mediana) : Math.round(c.mediana).toLocaleString("es-CO"),
        ...(c.opcional ? {} : { required: "" }),
      }));
      $("campos-numericos").append(caja);
    } else if (c.tipo === "categoria") {
      const caja = crear("div");
      caja.append(crear("label", { for: c.nombre }, c.etiqueta));
      const sel = crear("select", { id: c.nombre, name: c.nombre });
      if (c.nombre === "localidad") sel.append(crear("option", { value: "auto" }, "Detectar con la dirección"));
      c.opciones.forEach((o) => sel.append(crear("option", { value: o }, o)));
      if (c.nombre === "antiguedad_rango") sel.value = "Entre 10 y 20 años";
      caja.append(sel);
      $("campos-categoria").append(caja);
    } else {
      const lab = crear("label");
      lab.append(crear("input", { type: "checkbox", id: c.nombre, name: c.nombre }), document.createTextNode(c.etiqueta));
      $("campos-binarios").append(lab);
    }
  });
  estado.campos = config.campos;
}

function leerFormulario() {
  const datos = { latitud: estado.lat, longitud: estado.lon, direccion: $("direccion").value.trim() };
  estado.campos.forEach((c) => {
    const el = $(c.nombre);
    datos[c.nombre] = c.tipo === "binaria" ? (el.checked ? 1 : 0) : el.value;
  });
  return datos;
}

function mostrarError(texto) {
  const el = $("mensaje-error");
  el.textContent = texto || "";
  el.hidden = !texto;
}

/* --------------------------------------------------------- Geocodificar */
async function ubicarDireccion() {
  const direccion = $("direccion").value.trim();
  if (direccion.length < 4) { mensajeUbicacion("Escriba una dirección (por ejemplo: Carrera 15 # 93 - 60)."); return false; }
  $("btn-ubicar").disabled = true;
  mensajeUbicacion("Buscando la dirección…");
  try {
    const r = await fetch("/api/geocodificar?direccion=" + encodeURIComponent(direccion));
    const d = await r.json();
    if (!r.ok) { mensajeUbicacion(d.error); return false; }
    fijarUbicacion(d.latitud, d.longitud);
    mensajeUbicacion(`Ubicado: ${d.direccion_encontrada}${d.localidad ? " · " + d.localidad : ""}. Arrastre el marcador si no es el punto exacto.`, true);
    return true;
  } catch (e) {
    mensajeUbicacion("No fue posible consultar el servicio de direcciones. Ubique el punto con un clic en el mapa.");
    return false;
  } finally {
    $("btn-ubicar").disabled = false;
  }
}

/* -------------------------------------------------------------- Predecir */
async function calcular(evento) {
  evento.preventDefault();
  mostrarError("");
  if (estado.lat === null) {
    const ok = await ubicarDireccion();
    if (!ok) { mostrarError("Primero ubique el inmueble: escriba la dirección o haga clic en el mapa."); return; }
  }
  const boton = $("btn-calcular");
  boton.disabled = true; boton.textContent = "Calculando…";
  try {
    const r = await fetch("/api/predecir", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(leerFormulario()),
    });
    const d = await r.json();
    if (!r.ok) { mostrarError(d.error || "No fue posible calcular el precio."); return; }
    estado.resultado = d;
    pintarResultado(d);
    pintarMapa(d);
  } catch (e) {
    mostrarError("No hay conexión con el servidor. Intente de nuevo.");
  } finally {
    boton.disabled = false; boton.textContent = "Calcular precio";
  }
}

function pintarResultado(d) {
  $("res-precio").textContent = pesos(d.precio);
  $("res-rango").textContent = `Rango probable (80 %): ${millones(d.precio_min)} – ${millones(d.precio_max)}`;
  $("res-m2").textContent = pesos(d.precio_m2);
  $("res-localidad").textContent = d.localidad || "—";
  $("res-error").textContent = `± ${d.mape.toFixed(0)} %`;
  const ul = $("res-advertencias");
  ul.replaceChildren(...d.advertencias.map((a) => crear("li", {}, a)));
  $("resultado").hidden = false;

  const tabla = $("tabla-variables");
  tabla.replaceChildren(...d.variables_calculadas.map((v) => {
    const tr = crear("tr");
    const valor = typeof v.valor === "number" ? v.valor.toLocaleString("es-CO", { maximumFractionDigits: 5 }) : v.valor;
    tr.append(crear("td", {}, v.etiqueta), crear("td", {}, valor));
    return tr;
  }));
  $("entorno").hidden = false;
  $("control-radio").hidden = false;
}

/* ------------------------------------------------------------------ Mapa */
function filaDistancia(titulo, nombre, dist, idRuta) {
  const tr = crear("tr");
  const td1 = crear("td", {}, titulo);
  td1.append(crear("small", {}, nombre));
  const td2 = crear("td", {}, metros(dist));
  td2.append(crear("small", { id: idRuta }, `≈ ${Math.max(1, Math.round(dist / VELOCIDAD_A_PIE))} min en línea recta`));
  tr.append(td1, td2);
  return tr;
}

async function rutaCaminando(origen, destino, color, idTexto) {
  // Línea recta punteada de inmediato; si el servicio de rutas responde, se reemplaza por la ruta peatonal
  const recta = L.polyline([origen, destino], { color, weight: 3, dashArray: "6 8", opacity: .9 }).addTo(capaEntorno);
  try {
    const url = `https://routing.openstreetmap.de/routed-foot/route/v1/foot/${origen[1]},${origen[0]};${destino[1]},${destino[0]}?overview=full&geometries=geojson`;
    const r = await fetch(url, { signal: AbortSignal.timeout(7000) });
    const d = await r.json();
    if (d.code !== "Ok") return;
    const ruta = d.routes[0];
    capaEntorno.removeLayer(recta);
    L.polyline(ruta.geometry.coordinates.map(([x, y]) => [y, x]), { color, weight: 4, opacity: .9 }).addTo(capaEntorno);
    const el = $(idTexto);
    if (el) el.textContent = `caminando: ${metros(ruta.distance)} · ${Math.max(1, Math.round(ruta.distance / VELOCIDAD_A_PIE))} min`;
  } catch (e) { /* sin servicio de rutas: queda la línea recta */ }
}

function pintarMapa(d) {
  const e = d.entorno;
  const casa = [d.latitud, d.longitud];
  capaEntorno.clearLayers();
  fijarUbicacion(d.latitud, d.longitud, false);

  // Parques que tocan el radio (el más cercano resaltado)
  e.parques_poligonos.forEach((p) => {
    L.polygon(p.coords, {
      color: "#2e7d32", weight: p.cercano ? 2.5 : 1, fillColor: "#66bb6a", fillOpacity: p.cercano ? .45 : .2,
    }).bindTooltip(p.nombre).addTo(capaEntorno);
  });

  // Estación de TransMilenio más cercana
  L.marker([e.estacion.lat, e.estacion.lon], { icon: icono("#c62828", "TM") })
    .bindTooltip(`Estación ${e.estacion.nombre}`).addTo(capaEntorno);

  // Tabla de distancias
  $("tabla-distancias").replaceChildren(
    filaDistancia("Estación de TransMilenio", e.estacion.nombre, e.estacion.dist_m, "ruta-estacion"),
    filaDistancia("Parque más cercano", e.parque.nombre, e.parque.dist_m, "ruta-parque"),
    filaDistancia("Vía principal", `${e.via.nombre} (${e.via.tipo})`, e.via.dist_m, "ruta-via"),
  );
  $("ruta-via").textContent = "";

  rutaCaminando(casa, [e.estacion.lat, e.estacion.lon], "#c62828", "ruta-estacion");
  rutaCaminando(casa, [e.parque.lat, e.parque.lon], "#2e7d32", "ruta-parque");

  pintarAmenidades();
  const limites = L.latLngBounds([casa, [e.estacion.lat, e.estacion.lon], [e.parque.lat, e.parque.lon]]);
  mapa.fitBounds(limites.pad(0.25), { maxZoom: 16 });
}

function pintarAmenidades() {
  const d = estado.resultado;
  if (!d) return;
  const radio = Number($("radio").value);
  $("radio-valor").textContent = radio;
  capaAmenidades.clearLayers();
  if (circulo) mapa.removeLayer(circulo);
  circulo = L.circle([d.latitud, d.longitud], {
    radius: radio, color: "#5b1a6b", weight: 1.5, dashArray: "4 6", fillColor: "#5b1a6b", fillOpacity: .05, interactive: false,
  }).addTo(mapa);

  const lista = $("lista-amenidades");
  lista.replaceChildren();
  Object.entries(d.entorno.amenidades).forEach(([cat, info]) => {
    const [color, letra] = COLORES[cat] || ["#555", "•"];
    const dentro = info.elementos.filter((p) => p.dist_m <= radio);
    const visible = !estado.ocultas.has(cat);

    const fila = crear("label", { class: "amenidad" });
    const chk = crear("input", { type: "checkbox" });
    chk.checked = visible;
    chk.addEventListener("change", () => {
      chk.checked ? estado.ocultas.delete(cat) : estado.ocultas.add(cat);
      pintarAmenidades();
    });
    const punto = crear("span", { class: "color" });
    punto.style.background = color;
    const cercano = dentro.length ? ` · el más cercano a ${metros(dentro[0].dist_m)}` : "";
    fila.append(chk, punto, document.createTextNode(info.etiqueta + cercano), crear("span", { class: "conteo" }, String(dentro.length)));
    lista.append(fila);

    if (visible) {
      dentro.forEach((p) => {
        const nombre = p.nombre && p.nombre !== "Sin nombre" ? p.nombre : info.etiqueta;
        L.marker([p.lat, p.lon], { icon: icono(color, letra) })
          .bindTooltip(`${nombre} · ${metros(p.dist_m)}`).addTo(capaAmenidades);
      });
    }
  });
}

/* ----------------------------------------------------------------- Inicio */
$("btn-ubicar").addEventListener("click", ubicarDireccion);
$("direccion").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); ubicarDireccion(); } });
$("formulario").addEventListener("submit", calcular);
$("radio").addEventListener("input", pintarAmenidades);

fetch("/api/config").then((r) => r.json()).then(construirFormulario)
  .catch(() => mostrarError("No fue posible cargar la configuración del modelo."));
