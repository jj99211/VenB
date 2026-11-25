// Perfiles de puertos: perfil de la ruta con los puertos marcados, edición de tramos y puntos, generación y progreso.
(function () {
  const nodo = document.getElementById('datos-puertos');
  if (!nodo) return;
  const D = JSON.parse(nodo.textContent);
  const num = (v, d = 0) => Number(v).toLocaleString('es-ES', {minimumFractionDigits: d, maximumFractionDigits: d});

  async function enviar(url, datos) {
    const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(datos || {})});
    let j = {};
    try { j = await r.json(); } catch (e) { /* sin cuerpo */ }
    if (!r.ok) throw new Error(j.error || `Error ${r.status}`);
    return j;
  }

  // ---- progreso: la página se recarga al cambiar de fase
  function seguir() {
    const t = setInterval(async () => {
      try {
        const e = await (await fetch(D.urlEstado)).json();
        document.querySelectorAll('pre.registro').forEach(p => { p.textContent = (e.registro || []).join('\n'); });
        const paso = document.getElementById('paso-generar');
        if (paso && e.registro && e.registro.length) paso.textContent = e.registro[e.registro.length - 1];
        if (e.fase !== D.fase) { clearInterval(t); location.reload(); }
      } catch (err) { /* VenB ocupada: se reintenta */ }
    }, 2000);
  }
  if (D.fase === 'analizando' || D.fase === 'generando') seguir();
  document.querySelectorAll('#detener, #detener-generar').forEach(b => b.addEventListener('click', async () => {
    b.disabled = true;
    try { await enviar(D.urlDetener); location.reload(); } catch (err) { alert(err.message); b.disabled = false; }
  }));
  if (!D.a) return;

  // ---- perfil de la ruta con los puertos
  const svg = document.getElementById('perfil-ruta');
  if (svg && D.a.perfil && D.a.perfil.length > 1) {
    const P = D.a.perfil, W = 1000, H = 220, m = {l: 48, r: 10, t: 26, b: 22};
    const kmMax = P[P.length - 1][0], eMin = Math.min(...P.map(p => p[1]), D.a.alt_min ?? Infinity), eMax = Math.max(...P.map(p => p[1]), D.a.alt_max ?? -Infinity);
    const base = Math.floor((eMin - (eMax - eMin) * 0.08) / 50) * 50;
    const x = k => m.l + k / kmMax * (W - m.l - m.r);
    const y = e => H - m.b - (e - base) / Math.max(eMax - base, 1) * (H - m.t - m.b);
    const ns = 'http://www.w3.org/2000/svg';
    const el = (tag, at, txt) => { const n = document.createElementNS(ns, tag); for (const k in at) n.setAttribute(k, at[k]); if (txt != null) n.textContent = txt; svg.appendChild(n); return n; };
    const colores = {E: '#4a0c0c', '1': '#a51d1d', '2': '#de4f2a', '3': '#ee8f35', '4': '#f2c14e'};
    D.puertos.forEach((p, i) => {
      const sel = P.filter(q => q[0] >= p.km0 && q[0] <= p.km1);
      if (sel.length < 2) return;
      const pts = [[p.km0, base], ...sel, [p.km1, base]].map(q => `${x(q[0]).toFixed(1)},${y(q[1]).toFixed(1)}`).join(' ');
      el('polygon', {points: pts, fill: colores[p.cat] || '#bbbbbb', opacity: p.incluir ? 0.9 : 0.35});
      const t = el('text', {x: x((p.km0 + p.km1) / 2), y: y(Math.max(...sel.map(q => q[1]))) - 6, 'text-anchor': 'middle', class: 'etq-puerto'}, `${i + 1}`);
      t.appendChild(document.createElementNS(ns, 'title')).textContent = `${p.nombre}: ${p.categoria || 'sin categoría'}, coeficiente ${p.coef}`;
    });
    el('polyline', {points: P.map(q => `${x(q[0]).toFixed(1)},${y(q[1]).toFixed(1)}`).join(' '), fill: 'none', stroke: '#333', 'stroke-width': 1.5});
    const paso = [5, 10, 20, 25, 50, 100, 200].find(s => kmMax / s <= 12) || 500;
    for (let k = 0; k <= kmMax; k += paso) el('text', {x: x(k), y: H - 6, 'text-anchor': 'middle', class: 'eje'}, `${k}`);
    el('text', {x: 4, y: y(eMax) + 4, class: 'eje'}, `${num(eMax)} m`);
    el('text', {x: 4, y: y(base) - 2, class: 'eje'}, `${num(base)} m`);
    const guia = el('line', {x1: 0, x2: 0, y1: m.t, y2: H - m.b, stroke: '#2c5aa0', 'stroke-width': 1, visibility: 'hidden'});
    const info = el('text', {x: m.l, y: 14, class: 'eje'}, '');
    svg.addEventListener('mousemove', ev => {
      const r = svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) / r.width * W;
      const k = Math.min(Math.max((px - m.l) / (W - m.l - m.r) * kmMax, 0), kmMax);
      const q = P.reduce((a, b) => Math.abs(b[0] - k) < Math.abs(a[0] - k) ? b : a);
      guia.setAttribute('x1', x(q[0])); guia.setAttribute('x2', x(q[0])); guia.setAttribute('visibility', 'visible');
      info.textContent = `km ${num(q[0], 1)} · ${num(q[1])} m`;
    });
    svg.addEventListener('mouseleave', () => { guia.setAttribute('visibility', 'hidden'); info.textContent = ''; });
  }

  // ---- edición de tramos y puntos
  const tipos = Object.entries(D.tipos);
  function filaPunto(nombre, km, tipo) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="num">·</td><td><input type="text" class="w-nombre" maxlength="60" aria-label="Nombre del punto"></td>' +
      '<td class="num"><span class="con-mapa"><input type="number" class="w-km" step="0.05" aria-label="km"><button type="button" class="discreto ed-mapa" title="Elegir el punto en el mapa" aria-label="Elegir el punto en el mapa">📍</button></span></td><td><select class="w-tipo" aria-label="Tipo"></select></td>' +
      '<td class="num suave">al guardar</td><td><button type="button" class="discreto w-quitar">Quitar</button></td>';
    tr.querySelector('.w-nombre').value = nombre;
    tr.querySelector('.w-km').value = km;
    const s = tr.querySelector('.w-tipo');
    tipos.forEach(([k, v]) => { const o = new Option(v, k, false, k === tipo); s.add(o); });
    return tr;
  }
  document.addEventListener('click', ev => {
    const b = ev.target;
    if (b.classList.contains('w-quitar')) b.closest('tr').remove();
    if (b.classList.contains('w-anadir')) {
      const art = b.closest('.puerto-tramo');
      const k0 = parseFloat(art.querySelector('.p-km0').value), k1 = parseFloat(art.querySelector('.p-km1').value);
      const fila = filaPunto('', ((k0 + k1) / 2).toFixed(2), '');
      art.querySelector('tbody').appendChild(fila);
      fila.querySelector('.w-nombre').focus();
    }
    if (b.classList.contains('p-quitar')) {
      const art = b.closest('.puerto-tramo');
      if (confirm(`¿Quitar «${art.querySelector('.p-nombre').value}» de la lista? Se guarda al pulsar «Guardar cambios».`)) art.remove();
    }
  });

  // ---- elegir en el mapa (como en el Planificador): el punto del track más cercano a donde se pulsa,
  // dentro del tramo del puerto (con un margen) para no saltar a otro paso de la ruta por el mismo sitio
  const $ = id => document.getElementById(id);
  const dm = $('dialogo-mapa');
  let TR = null, mapa = null, marca = null, resalte = null, elegido = null, alHecho = null, rango = null;
  const metros = (a, b) => { const k = Math.cos(a[0] * Math.PI / 180); return Math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * k); };
  function cercanos(ll) {
    const d = TR.map((p, i) => (p[2] >= rango[0] && p[2] <= rango[1]) ? metros(p, ll) : Infinity), mejor = Math.min(...d), pasos = [];
    if (!isFinite(mejor)) return [];
    d.forEach((x, i) => {
      if (x > mejor * 1.5 + 100) return;
      const u = pasos[pasos.length - 1];
      if (u && TR[i][2] - TR[u.i][2] < 2) { if (x < u.d) Object.assign(u, {i, d: x}); }
      else pasos.push({i, d: x});
    });
    return pasos.sort((a, b) => a.d - b.d);
  }
  function marcar(i, d) {
    const p = TR[i];
    elegido = {km: Math.round(p[2] * 100) / 100, nombre: elegido && elegido.nombre};
    if (marca) marca.setLatLng([p[0], p[1]]); else marca = L.marker([p[0], p[1]]).addTo(mapa);
    $('mapa-resultado').textContent = `km ${num(elegido.km, 2)} del track` + (d !== undefined ? ` (a ${num(d)} m de donde has pulsado)` : '') + (elegido.nombre ? ` · ${elegido.nombre}` : '');
    $('mapa-usar').disabled = false;
  }
  function localidad(ll) {
    fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=14&accept-language=es&lat=${ll[0].toFixed(5)}&lon=${ll[1].toFixed(5)}`)
      .then(r => r.json()).then(j => {
        const a = j.address || {}, n = a.village || a.town || a.city || a.hamlet || a.municipality || '';
        if (n && elegido) { elegido.nombre = n; $('mapa-resultado').textContent += ` · ${n}`; }
      }).catch(() => {});
  }
  function prepararMapa() {
    mapa = L.map('mapa-puntos');
    const espana = TR.every(p => p[0] > 35 && p[0] < 44 && p[1] > -10 && p[1] < 4.5);
    const capas = {
      'IGN: topográfico': L.tileLayer('https://tms-mapa-raster.ign.es/1.0.0/mapa-raster/{z}/{x}/{y}.jpeg', {tms: true, maxZoom: 17, attribution: '© IGN España (CC BY 4.0)'}),
      'OpenStreetMap': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '© OpenStreetMap'}),
    };
    (espana ? capas['IGN: topográfico'] : capas.OpenStreetMap).addTo(mapa);
    L.control.layers(capas).addTo(mapa);
    L.polyline(TR.map(p => [p[0], p[1]]), {color: '#555', weight: 3, opacity: .6}).addTo(mapa);
    mapa.on('click', ev => {
      const ll = [ev.latlng.lat, ev.latlng.lng], pasos = cercanos(ll);
      if (!pasos.length) return;
      elegido = null;
      marcar(pasos[0].i, pasos[0].d);
      $('mapa-alternativas').innerHTML = pasos.length > 1 ? 'El track pasa varias veces por aquí: ' + pasos.map(x =>
        `<button type="button" class="discreto" data-i="${x.i}" data-d="${Math.round(x.d)}">km ${num(TR[x.i][2], 2)}</button>`).join(' ') : '';
      if (alHecho && alHecho.nombre) localidad(ll);
    });
  }
  if (dm) {
    $('mapa-alternativas').addEventListener('click', ev => { const b = ev.target.closest('button'); if (b) marcar(+b.dataset.i, +b.dataset.d); });
    $('mapa-usar').addEventListener('click', () => { const r = elegido; dm.close(); if (r && alHecho) alHecho.fn(r); });
    $('mapa-cancelar').addEventListener('click', () => dm.close());
  }
  async function elegirEnMapa(kmActual, k0, k1, pedirNombre, hecho) {
    alHecho = {fn: hecho, nombre: pedirNombre};
    elegido = null; $('mapa-usar').disabled = true; $('mapa-resultado').textContent = ''; $('mapa-alternativas').innerHTML = '';
    dm.showModal();
    if (!window.L) { $('mapa-resultado').textContent = 'No se ha podido cargar el mapa: comprueba la conexión a Internet.'; return; }
    if (!TR) {
      $('mapa-resultado').textContent = 'Cargando el track…';
      try { TR = await fetch(D.urlTrazado).then(r => r.json()); } catch (e) { TR = []; }
      if (TR.length < 2) { $('mapa-resultado').textContent = 'No se ha podido leer el track.'; TR = null; return; }
      $('mapa-resultado').textContent = '';
      prepararMapa();
    }
    // margen alrededor del tramo: 2 km o la mitad de su longitud, para poder alargar el pie o la cima
    const largo = isFinite(k0) && isFinite(k1) ? Math.abs(k1 - k0) : NaN;
    const mg = isFinite(largo) ? Math.max(2, largo / 2) : Infinity;
    rango = isFinite(largo) ? [Math.min(k0, k1) - mg, Math.max(k0, k1) + mg] : [-Infinity, Infinity];
    if (resalte) resalte.remove();
    const tramo = TR.filter(p => isFinite(largo) && p[2] >= Math.min(k0, k1) && p[2] <= Math.max(k0, k1)).map(p => [p[0], p[1]]);
    resalte = tramo.length > 1 ? L.polyline(tramo, {color: '#c62828', weight: 5, opacity: .9}).addTo(mapa) : null;
    mapa.invalidateSize();
    if (marca) { marca.remove(); marca = null; }
    const k = parseFloat(kmActual);
    if (resalte) mapa.fitBounds(resalte.getBounds(), {padding: [30, 30]});
    else mapa.fitBounds(L.latLngBounds(TR.map(p => [p[0], p[1]])), {padding: [20, 20]});
    if (isFinite(k)) {
      const i = TR.reduce((a, x, n) => Math.abs(x[2] - k) < Math.abs(TR[a][2] - k) ? n : a, 0);
      marcar(i);
    }
  }
  document.addEventListener('click', ev => {
    const b = ev.target.closest('.ed-mapa');
    if (!b || !dm) return;
    const art = b.closest('.puerto-tramo');
    const k0 = parseFloat(art.querySelector('.p-km0').value), k1 = parseFloat(art.querySelector('.p-km1').value);
    if (b.dataset.campo) {          // pie o cima
      const campo = art.querySelector(`.p-${b.dataset.campo}`);
      elegirEnMapa(campo.value, k0, k1, false, r => { campo.value = r.km.toFixed(2); });
      return;
    }
    const f = b.closest('tr'), nombre = f.querySelector('.w-nombre'), km = f.querySelector('.w-km');
    elegirEnMapa(km.value, k0, k1, !nombre.value.trim(), r => {
      km.value = r.km.toFixed(2);
      if (r.nombre && !nombre.value.trim()) nombre.value = r.nombre;
    });
  });

  function recoger() {
    return [...document.querySelectorAll('.puerto-tramo')].map(art => ({
      id: art.dataset.id,
      incluir: art.querySelector('.p-incluir').checked,
      nombre: art.querySelector('.p-nombre').value,
      subtitulo: art.querySelector('.p-subtitulo').value,
      km0: art.querySelector('.p-km0').value,
      km1: art.querySelector('.p-km1').value,
      manual: (D.puertos.find(p => p.id === art.dataset.id) || {}).manual,
      puntos: [...art.querySelectorAll('tbody tr')].map(tr => ({
        nombre: tr.querySelector('.w-nombre').value, km: tr.querySelector('.w-km').value, tipo: tr.querySelector('.w-tipo').value,
      })).filter(w => w.nombre.trim()),
    }));
  }
  // VenB Rutas: si el análisis aún no tiene club elegido, el último usado (como en el Planificador)
  const club = document.getElementById('club');
  if (club) {
    const ultimo = localStorage.getItem('venb-ultimo-club');
    if (!club.dataset.guardado && ultimo && [...club.options].some(o => o.value === ultimo)) club.value = ultimo;
    club.addEventListener('change', () => localStorage.setItem('venb-ultimo-club', club.value));
  }
  function datosGenerar() {
    return {puertos: recoger(), salidas: [...document.querySelectorAll('.salida:checked')].map(c => c.value),
            estilo_mapa: document.getElementById('estilo-mapa').value, paleta: document.getElementById('paleta').value,
            club: club ? club.value : ''};
  }
  const estadoG = document.getElementById('guardar-estado');
  async function accion(boton, url, datos, texto) {
    boton.disabled = true;
    if (estadoG) estadoG.textContent = texto;
    try { await enviar(url, datos); location.reload(); } catch (err) {
      if (estadoG) estadoG.textContent = '';
      alert(err.message);
      boton.disabled = false;
    }
  }
  const g = document.getElementById('guardar');
  if (g) g.addEventListener('click', () => accion(g, D.urlGuardar, {puertos: recoger()}, 'Guardando…'));
  const nt = document.getElementById('nuevo-tramo');
  if (nt) nt.addEventListener('click', () => accion(nt, D.urlTramo, {puertos: recoger(), km0: document.getElementById('nuevo-km0').value,
                                                                    km1: document.getElementById('nuevo-km1').value}, 'Añadiendo…'));
  document.querySelectorAll('.p-proponer').forEach(b => b.addEventListener('click', () => {
    if (!confirm('¿Sustituir los puntos de este puerto por los que propone OpenStreetMap?')) return;
    accion(b, D.urlProponer, {puertos: recoger(), id: b.closest('.puerto-tramo').dataset.id}, 'Buscando puntos…');
  }));
  const gen = document.getElementById('generar');
  if (gen) gen.addEventListener('click', async () => {
    gen.disabled = true;
    try {
      await enviar(D.urlGenerar, datosGenerar());
      D.fase = 'listo';      // al pasar a «generando» y luego a «hecho», la página se recarga
      document.getElementById('progreso-generar').hidden = false;
      const t = setInterval(async () => {
        const e = await (await fetch(D.urlEstado)).json();
        document.querySelectorAll('pre.registro').forEach(p => { p.textContent = (e.registro || []).join('\n'); });
        const paso = document.getElementById('paso-generar');
        if (paso && e.registro && e.registro.length) paso.textContent = e.registro[e.registro.length - 1];
        if (e.fase !== 'generando') { clearInterval(t); location.reload(); }
      }, 2000);
    } catch (err) { alert(err.message); gen.disabled = false; }
  });
})();
