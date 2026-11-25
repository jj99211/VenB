"""Página web interactiva (un solo fichero HTML): mapa, perfil y tabla de tiempos editable."""
import json
import re

import numpy as np

from . import estilo as E

PLANTILLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
  :root { --acento:#2c5aa0; --tinta:#1f2328; --gris:#6b7280; --linea:#e5e7eb; --fondo:#f7f7f5; --ok:#16855f; --mal:#c62828; }
  * { box-sizing:border-box; }
  body { margin:0; font:19px/1.4 system-ui, "Segoe UI", Roboto, sans-serif; color:var(--tinta); background:var(--fondo); }
  /* Cabecera: el promotor arriba y destacado; debajo la ruta (título, subtítulo, cifras en tarjetas), los botones y
     los ajustes. Todo en el flujo normal: nada se monta sobre nada, sea cual sea el ancho */
  /* la cabecera es un panel: fondo azulado que se aclara hacia abajo, borde y sombra; separada del mapa */
  header { margin:14px 20px 0; padding:18px 22px 16px; border:1px solid #d6dfec; border-radius:12px;
           background:linear-gradient(180deg, #e9f0f9 0%, #f6f9fd 45%, #fff 100%);
           box-shadow:0 1px 2px rgba(16,40,80,.06), 0 6px 18px rgba(16,40,80,.10); }
  .promotor { display:flex; flex-wrap:wrap; align-items:center; gap:12px 20px; padding-bottom:14px; margin-bottom:14px;
              border-bottom:3px solid var(--acento); }
  .promotor-logos { display:flex; flex-wrap:wrap; align-items:center; gap:14px; }
  .promotor-logos img { height:72px; max-width:260px; object-fit:contain; }
  .promotor-texto { display:flex; flex-direction:column; align-items:flex-start; gap:6px; }
  .promotor-nombre { font-size:28px; font-weight:750; line-height:1.15; letter-spacing:.2px; }
  .promotor-web { display:inline-flex; align-items:center; gap:6px; padding:4px 14px; border:1.5px solid var(--acento);
                  border-radius:999px; color:var(--acento); font-size:16px; font-weight:600; text-decoration:none; }
  .promotor-web:hover { background:var(--acento); color:#fff; }
  h1 { margin:0; font-size:26px; line-height:1.2; letter-spacing:.2px; }
  .subtitulo { margin:4px 0 0; color:var(--gris); font-size:18px; }
  .subtitulo:empty { display:none; }
  .datos { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
  .dato { display:flex; flex-direction:column; min-width:96px; padding:7px 14px; background:#fff;
          border:1px solid #dbe3ee; border-radius:8px; box-shadow:0 1px 2px rgba(16,40,80,.05); }
  .dato b { font-size:24px; line-height:1.15; font-variant-numeric:tabular-nums; }
  .dato span { font-size:14px; color:var(--gris); }
  .dato.ancho { min-width:0; }
  .acciones { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
  .boton { display:inline-flex; align-items:center; gap:8px; padding:9px 18px; border-radius:8px; font:600 17px/1.2 system-ui, sans-serif;
           text-decoration:none; cursor:pointer; border:2px solid var(--acento); }
  .boton.principal { background:var(--acento); color:#fff; }
  .boton.principal:hover { background:#234a85; border-color:#234a85; }
  .boton.secundario { background:#fff; color:var(--acento); }
  .boton.secundario:hover { background:#eef3fb; }
  .controles { display:flex; flex-wrap:wrap; gap:10px 18px; align-items:end; margin-top:14px; padding-top:12px; border-top:1px solid #dbe3ee; }
  .controles label[hidden] { display:none; }
  .controles label.casilla { flex-direction:row; align-items:flex-start; gap:8px; padding-bottom:4px; color:var(--tinta); }
  .controles label.casilla input { margin-top:5px; }
  .controles label.casilla small { display:block; color:var(--gris); font-size:14px; }
  .controles label { display:flex; flex-direction:column; font-size:16px; color:var(--gris); gap:2px; }
  .controles input, .controles select { font:inherit; padding:4px 6px; border:1px solid #ccc; border-radius:4px; }
  .controles input[type=number] { width:120px; }
  .dias { display:flex; gap:6px; flex-wrap:wrap; margin-top:10px; }
  .dias:empty { display:none; }
  .chip { color:#fff; padding:4px 10px; border-radius:4px; font-weight:600; font-size:17px; }
  @media (max-width: 640px) {
    header { margin:8px 8px 0; padding:12px 14px; border-radius:10px; }
    .promotor-logos img { height:56px; }
    .promotor-nombre { font-size:23px; }
    h1 { font-size:22px; }
    .datos { gap:6px; }
    .dato { min-width:0; padding:5px 10px; }
    .dato b { font-size:19px; }
    .dato span { font-size:13px; }
    .boton { padding:8px 14px; font-size:16px; }
  }
  .credito { margin-top:10px; }
  .credito a { display:inline-flex; align-items:center; gap:6px; color:var(--gris); text-decoration:none; font-size:14px; }
  .credito a:hover { text-decoration:underline; }
  .credito img { height:20px; opacity:.75; }
  main { display:grid; grid-template-columns:minmax(0, 1.25fr) minmax(0, 1fr); gap:14px; padding:14px 20px; }
  @media (max-width: 1500px) { main { grid-template-columns:1fr; } }
  .insertada #mapa { height:560px; min-height:0; }
  .insertada .tabla { max-height:none; }
  #mapa { height:62vh; min-height:420px; border-radius:6px; border:1px solid var(--linea); }
  #perfil { width:100%; height:340px; background:#fff; border:1px solid var(--linea); border-radius:6px; margin-top:10px; }
  .tabla { overflow:auto; max-height:calc(62vh + 350px); background:#fff; border:1px solid var(--linea); border-radius:6px; }
  table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
  table { font-size:16px; }
  th, td { padding:5px 7px; border-bottom:1px solid var(--linea); text-align:right; white-space:nowrap; }
  th { position:sticky; top:0; background:#2c5aa0; color:#fff; font-weight:600; font-size:14px; line-height:1.15; white-space:normal; z-index:1; }
  /* Sin sitio para todas las columnas (blog, móvil, iframe): fuera las secundarias; si aún no cabe, la tabla se desplaza */
  @media (max-width: 1100px) { .c2 { display:none; } }
  @media (min-width: 1501px) and (max-width: 2100px) { .c2 { display:none; } }
  @media (max-width: 640px) { .c3 { display:none; } th, td { padding:4px 5px; } table { font-size:15px; } td.n { white-space:normal; } td input { width:3.2em; } }
  td.n { text-align:left; }
  tr.ctrl td { font-weight:650; background:#fafafa; }
  td input { width:4.2em; font:inherit; padding:1px 3px; border:1px solid #ccc; border-radius:3px; text-align:right; }
  .pos { color:var(--ok); } .neg { color:var(--mal); font-weight:700; }
  .dia { display:inline-block; width:16px; height:16px; border-radius:2px; margin-right:5px; vertical-align:middle; }
  .caja { color:#fff; padding:10px 14px; border:3px solid #000; font-weight:600; line-height:1.3; font-size:18px; }
  .caja b { font-size:21px; }
  .leaflet-tooltip { font-size:16px; }
  .wpt { background:#fff; border:2px solid #333; border-radius:50%; display:flex; align-items:center; justify-content:center;
         font-size:17px; line-height:1; box-shadow:0 1px 3px rgba(0,0,0,.45); }
  .leaflet-tooltip.etiqueta { font-size:14px; font-weight:600; padding:1px 6px; background:rgba(255,255,255,.88);
         border:1px solid #888; border-radius:3px; box-shadow:none; }
  .leaflet-tooltip.etiqueta::before { display:none; }
  .leaflet-control-attribution { font-size:14px; }
  .leaflet-bar a { width:44px !important; height:44px !important; line-height:44px !important; font-size:28px !important; }
  .leaflet-popup-content { margin:0; } .leaflet-popup-content-wrapper { padding:0; border-radius:0; overflow:hidden; }
  footer { color:var(--gris); font-size:15px; padding:0 20px 16px; }
</style>
</head>
<body>
<header>
  __MARCA__
  <h1 id="titulo"></h1>
  <p class="subtitulo" id="subtitulo"></p>
  <div class="datos" id="resumen"></div>
  <div class="dias" id="dias"></div>
  <div class="acciones" id="acciones">
    <button type="button" class="boton principal" id="descargar-gpx" title="Track con los controles, la salida, la llegada y los demás puntos como waypoints (tipos de Garmin Connect)"><span aria-hidden="true">⬇</span> Descargar GPX con waypoints</button>
  </div>
  <div class="controles">
    <label>Salida <input type="datetime-local" id="salida"></label>
    <label><span id="etiqueta-limite">Límite (h)</span> <input type="number" id="limite" step="0.5" min="1"></label>
    <label title="Se aplica a los controles intermedios que no tienen una parada propia; los demás puntos llevan la parada indicada en la tabla">Tiempo de parada por defecto en los controles (min) <input type="number" id="defecto" step="5" min="0"></label>
    <label>Mapa base
      <select id="base"><option value="ign_mtn">IGN: topográfico (MTN)</option><option value="ign_base">IGN Base</option><option value="ign_orto">IGN: ortofoto con rótulos</option><option value="topo">OpenTopoMap</option><option value="osm">OpenStreetMap</option></select>
    </label>
    <label class="casilla"><input type="checkbox" id="nombres" checked><span>Ver los nombres de los puntos<small>en el mapa y en el perfil; sin marcar, al pasar el ratón por encima</small></span></label>
  </div>
</header>
<main>
  <section>
    <div id="mapa"></div>
    <svg id="perfil" preserveAspectRatio="none"></svg>
  </section>
  <section class="tabla"><table id="tabla"></table></section>
</main>
<footer>Mapa: © OpenStreetMap contributors · OpenTopoMap (CC-BY-SA) · Altitudes: EU-DEM 25 m (OpenTopoData).
<span id="nota-velocidad">Velocidad según la pendiente media del tramo (ascenso/distancia), con pérdida por fatiga a lo largo de la ruta.</span>
<span id="nota-pie"></span>
__CREDITO__</footer>
<script>
// FICHA = true en la copia para publicar en una web (Planificador, «Ruta para una web»): tiempos desde la salida, sin fecha, cierres ni márgenes
const FICHA = false;
const D = __DATOS__;
// horario del plan (Planificador): sin hora de salida, tiempos desde la salida; sin límite, sin cierres ni márgenes
const CON_SALIDA = !FICHA && (!D.horario || D.horario.salida !== false);
const CON_LIMITE = !FICHA && (!D.horario || D.horario.limite !== false);
// Perfiles de puertos: la página de un puerto no habla de tiempos (sin velocidad, paradas, llegada ni salida)
const PUERTO = !!D.puerto;
if (PUERTO && document.getElementById("nota-velocidad")) document.getElementById("nota-velocidad").remove();
// ruta libre: el límite es un objetivo, no un cierre; llegar tarde cuenta a partir de 5 min (antes suele ser redondeo)
const OBJETIVO = !!(D.horario && D.horario.objetivo), TOLERANCIA = 5;
const tarde = r => CON_LIMITE && r.margen < -TOLERANCIA;
const retraso = min => { min = Math.round(min); return min < 60 ? `${min} min` : dur(min) + " h"; };
const COLORES = __COLORES__;
const ICONOS = __ICONOS__;
const SIN_ICONO_PERFIL = ["salida", "llegada", "meta"];
const kmTexto = k => k < 100 ? "km " + k.toFixed(1).replace(".", ",") : "km " + k.toFixed(0);
const icono = r => r.tipo && ICONOS[r.tipo] ? ICONOS[r.tipo] + " " : "";
const MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
const MESES_L = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];

const V = D.velocidades;
const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function velocidadBase(p) {
  const t = V.tramos;
  for (let i = 0; i < t.length; i++) if (p < t[i][0] || (i === t.length - 1 && p <= t[i][0])) return t[i][1];
  return V.resto;
}
const fatiga = f => 1 - Math.min(Math.floor(f / (V.fatiga_cada || 1) + 1e-6) * V.fatiga_pct, V.fatiga_max_pct) / 100;
const hhmm = d => d.toTimeString().slice(0,5);
const desde = d => "+" + dur((d - estado.salida) / 60e3);                 // tiempo desde la salida (ficha)
const momento = d => CON_SALIDA ? `${d.getDate()} · ${hhmm(d)}` : desde(d);
const hora = d => CON_SALIDA ? hhmm(d) : desde(d);
function dur(min, signo) {
  const neg = min < 0; min = Math.round(Math.abs(min));
  return (neg ? "−" : signo ? "+" : "") + Math.floor(min/60) + ":" + String(min%60).padStart(2,"0");
}
const diaDe = (t, t0) => !CON_SALIDA ? Math.floor((t - t0) / 864e5) : Math.round((new Date(t.getFullYear(),t.getMonth(),t.getDate()) - new Date(t0.getFullYear(),t0.getMonth(),t0.getDate())) / 864e5);
const color = d => COLORES[((d % COLORES.length) + COLORES.length) % COLORES.length];
function aLocal(d) { const z = n => String(n).padStart(2,"0"); return `${d.getFullYear()}-${z(d.getMonth()+1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`; }

const estado = { salida: new Date(D.salida), limite: D.limite_h, defecto: D.parada_defecto,
                 paradas: D.puntos.map(p => p.parada) };

function calcular() {
  const t0 = estado.salida, total = D.total_km, n = D.puntos.length;
  let ant = null;
  return D.puntos.map((p, i) => {
    const r = Object.assign({}, p);
    if (!ant) { r.llegada = r.salida = t0; r.vel = 0; r.parada = 0; }
    else {
      r.vel = velocidadBase(p.pendiente) * fatiga(p.km / total) * (V.factor || 1);
      r.llegada = new Date(ant.salida.getTime() + p.km_tramo / r.vel * 3600e3);
      let par = estado.paradas[i];
      if (par === null) par = (p.control && i < n - 1) ? estado.defecto : 0;
      r.parada = par;
      r.salida = new Date(r.llegada.getTime() + par * 60e3);
    }
    r.cierre = p.cierre_hoja ? new Date(p.cierre_hoja) : p.cierre_h != null ? new Date(t0.getTime() + p.cierre_h * 3600e3)
      : new Date(t0.getTime() + p.km / total * estado.limite * 3600e3);
    r.margen = (r.cierre - r.salida) / 60e3;   // al reanudar la marcha: llegada + parada
    r.apertura = p.apertura_hoja ? new Date(p.apertura_hoja) : p.apertura_h != null ? new Date(t0.getTime() + p.apertura_h * 3600e3) : null;
    r.antes = r.apertura && r.llegada < r.apertura;
    r.dia = diaDe(r.llegada, t0);
    ant = r; return r;
  });
}

// ---------- mapa
const mapa = L.map("mapa", { zoomSnap: 0.25 });
const capas = {
  topo: L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", { maxZoom: 17, attribution: "© OpenStreetMap, OpenTopoMap" }),
  osm: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }),
  ign_mtn: L.tileLayer("https://tms-mapa-raster.ign.es/1.0.0/mapa-raster/{z}/{x}/{y}.jpeg", { tms: true, maxZoom: 17, attribution: "© IGN España (CC BY 4.0)" }),
  ign_base: L.tileLayer("https://tms-ign-base.idee.es/1.0.0/IGNBaseTodo/{z}/{x}/{y}.jpeg", { tms: true, maxZoom: 17, attribution: "© IGN España (CC BY 4.0)" }),
  ign_orto: L.layerGroup([
    L.tileLayer("https://tms-pnoa-ma.idee.es/1.0.0/pnoa-ma/{z}/{x}/{y}.jpeg", { tms: true, maxZoom: 19, attribution: "PNOA © IGN España (CC BY 4.0)" }),
    L.tileLayer("https://tms-ign-base.idee.es/1.0.0/IGNBaseOrto/{z}/{x}/{y}.png", { tms: true, maxZoom: 19 })]),
};
const selBase = document.getElementById("base");
selBase.value = capas[D.base] ? D.base : "topo";
let capa = capas[selBase.value].addTo(mapa);
document.getElementById("base").onchange = e => { mapa.removeLayer(capa); capa = capas[e.target.value].addTo(mapa); };
const grupoTrack = L.layerGroup().addTo(mapa), grupoPuntos = L.layerGroup().addTo(mapa);
const TRAZO = D.trazo || D.track.map(t => [t[0], t[1], t[3]]);   // por si faltara el trazo
mapa.fitBounds(L.latLngBounds(TRAZO.map(t => [t[0], t[1]])), { padding: [20, 20] });

function horaEnKm(res, km) {
  let i = 1; while (i < res.length - 1 && res[i].km < km) i++;
  const a = res[i-1], b = res[i], f = Math.max(0, Math.min(1, (km - a.km) / Math.max(b.km - a.km, 1e-9)));
  return new Date(a.salida.getTime() + f * (b.llegada - a.salida));
}

function popup(r) {
  const tit = icono(r) + esc((r.control ? r.control + " - " : "") + r.nombre.toUpperCase());
  const linea = `${hora(r.llegada)} h${r.parada ? ` (+${r.parada} min)` : ""}` + (CON_LIMITE ? ` &lt; ${hora(r.cierre)} h<br>
    ${OBJETIVO && tarde(r) ? `${retraso(-r.margen)} después del objetivo` : `margen ${dur(r.margen, true)} h`}` : "");
  return `<div class="caja" style="background:${color(r.dia)}"><b>${tit}</b><br>
    km ${r.km.toFixed(0)} (+${r.asc_total.toFixed(0)} m) · ${r.alt.toFixed(0)} m<br>
    ${linea}</div>`;
}

function dibujarMapa(res) {
  grupoTrack.clearLayers(); grupoPuntos.clearLayers();
  let tramo = [], diaAct = null;
  const cerrar = () => { if (tramo.length > 1) L.polyline(tramo, { color: color(diaAct), weight: 7, opacity: .9 }).addTo(grupoTrack); };
  const halo = L.polyline(TRAZO.map(t => [t[0], t[1]]), { color: "#111", weight: 11, opacity: .45 }).addTo(grupoTrack);
  let j = 1;
  for (const t of TRAZO) {
    while (j < res.length - 1 && res[j].km < t[2]) j++;
    const a = res[j-1], b = res[j], f = Math.max(0, Math.min(1, (t[2] - a.km) / Math.max(b.km - a.km, 1e-9)));
    const d = diaDe(new Date(a.salida.getTime() + f * (b.llegada - a.salida)), estado.salida);
    if (d !== diaAct) { if (tramo.length) { tramo.push([t[0], t[1]]); cerrar(); } tramo = [[t[0], t[1]]]; diaAct = d; }
    else tramo.push([t[0], t[1]]);
  }
  cerrar();
  // puntos de la ruta: los controles y los destacados, círculo grande; los demás, el icono de su tipo (o un círculo
  // pequeño si no tiene). El nombre, siempre visible salvo que se desmarque «Nombres de los puntos».
  const fijos = document.getElementById("nombres").checked, ultimo = res.length - 1;
  res.forEach((r, i) => {
    // llegada en el mismo sitio que la salida: sin rótulo propio, que taparía el de la salida
    const repetido = i === ultimo && i > 0 && Math.abs(r.lat - res[0].lat) < 0.002 && Math.abs(r.lon - res[0].lon) < 0.002;
    let m;
    if (r.control || r.destacado)
      m = L.circleMarker([r.lat, r.lon], { radius: 11, color: tarde(r) ? "#c62828" : "#111", weight: 4, fillColor: "#fff", fillOpacity: 1 });
    else if (r.tipo && ICONOS[r.tipo])
      m = L.marker([r.lat, r.lon], { icon: L.divIcon({ className: "wpt", html: ICONOS[r.tipo], iconSize: [30, 30] }), riseOnHover: true,
                                     zIndexOffset: i === 0 ? 1000 : 0 });   // la salida, por encima de la llegada
    else
      m = L.circleMarker([r.lat, r.lon], { radius: 6, color: "#333", weight: 2, fillColor: "#fff", fillOpacity: 1 });
    m.bindPopup(popup(r));
    if (!repetido)
      m.bindTooltip(esc((r.control ? r.control + " " : "") + r.nombre),
                    { direction: "right", offset: [14, 0], permanent: fijos, className: fijos ? "etiqueta" : "" });
    m.addTo(grupoPuntos);
  });
}

// ---------- perfil (SVG)
function dibujarPerfil(res) {
  const svg = document.getElementById("perfil");
  const conIcono = res.filter(r => r.tipo && ICONOS[r.tipo] && !SIN_ICONO_PERFIL.includes(r.tipo));
  const R = 13, FILA = 2 * R + 20;
  const W = svg.clientWidth || 800, m = { l: 80, r: 12, t: 26, b: 52 };
  const total = D.total_km, maxTrack = Math.max(...D.track.map(t => t[2]));
  // fila de cada icono (sube una si toca a otro); el perfil deja arriba sitio para todas. Con «Nombres de los
  // puntos», el nombre va junto al disco (a la derecha; a la izquierda si no cabe) y cuenta para los choques.
  const conNombre = document.getElementById("nombres").checked;
  const anchoNombre = r => conNombre ? esc(r.nombre).length * 8.2 + 8 : 0;
  const filaDe = [], ladoDe = [], puestos = [];
  for (const r of conIcono) {
    const x = m.l + r.km / total * (W - m.l - m.r), w = anchoNombre(r);
    const izq = w && x + R + w > W - m.r;
    const a = izq ? x - R - w : x - R - 15, b = izq ? x + R + 15 : x + R + w;
    let n = 0; while (puestos.some(([a2, b2, n2]) => n2 === n && a < b2 + 6 && a2 < b + 6)) n++;
    puestos.push([a, b, n]); filaDe.push(n); ladoDe.push(izq);
  }
  const nFilas = filaDe.length ? Math.max(...filaDe) + 1 : 0;
  // 340 px de alto (como en la hoja de estilo) más lo que ocupen las filas de iconos a partir de la segunda
  const H = 340 + Math.max(0, nFilas - 1) * FILA;
  svg.style.height = H + "px";
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const hueco = nFilas * FILA + (nFilas ? 6 : 0);
  const maxE = maxTrack * 1.1 * (H - m.t - m.b) / Math.max(H - m.t - m.b - hueco, 60);
  const fila0 = m.t + hueco - 6;   // línea base del km de la primera fila (la más baja)
  const X = km => m.l + km / total * (W - m.l - m.r), Y = e => H - m.b - e / maxE * (H - m.t - m.b);
  let s = "";
  const techo = maxTrack * 1.1;   // las altitudes rotuladas, solo hasta el perfil (no en la fila de iconos)
  for (let e = 0; e < techo; e += techo > 2600 ? 500 : 250)
    s += `<line x1="${m.l}" x2="${W-m.r}" y1="${Y(e)}" y2="${Y(e)}" stroke="#eee"/><text x="${m.l-4}" y="${Y(e)+4}" font-size="19" text-anchor="end" fill="#666">${e}</text>`;
  const pend = __PENDIENTES__;
  for (let i = 0; i < D.track.length - 1; i++) {
    const a = D.track[i], b = D.track[i+1];
    const p = (b[2] - a[2]) / Math.max((b[3] - a[3]) * 1000, 1) * 100;
    let c = pend[pend.length-1][1]; for (const [lim, col] of pend) if (p < lim) { c = col; break; }
    s += `<path d="M${X(a[3])},${Y(0)}L${X(a[3])},${Y(a[2])}L${X(b[3])},${Y(b[2])}L${X(b[3])},${Y(0)}Z" fill="${c}"/>`;
  }
  s += `<polyline fill="none" stroke="#5a4a1a" stroke-width=".8" points="${D.track.map(t => X(t[3]) + "," + Y(t[2])).join(" ")}"/>`;
  // banda de días
  let ini = 0, d0 = res[0].dia;
  const banda = (a, b, d) => s += `<rect x="${X(a)}" y="${H-m.b+2}" width="${X(b)-X(a)}" height="14" fill="${color(d)}"/>`;
  for (let km = 0; km <= total; km += total / 400) {
    const d = diaDe(horaEnKm(res, km), estado.salida);
    if (d !== d0) { banda(ini, km, d0); ini = km; d0 = d; }
  }
  banda(ini, total, d0);
  if (PUERTO) s = s.replace(/<rect [^>]*height="14"[^>]*\/>/g, "");   // un puerto no tiene días
  // rejilla vertical (cada 10 km; más espaciada en rutas largas) y km rotulados donde caben
  const rej = total <= 300 ? 10 : total <= 1000 ? 50 : 100;
  const rot = [1, 2, 5, 10, 20, 50].map(f => f * rej).find(p => (W - m.l - m.r) * p / total >= 50) || 50 * rej;
  for (let k = rej; k < total; k += rej)
    s += `<line x1="${X(k)}" x2="${X(k)}" y1="${m.t}" y2="${Y(0)}" stroke="#000" stroke-opacity=".16" stroke-width="1"/>`;
  for (let k = 0; k <= total; k += rot)
    s += `<text x="${X(k)}" y="${H-8}" font-size="19" text-anchor="middle" fill="#666">${k}</text>`;
  for (const r of res) if (r.control) {
    s += `<line x1="${X(r.km)}" x2="${X(r.km)}" y1="${Y(r.alt)}" y2="${m.t}" stroke="${tarde(r) ? "#c62828" : "#555"}" stroke-width="2.5"/>`
       + `<text x="${X(r.km)+4}" y="${m.t-6}" font-size="19" font-weight="700" fill="#333">${r.control}</text>`;
  }
  // iconos de los puntos (café, puerto, población…) en una fila sobre el perfil, con su km y una línea
  // hasta el eje; si dos se tocan, el segundo sube una fila. La salida y la llegada no llevan: son los extremos.
  conIcono.forEach((r, i) => {
    const x = X(r.km), n = filaDe[i];
    const yk = fila0 - n * FILA, y = yk - 14 - R;
    s += `<g><title>${esc(r.nombre)}</title><line x1="${x}" x2="${x}" y1="${Y(0)}" y2="${yk}" stroke="#333" stroke-width="1.2" stroke-dasharray="4 3"/>`
       + `<text x="${x}" y="${yk}" font-size="14" text-anchor="middle" fill="#333" stroke="#fff" stroke-width="4" paint-order="stroke">${kmTexto(r.km)}</text>`
       + `<circle cx="${x}" cy="${y}" r="${R}" fill="#fff" stroke="#333" stroke-width="1.5"/>`
       + `<text x="${x}" y="${y + 1}" font-size="15" text-anchor="middle" dominant-baseline="central">${ICONOS[r.tipo]}</text>`
       + (conNombre ? `<text x="${ladoDe[i] ? x - R - 5 : x + R + 5}" y="${y + 1}" font-size="14" font-weight="600" text-anchor="${ladoDe[i] ? "end" : "start"}" dominant-baseline="central" fill="#333" stroke="#fff" stroke-width="4" paint-order="stroke">${esc(r.nombre)}</text>` : "")
       + `</g>`;
  });
  svg.innerHTML = s;
}

// ---------- tabla
function dibujarTabla(res) {
  const cab = ["", "Lugar", "km", "Tramo", "Alt.", "Asc. tramo", "Asc. total", "% medio"]
    .concat(PUERTO ? [] : ["Vel.", "Parada (min)", "Llegada", "Salida"])
    .concat(CON_LIMITE && !PUERTO ? [OBJETIVO ? "Objetivo" : "Cierre", "Margen", "Apertura"] : []);
  const CLASE = {"Tramo": "c2", "Asc. tramo": "c2", "% medio": "c2", "Vel.": "c2", "Alt.": "c3", "Salida": "c3", "Apertura": "c3"};
  const cls = c => CLASE[c] ? ` class="${CLASE[c]}"` : "";
  let s = "<thead><tr>" + cab.map(c => `<th${cls(c)}>${c}</th>`).join("") + "</tr></thead><tbody>";
  res.forEach((r, i) => {
    const valor = estado.paradas[i] === null ? "" : estado.paradas[i];
    const marcador = r.control ? (r.parada || "") : "";
    s += `<tr class="${r.control ? "ctrl" : ""}"><td class="n">${r.control}</td>
      <td class="n"><span class="dia" style="background:${color(r.dia)}"></span>${icono(r)}${esc(r.nombre)}</td>
      <td>${r.km.toFixed(1)}</td><td class="c2">${r.km_tramo.toFixed(1)}</td><td class="c3">${r.alt.toFixed(0)}</td>
      <td class="c2">${r.asc_tramo.toFixed(0)}</td><td>${r.asc_total.toFixed(0)}</td><td class="c2">${(r.pendiente*100).toFixed(1)}%</td>` + (PUERTO ? "</tr>" : `
      <td class="c2">${r.vel ? r.vel.toFixed(1) : ""}</td>
      <td>${i ? `<input type="number" min="0" step="5" data-i="${i}" value="${valor}" placeholder="${marcador}">` : ""}</td>
      <td>${momento(r.llegada)}</td><td class="c3">${momento(r.salida)}</td>` + (!CON_LIMITE ? "</tr>" : `
      <td>${momento(r.cierre)}</td>
      <td class="${r.margen < -TOLERANCIA ? "neg" : "pos"}">${i ? dur(r.margen, true) : ""}</td>
      <td class="c3 ${r.antes ? "neg" : ""}">${r.apertura ? hora(r.apertura) + (r.antes ? " ⚠" : "") : ""}</td></tr>`));
  });
  document.getElementById("tabla").innerHTML = s + "</tbody>";
  document.querySelectorAll("#tabla input").forEach(inp => inp.onchange = e => {
    const v = e.target.value.trim();
    estado.paradas[+e.target.dataset.i] = v === "" ? null : Math.max(0, +v);
    todo();
  });
}

// cifras del resumen en tarjetas: valor grande y qué es debajo
const dato = (valor, etiqueta, clase = "") => `<div class="dato"><b class="${clase}">${valor}</b><span>${etiqueta}</span></div>`;
const basicos = () => dato(D.total_km.toFixed(0) + " km", "distancia") + dato("+" + Math.round(D.total_asc).toLocaleString("es") + " m", "desnivel");
function dibujarResumen(res) {
  const fin = res[res.length - 1];
  const totalMin = (fin.llegada - estado.salida) / 60e3;
  const peor = res.slice(1).filter(r => r.control).reduce((a, b) => b.margen < a.margen ? b : a, fin);
  const dias = [...new Set(res.map(r => r.dia))];
  if (PUERTO) {
    const pend = D.total_km ? (res[res.length - 1].alt - res[0].alt) / (D.total_km * 10) : 0;
    document.getElementById("resumen").innerHTML =
      dato(D.total_km.toFixed(1).replace(".", ",") + " km", "distancia") + dato("+" + Math.round(res[res.length - 1].alt - res[0].alt).toLocaleString("es") + " m", "desnivel")
      + dato(pend.toFixed(1).replace(".", ",") + " %", "pendiente media");
    document.getElementById("dias").innerHTML = "";
    return;
  }
  if (!CON_SALIDA) {
    document.getElementById("resumen").innerHTML =
      basicos() + dato(dur(totalMin) + " h", "tiempo previsto") + (dias.length > 1 ? dato(dias.length, "días") : "")
       + (CON_LIMITE ? dato(dur(estado.limite * 60) + " h", OBJETIVO ? "objetivo" : "límite")
                       + dato(dur(fin.margen, true) + " h", "margen en meta", fin.margen < -TOLERANCIA ? "neg" : "pos") : "");
    document.getElementById("dias").innerHTML = dias.length > 1 ? dias.map(d => `<span class="chip" style="background:${color(d)}">Día ${d + 1}</span>`).join("") : "";
    return;
  }
  document.getElementById("resumen").innerHTML =
    basicos() + dato(`${fin.llegada.getDate()}/${fin.llegada.getMonth()+1} ${hhmm(fin.llegada)}`, "llegada")
    + dato(dur(totalMin) + " h", "tiempo previsto") + (!CON_LIMITE ? "" :
      dato(dur(fin.margen, true) + " h", "margen en meta", fin.margen < -TOLERANCIA ? "neg" : "pos")
      + dato(dur(peor.margen, true) + " h", `margen mínimo (${esc(peor.control)} ${esc(peor.nombre)})`, peor.margen < -TOLERANCIA ? "neg" : "pos"));
  document.getElementById("dias").innerHTML = dias.map(d => {
    const f = new Date(estado.salida.getFullYear(), estado.salida.getMonth(), estado.salida.getDate() + d);
    return `<span class="chip" style="background:${color(d)}">${f.getDate()} ${MESES_L[f.getMonth()]}</span>`;
  }).join("");
}

function todo() {
  const res = calcular();
  dibujarResumen(res); dibujarMapa(res); dibujarPerfil(res); dibujarTabla(res);
}

document.getElementById("titulo").textContent = D.nombre;
document.getElementById("subtitulo").textContent = D.subtitulo || "";
const inSalida = document.getElementById("salida"), inLimite = document.getElementById("limite"), inDefecto = document.getElementById("defecto");
inSalida.value = aLocal(estado.salida); inLimite.value = estado.limite; inDefecto.value = estado.defecto;
inSalida.onchange = () => { if (inSalida.value) { estado.salida = new Date(inSalida.value); todo(); } };
inLimite.onchange = () => { estado.limite = +inLimite.value || estado.limite; todo(); };
inDefecto.onchange = () => { estado.defecto = Math.max(0, +inDefecto.value || 0); todo(); };
window.addEventListener("resize", () => dibujarPerfil(calcular()));
// en la ficha (o sin hora de salida) no hay fecha; en la ficha (o sin límite), tampoco tiempo límite
if (!CON_SALIDA) inSalida.closest("label").hidden = true;
if (!CON_LIMITE) inLimite.closest("label").hidden = true;
// la parada por defecto en los controles solo se muestra en una ruta oficial (con tiempo límite y cierres, no objetivo)
// que tenga controles de paso intermedios; en las demás (y en la ficha para una web) no aparece
if (!(CON_LIMITE && !OBJETIVO && D.puntos.some((p, i) => p.control && i > 0 && i < D.puntos.length - 1))) inDefecto.closest("label").hidden = true;
if (OBJETIVO) document.getElementById("etiqueta-limite").textContent = "Objetivo (h)";
if (!CON_SALIDA) document.getElementById("nota-pie").insertAdjacentHTML("beforeend", "<br>Tiempos en horas:minutos desde la salida, con las paradas previstas; cambia las paradas en la tabla.");
// GPX hecho aquí mismo (la página se comparte suelta, sin servidor): track y puntos como waypoints
document.getElementById("nombres").onchange = () => todo();
document.getElementById("descargar-gpx").onclick = () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([D.gpx.texto], {type: "application/gpx+xml"}));
  a.download = D.gpx.nombre;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
todo();
// Insertada en otra web (iframe): envía su altura a la página que la contiene; venb-insertar.js (cargado en esa página)
// ajusta el iframe y no hay desplazamiento dentro. Formato fijo y con versión: {tipo: "venb-ruta", version: 1, altura};
// si venb-insertar.js carga después, pide la altura con {tipo: "venb-ruta", version: 1, pedir: "altura"}.
// Sin venb-insertar.js, el mensaje no hace nada.
if (window.self !== window.top) {
  document.documentElement.classList.add("insertada");
  // en un blog con barra lateral el iframe queda estrecho: la misma página en una pestaña nueva
  const grande = document.createElement("a");
  grande.className = "boton secundario"; grande.href = location.href; grande.target = "_blank"; grande.rel = "noopener";
  grande.innerHTML = '<span aria-hidden="true">⛶</span> Ver a pantalla completa'; grande.title = "Abre la ruta en una pestaña nueva, a pantalla completa";
  document.getElementById("acciones").appendChild(grande);
  let ultima = 0;
  const avisar = () => {
    const h = Math.ceil(document.documentElement.scrollHeight);
    if (Math.abs(h - ultima) > 2) { ultima = h; window.parent.postMessage({tipo: "venb-ruta", version: 1, altura: h}, "*"); }
  };
  new ResizeObserver(avisar).observe(document.body);
  window.addEventListener("load", avisar);
  // venb-insertar.js puede cargarse después que la ruta: al cargar, pide la altura y aquí se vuelve a enviar
  window.addEventListener("message", e => {
    if (e.source === window.parent && e.data && e.data.tipo === "venb-ruta" && e.data.pedir === "altura") { ultima = 0; avisar(); }
  });
  avisar();
}
</script>
</body>
</html>
"""


def _logo_b64(ruta, alto=160):
    """PNG incrustable (data URL), reducido a `alto` px: los originales de los clubes pueden ser enormes."""
    import base64
    import io
    from PIL import Image
    im = Image.open(ruta).convert("RGBA")
    if im.height > alto:
        im = im.resize((max(1, round(im.width * alto / im.height)), alto), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _marca_html(proyecto):
    """(cabecera, pie): el promotor (club de VenB Rutas o marca propia de Ajustes) destacado arriba, con su nombre y un
    botón a su web; el crédito de VenB / Vivir en bici, discreto, al pie. Sin promotor, la cabecera queda vacía."""
    import html as h
    import re
    from pathlib import Path
    marca = proyecto.seccion("marca")
    club = marca.get("club")
    if club:
        nombre, web, logos = club.get("nombre") or "", club.get("web") or "", list(club.get("logos") or [])
    else:
        texto = marca.get("texto") or " - ".join(t for t in (marca.get("nombre"), marca.get("web")) if t)
        logos = []
        if marca.get("logo"):
            ruta = Path(marca["logo"])
            logos = [ruta if ruta.is_absolute() else proyecto.base / ruta]
        m = re.search(r"https?://\S+", texto)
        web = m.group(0) if m else ""
        nombre = re.sub(r"\s*[-·|]\s*$", "", texto.replace(web, "")).strip() if web else texto.strip()
        if "vivirenbici" in texto.lower() or "vivir en bici" in texto.lower():
            nombre, web, logos = "", "", []      # la marca de VenB no es un promotor: va al pie
    partes = []
    imgs = "".join(f'<img src="{_logo_b64(r)}" alt="">' for r in logos if Path(r).exists())
    if imgs:
        partes.append(f'<div class="promotor-logos">{imgs}</div>')
    if nombre or web:
        dominio = re.sub(r"^https?://(www\.)?", "", web).rstrip("/")
        enlace = (f'<a class="promotor-web" href="{h.escape(web)}" target="_blank" rel="noopener" '
                  f'title="Abre la web en una pestaña nueva">{h.escape(dominio)} <span aria-hidden="true">↗</span></a>') if web else ""
        partes.append(f'<div class="promotor-texto"><div class="promotor-nombre">{h.escape(nombre or dominio)}</div>{enlace}</div>')
    cabecera = f'<div class="promotor">{"".join(partes)}</div>' if partes else ""
    pie = ('<div class="credito"><a href="https://www.vivirenbici.es" target="_blank" rel="noopener">'
           f'<img src="{_logo_b64(Path(__file__).parent / "recursos" / "logo_marca.png", 48)}" alt="">'
           'Ruta preparada con VenB · vivirenbici.es</a></div>')
    return cabecera, pie


def _base(tr):
    """Mapa base inicial: el topográfico del IGN si cubre todo el track (solo España); si no, OpenTopoMap."""
    from .teselas import a_mercator, cubre
    try:
        return "ign_mtn" if cubre("ign_mtn", 11, *a_mercator(tr.lon, tr.lat)) else "topo"
    except Exception:
        return "topo"


def _mayus(texto, fichero=False):
    """MAYÚSCULAS sin tildes (como en los GPX de Garmin Connect); la Ñ se conserva salvo en nombres de fichero."""
    import unicodedata
    t = str(texto).upper().replace("Ñ", "\0")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = t.replace("\0", "N" if fichero else "Ñ")
    if fichero:
        t = re.sub(r"[^A-Z0-9]+", "_", t).strip("_")
    return re.sub(r"\s+", " ", t).strip()


def _trazo(tr):
    """Puntos para dibujar el track en el mapa interactivo: [[lat, lon, km]]. Los del GPX original
    simplificados a 1,5 m (antes, uno cada 250 m: las curvas salían cortadas en recta)."""
    idx = tr.trazado(1.5)
    if idx is None:   # track sin los puntos originales: el remuestreado cada 25 m
        from .datos import simplificar
        lat, lon, km = tr.lat, tr.lon, tr.km
        idx = simplificar(lat, lon, 1.5)
    else:
        lat, lon, km = tr.orig_lat, tr.orig_lon, tr.orig_km
    return [[round(float(lat[i]), 6), round(float(lon[i]), 6), round(float(km[i]), 3)] for i in idx]


def _puntos_gpx(tr):
    """Track del GPX descargable: los vértices del GPX original (simplificados a 1,5 m) más un punto cada
    25 m, para que la geometría sea la del original y el perfil de altitud conserve su detalle."""
    if tr.orig_lat is None:
        return tr.lat, tr.lon, tr.ele, tr.km
    idx = tr.trazado(1.5)
    km = np.r_[tr.km, tr.orig_km[idx]]
    lat, lon = np.r_[tr.lat, tr.orig_lat[idx]], np.r_[tr.lon, tr.orig_lon[idx]]
    orden = np.argsort(km, kind="stable")
    km, lat, lon = km[orden], lat[orden], lon[orden]
    # fuera duplicados (mismo km y posición, p. ej. el primer y el último punto)
    nuevo = np.r_[True, (np.diff(km) > 1e-6) | (np.abs(np.diff(lat)) > 1e-7) | (np.abs(np.diff(lon)) > 1e-7)]
    km, lat, lon = km[nuevo], lat[nuevo], lon[nuevo]
    return lat, lon, np.interp(km, tr.km, tr.ele), km


def gpx_waypoints(proyecto, plan):
    """(nombre de fichero, texto) del GPX de la ruta con todos sus puntos (los de la hoja y los añadidos a mano)
    como waypoints con los tipos del creador de rutas de Garmin Connect: CHECKPOINT en los controles,
    SEGMENT START / SEGMENT END en la salida y la llegada y GENERIC en el resto. Nombre: BRM200_SALIDA_WP.gpx."""
    from xml.sax.saxutils import escape
    regla = proyecto.cfg.get("regla") or {}
    if regla.get("distancia"):
        prefijo = f"{regla.get('prefijo', 'BRM')}{regla['distancia']}"
    else:
        prefijo = f"RUTA{plan.total_km:.0f}"
    pts = plan.puntos
    nombre = f"{prefijo}_{_mayus(pts[0].nombre, fichero=True) or 'SALIDA'}_WP.gpx"
    wpts = []
    for i, p in enumerate(pts):
        if p.lat is None or p.lon is None:
            continue
        tipo = ("SEGMENT START" if i == 0 else "SEGMENT END" if i == len(pts) - 1
                else "CHECKPOINT" if p.es_control else "GENERIC")
        texto = _mayus(p.nombre)
        if p.es_control and p.control:
            texto = f"{p.control}_{texto}"
        wpts.append(f'  <wpt lat="{p.lat:.6f}" lon="{p.lon:.6f}"><ele>{p.alt:.1f}</ele><name>{escape(texto)}</name>'
                    f"<type>{tipo}</type></wpt>")
    lat, lon, ele, _ = _puntos_gpx(plan.track)
    trk = "\n".join(f'      <trkpt lat="{a:.6f}" lon="{b:.6f}"><ele>{c:.1f}</ele></trkpt>'
                    for a, b, c in zip(lat, lon, ele))
    titulo = escape(nombre[:-4])
    texto = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<gpx version="1.1" creator="VenB" xmlns="http://www.topografix.com/GPX/1/1">\n'
             f"  <metadata><name>{titulo}</name></metadata>\n" + "\n".join(wpts) +
             f"\n  <trk><name>{titulo}</name>\n    <trkseg>\n{trk}\n    </trkseg>\n  </trk>\n</gpx>\n")
    return nombre, texto


def generar_gpx(proyecto, plan):
    """Escribe el GPX con waypoints en la carpeta de salida y devuelve su ruta."""
    nombre, texto = gpx_waypoints(proyecto, plan)
    ruta = proyecto.salida_dir / nombre
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def generar(proyecto, plan):
    tr = plan.track
    paso = max(1, int(round(0.25 / (tr.km[1] - tr.km[0]))))   # perfil: un punto cada ~250 m
    idx = np.r_[np.arange(0, len(tr.km), paso), len(tr.km) - 1]
    track = [[round(float(tr.lat[i]), 5), round(float(tr.lon[i]), 5), round(float(tr.ele[i]), 1),
              round(float(tr.km[i]), 3)] for i in idx]
    cfg_paradas = dict(proyecto.seccion("paradas"))
    defecto = cfg_paradas.pop("por_defecto_min", 0)
    puntos = []
    for i, p in enumerate(plan.puntos):
        es_defecto = p.es_control and i < len(plan.puntos) - 1 and p.parada_min == defecto
        puntos.append({
            "nombre": p.nombre, "control": p.control, "destacado": p.destacado,
            "km": round(p.km, 3), "km_tramo": round(p.km_tramo, 3), "lat": p.lat, "lon": p.lon,
            "alt": round(p.alt, 1), "asc_tramo": round(p.asc_tramo, 1), "asc_total": round(p.asc_total, 1),
            "pendiente": p.pendiente, "tipo": p.tipo_parada,
            # null = usa la parada por defecto (editable en la página)
            "parada": None if (es_defecto or (not p.es_control and not p.parada_min)) else p.parada_min,
            "cierre_hoja": p.cierre_hoja.isoformat() if p.cierre_hoja and "cierre_rm_h" not in p.extra else None,
            "apertura_hoja": p.apertura_hoja.isoformat() if p.apertura_hoja and "apertura_rm_h" not in p.extra else None,
            # reglas de Randonneurs Mondiaux: horas desde la salida, que se puede cambiar en la página
            "cierre_h": p.extra.get("cierre_rm_h"), "apertura_h": p.extra.get("apertura_rm_h"),
        })
    datos = {"nombre": plan.nombre, "subtitulo": proyecto.cfg.get("subtitulo", ""),
             "salida": plan.salida.isoformat(), "limite_h": plan.limite_h, "parada_defecto": defecto,
             "horario": getattr(plan, "horario", {"salida": True, "limite": True}),
             "puerto": bool(getattr(plan, "puerto", None)),
             "total_km": plan.total_km, "total_asc": plan.total_asc, "track": track, "puntos": puntos,
             "trazo": _trazo(tr),   # geometría del mapa; "track" (cada ~250 m) queda para el perfil
             "velocidades": plan.velocidades, "base": _base(tr),
             # «Descargar GPX»: el mismo fichero que genera el Planificador (track completo y waypoints)
             "gpx": dict(zip(("nombre", "texto"), gpx_waypoints(proyecto, plan)))}
    import html as h
    # "</" escapado: un nombre de la hoja no puede cerrar el <script> que lleva los datos
    cabecera, pie = _marca_html(proyecto)
    html = (PLANTILLA.replace("__TITULO__", h.escape(plan.nombre))
            .replace("__MARCA__", cabecera).replace("__CREDITO__", pie)
            .replace("__DATOS__", json.dumps(datos, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__COLORES__", json.dumps(E.COLORES_DIA))
            .replace("__ICONOS__", json.dumps(E.ICONOS, ensure_ascii=False))
            .replace("__PENDIENTES__", json.dumps(E.COLORES_PENDIENTE)))
    ruta = proyecto.salida_dir / "ruta_interactiva.html"
    ruta.write_text(html, encoding="utf-8")
    return ruta
