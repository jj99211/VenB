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
  :root { --tinta:#1f2328; --gris:#6b7280; --linea:#e5e7eb; --fondo:#f7f7f5; --ok:#16855f; --mal:#c62828; }
  * { box-sizing:border-box; }
  body { margin:0; font:24px/1.4 system-ui, "Segoe UI", Roboto, sans-serif; color:var(--tinta); background:var(--fondo); }
  header { padding:14px 20px 10px; background:#fff; border-bottom:1px solid var(--linea); position:relative; }
  .marca { position:absolute; top:12px; right:20px; display:flex; flex-direction:column; align-items:center; gap:6px; }
  .marca img { height:110px; }
  .marca a { color:#b8322a; font-weight:600; font-size:22px; text-decoration:none; }
  .marca a:hover { text-decoration:underline; }
  @media (max-width: 1500px) { .marca { position:static; flex-direction:row; justify-content:flex-start; margin-bottom:8px; } .marca img { height:70px; } }
  h1 { margin:0; font-size:44px; letter-spacing:.3px; }
  h1 small { font-weight:500; color:var(--gris); font-size:28px; margin-left:8px; }
  .datos { display:flex; flex-wrap:wrap; gap:6px 18px; margin-top:6px; color:#333; }
  .datos b { font-variant-numeric:tabular-nums; }
  .controles { display:flex; flex-wrap:wrap; gap:10px 18px; align-items:end; margin-top:10px; }
  .controles label { display:flex; flex-direction:column; font-size:20px; color:var(--gris); gap:2px; }
  .controles input, .controles select { font:inherit; padding:4px 6px; border:1px solid #ccc; border-radius:4px; }
  .controles input[type=number] { width:120px; }
  .controles button { font:inherit; font-size:20px; padding:5px 12px; border:1px solid #888; border-radius:4px; background:#fff; cursor:pointer; }
  .dias { display:flex; gap:6px; flex-wrap:wrap; }
  .chip { color:#fff; padding:5px 12px; border-radius:4px; font-weight:600; font-size:22px; }
  main { display:grid; grid-template-columns:minmax(0, 1.25fr) minmax(0, 1fr); gap:14px; padding:14px 20px; }
  @media (max-width: 1500px) { main { grid-template-columns:1fr; } }
  #mapa { height:62vh; min-height:420px; border-radius:6px; border:1px solid var(--linea); }
  #perfil { width:100%; height:340px; background:#fff; border:1px solid var(--linea); border-radius:6px; margin-top:10px; }
  .tabla { overflow:auto; max-height:calc(62vh + 350px); background:#fff; border:1px solid var(--linea); border-radius:6px; }
  table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
  th, td { padding:6px 10px; border-bottom:1px solid var(--linea); text-align:right; white-space:nowrap; }
  th { position:sticky; top:0; background:#2c5aa0; color:#fff; font-weight:600; font-size:20px; z-index:1; }
  td.n { text-align:left; }
  tr.ctrl td { font-weight:650; background:#fafafa; }
  td input { width:90px; font:inherit; padding:1px 3px; border:1px solid #ccc; border-radius:3px; text-align:right; }
  .pos { color:var(--ok); } .neg { color:var(--mal); font-weight:700; }
  .dia { display:inline-block; width:16px; height:16px; border-radius:2px; margin-right:5px; vertical-align:middle; }
  .caja { color:#fff; padding:10px 14px; border:3px solid #000; font-weight:600; line-height:1.3; font-size:22px; }
  .caja b { font-size:26px; }
  .leaflet-tooltip { font-size:20px; }
  .leaflet-control-attribution { font-size:14px; }
  .leaflet-bar a { width:44px !important; height:44px !important; line-height:44px !important; font-size:28px !important; }
  .leaflet-popup-content { margin:0; } .leaflet-popup-content-wrapper { padding:0; border-radius:0; overflow:hidden; }
  footer { color:var(--gris); font-size:20px; padding:0 20px 16px; }
</style>
</head>
<body>
<header>
  __MARCA__
  <h1 id="titulo"></h1>
  <div class="datos" id="resumen"></div>
  <div class="controles">
    <label>Salida <input type="datetime-local" id="salida"></label>
    <label>Límite (h) <input type="number" id="limite" step="0.5" min="1"></label>
    <label>Parada por defecto en controles (min) <input type="number" id="defecto" step="5" min="0"></label>
    <label>Mapa base
      <select id="base"><option value="ign_mtn">IGN: topográfico (MTN)</option><option value="ign_base">IGN Base</option><option value="ign_orto">IGN: ortofoto con rótulos</option><option value="topo">OpenTopoMap</option><option value="osm">OpenStreetMap</option></select>
    </label>
    <button type="button" id="descargar-gpx" title="Track con los controles, la salida, la llegada y los demás puntos como waypoints (tipos de Garmin Connect)">Descargar GPX con waypoints</button>
    <div class="dias" id="dias"></div>
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
Velocidad según la pendiente media del tramo (ascenso/distancia), con pérdida por fatiga a lo largo de la ruta.</footer>
<script>
const D = __DATOS__;
const COLORES = __COLORES__;
const ICONOS = __ICONOS__;
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
function dur(min, signo) {
  const neg = min < 0; min = Math.round(Math.abs(min));
  return (neg ? "−" : signo ? "+" : "") + Math.floor(min/60) + ":" + String(min%60).padStart(2,"0");
}
const diaDe = (t, t0) => Math.round((new Date(t.getFullYear(),t.getMonth(),t.getDate()) - new Date(t0.getFullYear(),t0.getMonth(),t0.getDate())) / 864e5);
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
mapa.fitBounds(L.latLngBounds(D.track.map(t => [t[0], t[1]])), { padding: [20, 20] });

function horaEnKm(res, km) {
  let i = 1; while (i < res.length - 1 && res[i].km < km) i++;
  const a = res[i-1], b = res[i], f = Math.max(0, Math.min(1, (km - a.km) / Math.max(b.km - a.km, 1e-9)));
  return new Date(a.salida.getTime() + f * (b.llegada - a.salida));
}

function popup(r) {
  const tit = icono(r) + esc((r.control ? r.control + " - " : "") + r.nombre.toUpperCase());
  return `<div class="caja" style="background:${color(r.dia)}"><b>${tit}</b><br>
    km ${r.km.toFixed(0)} (+${r.asc_total.toFixed(0)} m) · ${r.alt.toFixed(0)} m<br>
    ${hhmm(r.llegada)} h${r.parada ? ` (+${r.parada} min)` : ""} &lt; ${hhmm(r.cierre)} h<br>
    margen ${dur(r.margen, true)} h</div>`;
}

function dibujarMapa(res) {
  grupoTrack.clearLayers(); grupoPuntos.clearLayers();
  let tramo = [], diaAct = null;
  const cerrar = () => { if (tramo.length > 1) L.polyline(tramo, { color: color(diaAct), weight: 7, opacity: .9 }).addTo(grupoTrack); };
  const halo = L.polyline(D.track.map(t => [t[0], t[1]]), { color: "#111", weight: 11, opacity: .45 }).addTo(grupoTrack);
  let j = 1;
  for (const t of D.track) {
    while (j < res.length - 1 && res[j].km < t[3]) j++;
    const a = res[j-1], b = res[j], f = Math.max(0, Math.min(1, (t[3] - a.km) / Math.max(b.km - a.km, 1e-9)));
    const d = diaDe(new Date(a.salida.getTime() + f * (b.llegada - a.salida)), estado.salida);
    if (d !== diaAct) { if (tramo.length) { tramo.push([t[0], t[1]]); cerrar(); } tramo = [[t[0], t[1]]]; diaAct = d; }
    else tramo.push([t[0], t[1]]);
  }
  cerrar();
  for (const r of res) {
    if (!(r.control || r.destacado)) {
      L.circleMarker([r.lat, r.lon], { radius: 5, color: "#333", weight: 1.5, fillColor: "#fff", fillOpacity: 1 })
        .bindPopup(popup(r)).addTo(grupoPuntos);
      continue;
    }
    L.circleMarker([r.lat, r.lon], { radius: 11, color: r.margen < 0 ? "#c62828" : "#111", weight: 4, fillColor: "#fff", fillOpacity: 1 })
      .bindPopup(popup(r)).bindTooltip(esc((r.control || "") + " " + r.nombre), { direction: "right" }).addTo(grupoPuntos);
  }
}

// ---------- perfil (SVG)
function dibujarPerfil(res) {
  const svg = document.getElementById("perfil");
  const W = svg.clientWidth || 800, H = svg.clientHeight || 340, m = { l: 80, r: 12, t: 26, b: 52 };
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const maxE = Math.max(...D.track.map(t => t[2])) * 1.1, total = D.total_km;
  const X = km => m.l + km / total * (W - m.l - m.r), Y = e => H - m.b - e / maxE * (H - m.t - m.b);
  let s = "";
  for (let e = 0; e < maxE; e += maxE > 2600 ? 500 : 250)
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
  for (let k = 0; k <= total; k += total > 600 ? 100 : 25)
    s += `<text x="${X(k)}" y="${H-8}" font-size="19" text-anchor="middle" fill="#666">${k}</text>`;
  for (const r of res) if (r.control) {
    s += `<line x1="${X(r.km)}" x2="${X(r.km)}" y1="${Y(r.alt)}" y2="${m.t}" stroke="${r.margen < 0 ? "#c62828" : "#555"}" stroke-width="2.5"/>`
       + `<text x="${X(r.km)+4}" y="${m.t-6}" font-size="19" font-weight="700" fill="#333">${r.control}</text>`;
  }
  svg.innerHTML = s;
}

// ---------- tabla
function dibujarTabla(res) {
  const cab = ["", "Lugar", "km", "Tramo", "Alt.", "Asc. tramo", "Asc. total", "% medio", "Vel.", "Parada (min)", "Llegada", "Salida", "Cierre", "Margen", "Apertura"];
  let s = "<thead><tr>" + cab.map(c => `<th>${c}</th>`).join("") + "</tr></thead><tbody>";
  res.forEach((r, i) => {
    const valor = estado.paradas[i] === null ? "" : estado.paradas[i];
    const marcador = r.control ? (r.parada || "") : "";
    s += `<tr class="${r.control ? "ctrl" : ""}"><td class="n">${r.control}</td>
      <td class="n"><span class="dia" style="background:${color(r.dia)}"></span>${icono(r)}${esc(r.nombre)}</td>
      <td>${r.km.toFixed(1)}</td><td>${r.km_tramo.toFixed(1)}</td><td>${r.alt.toFixed(0)}</td>
      <td>${r.asc_tramo.toFixed(0)}</td><td>${r.asc_total.toFixed(0)}</td><td>${(r.pendiente*100).toFixed(1)}%</td>
      <td>${r.vel ? r.vel.toFixed(1) : ""}</td>
      <td>${i ? `<input type="number" min="0" step="5" data-i="${i}" value="${valor}" placeholder="${marcador}">` : ""}</td>
      <td>${r.llegada.getDate()} · ${hhmm(r.llegada)}</td><td>${r.salida.getDate()} · ${hhmm(r.salida)}</td>
      <td>${r.cierre.getDate()} · ${hhmm(r.cierre)}</td>
      <td class="${r.margen < 0 ? "neg" : "pos"}">${i ? dur(r.margen, true) : ""}</td>
      <td class="${r.antes ? "neg" : ""}">${r.apertura ? hhmm(r.apertura) + (r.antes ? " ⚠" : "") : ""}</td></tr>`;
  });
  document.getElementById("tabla").innerHTML = s + "</tbody>";
  document.querySelectorAll("#tabla input").forEach(inp => inp.onchange = e => {
    const v = e.target.value.trim();
    estado.paradas[+e.target.dataset.i] = v === "" ? null : Math.max(0, +v);
    todo();
  });
}

function dibujarResumen(res) {
  const fin = res[res.length - 1];
  const totalMin = (fin.llegada - estado.salida) / 60e3;
  const peor = res.slice(1).filter(r => r.control).reduce((a, b) => b.margen < a.margen ? b : a);
  document.getElementById("resumen").innerHTML =
    `<span><b>${D.total_km.toFixed(0)}</b> km</span><span><b>+${Math.round(D.total_asc).toLocaleString("es")}</b> m</span>
     <span>llegada <b>${fin.llegada.getDate()}/${fin.llegada.getMonth()+1} ${hhmm(fin.llegada)}</b></span>
     <span>tiempo previsto <b>${dur(totalMin)}</b> h</span>
     <span>margen en meta <b class="${fin.margen < 0 ? "neg" : "pos"}">${dur(fin.margen, true)}</b> h</span>
     <span>margen mínimo <b class="${peor.margen < 0 ? "neg" : "pos"}">${dur(peor.margen, true)}</b> h (${esc(peor.control)} ${esc(peor.nombre)})</span>`;
  const dias = [...new Set(res.map(r => r.dia))];
  document.getElementById("dias").innerHTML = dias.map(d => {
    const f = new Date(estado.salida.getFullYear(), estado.salida.getMonth(), estado.salida.getDate() + d);
    return `<span class="chip" style="background:${color(d)}">${f.getDate()} ${MESES_L[f.getMonth()]}</span>`;
  }).join("");
}

function todo() {
  const res = calcular();
  dibujarResumen(res); dibujarMapa(res); dibujarPerfil(res); dibujarTabla(res);
}

document.getElementById("titulo").innerHTML = esc(D.nombre) + (D.subtitulo ? `<small>${esc(D.subtitulo)}</small>` : "");
const inSalida = document.getElementById("salida"), inLimite = document.getElementById("limite"), inDefecto = document.getElementById("defecto");
inSalida.value = aLocal(estado.salida); inLimite.value = estado.limite; inDefecto.value = estado.defecto;
inSalida.onchange = () => { if (inSalida.value) { estado.salida = new Date(inSalida.value); todo(); } };
inLimite.onchange = () => { estado.limite = +inLimite.value || estado.limite; todo(); };
inDefecto.onchange = () => { estado.defecto = Math.max(0, +inDefecto.value || 0); todo(); };
window.addEventListener("resize", () => dibujarPerfil(calcular()));
// GPX hecho aquí mismo (la página se comparte suelta, sin servidor): track y puntos como waypoints
document.getElementById("descargar-gpx").onclick = () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([D.gpx.texto], {type: "application/gpx+xml"}));
  a.download = D.gpx.nombre;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
todo();
</script>
</body>
</html>
"""


def _marca_html(proyecto):
    """Logotipo (incrustado) y enlace a la web de la sección [marca]."""
    import base64
    import html as h
    import re
    from pathlib import Path
    marca = proyecto.seccion("marca")
    texto = marca.get("texto") or " - ".join(t for t in (marca.get("nombre"), marca.get("web")) if t)
    partes = []
    if marca.get("logo"):
        ruta = Path(marca["logo"])
        ruta = ruta if ruta.is_absolute() else proyecto.base / ruta
        if ruta.exists():
            datos = base64.b64encode(ruta.read_bytes()).decode()
            partes.append(f'<img src="data:image/png;base64,{datos}" alt="logotipo">')
    if texto:
        m = re.search(r"https?://\S+", texto)
        url = m.group(0) if m else ""
        partes.append(f'<a href="{h.escape(url)}" target="_blank" rel="noopener">{h.escape(texto)}</a>'
                      if url else f"<span>{h.escape(texto)}</span>")
    return f'<div class="marca">{"".join(partes)}</div>' if partes else ""


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


def gpx_waypoints(proyecto, plan):
    """(nombre de fichero, texto) del GPX de la ruta con todos sus puntos (los de la hoja y los añadidos a mano)
    como waypoints con los tipos del creador de rutas de Garmin Connect: CHECKPOINT en los controles,
    SEGMENT START / SEGMENT END en la salida y la llegada y GENERIC en el resto. Nombre: BRM200_SALIDA_WP.gpx."""
    from xml.sax.saxutils import escape
    regla = proyecto.cfg.get("regla") or {}
    if regla.get("distancia"):
        prefijo = f"BRM{regla['distancia']}"
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
    tr = plan.track
    trk = "\n".join(f'      <trkpt lat="{a:.5f}" lon="{b:.5f}"><ele>{c:.1f}</ele></trkpt>'
                    for a, b, c in zip(tr.lat, tr.lon, tr.ele))
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
    paso = max(1, int(round(0.25 / (tr.km[1] - tr.km[0]))))   # un punto cada ~250 m
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
             "total_km": plan.total_km, "total_asc": plan.total_asc, "track": track, "puntos": puntos,
             "velocidades": plan.velocidades, "base": _base(tr),
             # «Descargar GPX»: el mismo fichero que genera el Planificador (track completo y waypoints)
             "gpx": dict(zip(("nombre", "texto"), gpx_waypoints(proyecto, plan)))}
    import html as h
    # "</" escapado: un nombre de la hoja no puede cerrar el <script> que lleva los datos
    html = (PLANTILLA.replace("__TITULO__", h.escape(plan.nombre))
            .replace("__MARCA__", _marca_html(proyecto))
            .replace("__DATOS__", json.dumps(datos, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__COLORES__", json.dumps(E.COLORES_DIA))
            .replace("__ICONOS__", json.dumps(E.ICONOS, ensure_ascii=False))
            .replace("__PENDIENTES__", json.dumps(E.COLORES_PENDIENTE)))
    ruta = proyecto.salida_dir / "ruta_interactiva.html"
    ruta.write_text(html, encoding="utf-8")
    return ruta
