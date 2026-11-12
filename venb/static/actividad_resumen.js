// Histórico: ventana flotante con el resumen de una actividad (datos principales, perfil altimétrico y recorrido).
(() => {
  const dlg = document.getElementById('resumen-actividad');
  if (!dlg) return;
  const cuerpo = document.getElementById('ra-cuerpo');
  const NS = 'http://www.w3.org/2000/svg';
  const num = (x, d = 0) => x == null || !isFinite(x) ? '–' : x.toLocaleString('es-ES', { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: 'always' });
  const hm = h => { if (h == null || !isFinite(h)) return '–'; const m = Math.round(h * 60); return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}m`; };
  const esc = t => String(t ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let ultimo = null;

  function cifras(a) {
    const pie = /carrera|caminar|senderismo/i.test(a.tipo);
    const c = [['Distancia', num(a.km, a.km < 100 ? 1 : 0) + ' km'], ['En movimiento', hm(a.h)]];
    if (a.h_total && a.h && a.h_total - a.h > 1 / 60) c.push(['Tiempo total', hm(a.h_total)]);
    if (a.km > 0 && a.h > 0) {
      if (pie) { const s = Math.round(a.h * 3600 / a.km); c.push(['Ritmo medio', `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')} /km`]); }
      else c.push(['Velocidad media', num(a.km / a.h, 1) + ' km/h']);
    }
    if (a.desnivel != null) c.push(['Desnivel positivo', num(a.desnivel) + ' m']);
    if (a.alt_min != null) c.push(['Altitud', `${num(a.alt_min)}–${num(a.alt_max)} m`]);
    if (a.fc_media) c.push(['FC media / máx.', `${num(a.fc_media)} / ${num(a.fc_max)} ppm`]);
    if (a.potencia_media) c.push(['Potencia media', num(a.potencia_media) + ' W' + (a.np ? ` (NP ${num(a.np)} W)` : '')]);
    if (a.p20) c.push(['Mejor 20 min', num(a.p20) + ' W']);
    if (a.tss != null) c.push([(a.tss_real ? 'TSS' : 'TSS estimado') + (a.potencia_dudosa ? ' (poco fiable)' : ''), num(a.tss)]);
    if (a.calorias) c.push(['Calorías', num(a.calorias) + ' kcal']);
    if (a.bici_nombre) c.push(['Bici', esc(a.bici_nombre)]);
    const avisos = (a.sensores || []).length ? '<div class="aviso medio ra-sensores"><b>Sensores:</b> ' + a.sensores.map(esc).join('; ') +
      '.' + (a.tramos_sensores.length ? ' En el perfil, los tramos sin datos van sombreados.' : '') + '</div>' : '';
    return '<div class="ra-cifras">' + c.map(([t, v]) => `<div><span>${t}</span><b>${v}</b></div>`).join('') + '</div>' + avisos;
  }

  function el(padre, nombre, atr) {
    const e = document.createElementNS(NS, nombre);
    for (const k in atr) e.setAttribute(k, atr[k]);
    padre.appendChild(e);
    return e;
  }

  function perfil(caja, p) {
    const pts = p.filter(x => x[1] != null);
    if (pts.length < 2) return false;
    const W = Math.max(caja.clientWidth, 280), H = 190, mi = 46, md = 10, ma = 10, mb = 26;
    const dmax = pts[pts.length - 1][0] || 1;
    let amin = Math.min(...pts.map(x => x[1])), amax = Math.max(...pts.map(x => x[1]));
    if (amax - amin < 40) { const m = (amax + amin) / 2; amin = m - 20; amax = m + 20; }
    const pad = (amax - amin) * 0.08; amin -= pad; amax += pad;
    const x = d => mi + d / dmax * (W - mi - md), y = h => ma + (amax - h) / (amax - amin) * (H - ma - mb);
    const svg = el(caja, 'svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': `Perfil altimétrico: de ${num(Math.min(...pts.map(x => x[1])))} a ${num(Math.max(...pts.map(x => x[1])))} m en ${num(dmax, 1)} km` });
    // marcas del eje: 4 alturas redondas y unas pocas distancias
    const pasoA = [10, 20, 50, 100, 200, 250, 500, 1000].find(s => (amax - amin) / s <= 4) || 1000;
    for (let h = Math.ceil(amin / pasoA) * pasoA; h <= amax; h += pasoA) {
      el(svg, 'line', { class: 'rejilla', x1: mi, x2: W - md, y1: y(h), y2: y(h) });
      el(svg, 'text', { class: 'marca-eje', x: mi - 6, y: y(h) + 4, 'text-anchor': 'end' }).textContent = num(h);
    }
    const pasoD = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500].find(s => dmax / s <= 7) || 1000;
    for (let d = 0; d <= dmax; d += pasoD) el(svg, 'text', { class: 'marca-eje', x: x(d), y: H - 6, 'text-anchor': 'middle' }).textContent = num(d);
    el(svg, 'line', { class: 'eje', x1: mi, x2: W - md, y1: H - mb, y2: H - mb });
    // tramos sin datos de algún sensor (validador de sensores)
    for (const [k0, k1, s] of (tramosSensores || [])) {
      const r = el(svg, 'rect', { class: 'ra-sin-datos', x: x(k0), y: ma, width: Math.max(x(k1) - x(k0), 2), height: H - ma - mb });
      el(r, 'title', {}).textContent = `Sin datos (${s}): km ${num(k0, 1)}–${num(k1, 1)}`;
    }
    const linea = pts.map((q, i) => `${i ? 'L' : 'M'}${x(q[0]).toFixed(1)},${y(q[1]).toFixed(1)}`).join('');
    el(svg, 'path', { d: `${linea}L${x(pts[pts.length - 1][0]).toFixed(1)},${H - mb}L${x(pts[0][0]).toFixed(1)},${H - mb}Z`, class: 'ra-area' });
    el(svg, 'path', { d: linea, class: 'ra-linea' });
    // lectura al pasar el ratón o el dedo
    const cruz = el(svg, 'line', { class: 'cruz', y1: ma, y2: H - mb, visibility: 'hidden' });
    const punto = el(svg, 'circle', { r: 4, class: 'ra-punto', visibility: 'hidden' });
    const dato = document.createElement('p');
    dato.className = 'suave ra-dato';
    dato.textContent = 'Pasa el ratón por el perfil para ver la distancia y la altitud.';
    caja.appendChild(dato);
    const mover = e => {
      const r = svg.getBoundingClientRect(), d = ((e.clientX - r.left) * W / r.width - mi) / (W - mi - md) * dmax;
      if (d < 0 || d > dmax) return;
      let a = 0, b = pts.length - 1;
      while (b - a > 1) { const m = (a + b) >> 1; if (pts[m][0] < d) a = m; else b = m; }
      const q = Math.abs(pts[a][0] - d) < Math.abs(pts[b][0] - d) ? pts[a] : pts[b];
      cruz.setAttribute('x1', x(q[0])); cruz.setAttribute('x2', x(q[0])); cruz.setAttribute('visibility', 'visible');
      punto.setAttribute('cx', x(q[0])); punto.setAttribute('cy', y(q[1])); punto.setAttribute('visibility', 'visible');
      dato.textContent = `km ${num(q[0], 1)} · ${num(q[1])} m de altitud`;
      marcarMapa(q);
    };
    svg.addEventListener('pointermove', mover);
    svg.addEventListener('pointerdown', mover);
    return true;
  }

  let marcarMapa = () => {};
  function mapa(caja, t, p) {
    if (t.length < 2) return false;
    const lat0 = t.reduce((s, q) => s + q[0], 0) / t.length, k = Math.cos(lat0 * Math.PI / 180);
    const xs = t.map(q => q[1] * k), ys = t.map(q => q[0]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const L = 220, m = 10, esc = (L - 2 * m) / Math.max(x1 - x0, y1 - y0, 1e-6);
    const W = (x1 - x0) * esc + 2 * m, H = (y1 - y0) * esc + 2 * m;
    const px = q => [m + (q[1] * k - x0) * esc, m + (y1 - q[0]) * esc];
    const svg = el(caja, 'svg', { viewBox: `0 0 ${W.toFixed(1)} ${H.toFixed(1)}`, width: W.toFixed(0), height: H.toFixed(0), role: 'img', 'aria-label': 'Recorrido de la actividad, con el norte arriba' });
    el(svg, 'path', { class: 'ra-track', d: t.map((q, i) => (i ? 'L' : 'M') + px(q).map(v => v.toFixed(1)).join(',')).join('') });
    const [sx, sy] = px(t[0]), [fx, fy] = px(t[t.length - 1]);
    el(svg, 'circle', { cx: fx, cy: fy, r: 4, class: 'ra-fin' });
    el(svg, 'circle', { cx: sx, cy: sy, r: 4, class: 'ra-inicio' });
    const aqui = el(svg, 'circle', { r: 5, class: 'ra-punto', visibility: 'hidden' });
    // perfil y track salen de los mismos puntos (el track, solo los que tienen posición): se busca el equivalente
    marcarMapa = q => {
      const i = p.indexOf(q);
      const j = Math.min(t.length - 1, Math.round(i / Math.max(p.length - 1, 1) * (t.length - 1)));
      if (i < 0) return;
      const [ax, ay] = px(t[j]);
      aqui.setAttribute('cx', ax); aqui.setAttribute('cy', ay); aqui.setAttribute('visibility', 'visible');
    };
    return true;
  }

  let tramosSensores = [];
  function pintar(a) {
    tramosSensores = a.tramos_sensores || [];
    document.getElementById('ra-titulo').textContent = a.titulo || a.tipo;
    document.getElementById('ra-sub').textContent = `${a.fecha} · ${a.tipo}`;
    marcarMapa = () => {};
    cuerpo.innerHTML = cifras(a) + '<div class="ra-graficos"><div class="ra-perfil"></div><div class="ra-mapa"></div></div>' +
      (a.garmin ? `<p class="suave"><a href="${esc(a.garmin)}" target="_blank" rel="noopener">Abrir en Garmin Connect ↗</a></p>` : '');
    const hayMapa = mapa(cuerpo.querySelector('.ra-mapa'), a.track, a.perfil);
    if (!hayMapa) cuerpo.querySelector('.ra-mapa').remove();
    if (!perfil(cuerpo.querySelector('.ra-perfil'), a.perfil)) {
      cuerpo.querySelector('.ra-perfil').innerHTML = '<p class="suave">' + (a.perfil.length ? 'Esta actividad no tiene datos de altitud.'
        : 'No hay perfil: en este ordenador no está el recorrido de esta actividad (las anteriores a la descarga de Garmin solo traen el resumen).') + '</p>';
    }
  }

  // desde un aviso de Inicio: /historico?resumen=<id> abre el resumen de esa actividad
  const pedido = new URLSearchParams(location.search).get('resumen');
  if (pedido) {
    const b = [...document.querySelectorAll('.ver-resumen')].find(x => x.dataset.url.includes(`/actividad/${pedido}/`));
    if (b) setTimeout(() => b.click(), 0);
  }

  document.addEventListener('click', e => {
    const b = e.target.closest('.ver-resumen');
    if (!b) return;
    ultimo = b;
    document.getElementById('ra-titulo').textContent = 'Cargando…';
    document.getElementById('ra-sub').textContent = '';
    cuerpo.innerHTML = '';
    dlg.showModal();
    fetch(b.dataset.url).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(pintar).catch(() => {
      document.getElementById('ra-titulo').textContent = 'No se ha podido leer la actividad';
    });
  });
  dlg.addEventListener('close', () => { if (ultimo) ultimo.focus(); });
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });   // clic fuera de la ventana
})();
