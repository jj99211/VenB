/* VenB: gráficas SVG sin dependencias, para funcionar sin internet.
   VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const MES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const ALTO = 240, M = { a: 12, d: 44, b: 26, i: 44 };
  const svgEl = (padre, tipo, at) => {
    const e = document.createElementNS(NS, tipo);
    for (const k in at || {}) e.setAttribute(k, at[k]);
    if (padre) padre.appendChild(e);
    return e;
  };
  // Duraciones legibles: 9,25 h -> 9h15m; los totales de 100 h o más, solo en horas
  const hm = h => { if (h == null) return '–'; const m = Math.round(h * 60); return m >= 6000 ? num(m / 60) + 'h' : `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}m`; };
  const valor = (v, o) => o.ud === 'h' ? hm(v) : num(v, o.dec || 0) + (o.ud ? ' ' + o.ud : '');
  const num = (x, d = 0) => x == null ? '–' : x.toLocaleString('es-ES', { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: 'always' }).replace('-', '−');
  const ms = s => { const [a, m, d] = s.split('-').map(Number); return Date.UTC(a, m - 1, d); };
  const dd = n => String(n).padStart(2, '0');
  const fechaLarga = t => { const f = new Date(t); return `${dd(f.getUTCDate())}/${dd(f.getUTCMonth() + 1)}/${f.getUTCFullYear()}`; };
  const fechaMes = t => `${dd(new Date(t).getUTCDate())}/${dd(new Date(t).getUTCMonth() + 1)}`;

  /* ---------- Tooltip único ---------- */
  const tip = document.createElement('div');
  tip.className = 'tip';
  tip.hidden = true;
  document.body.appendChild(tip);
  function mostrar(titulo, filas, x, y) {
    tip.replaceChildren();
    const t = document.createElement('div');
    t.className = 'tip-t';
    t.textContent = titulo;
    tip.appendChild(t);
    for (const f of filas) {
      const r = document.createElement('div');
      r.className = 'tip-f';
      if (f.c) { const k = document.createElement('i'); k.style.background = f.c; r.appendChild(k); }
      const v = document.createElement('b');
      v.textContent = f.v;
      r.appendChild(v);
      if (f.n) { const n = document.createElement('span'); n.textContent = f.n; r.appendChild(n); }
      tip.appendChild(r);
    }
    tip.hidden = false;
    const a = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(8, x + 14 + a > innerWidth ? x - a - 14 : x + 14) + 'px';
    tip.style.top = Math.max(8, Math.min(y - h / 2, innerHeight - h - 8)) + 'px';
  }
  const ocultar = () => { tip.hidden = true; };

  /* ---------- Piezas comunes ---------- */
  function escala(min, max, marcas = 5, ceroFijo = false) {
    if (ceroFijo) min = Math.min(0, min);
    if (min === max) { min -= 1; max += 1; }
    const bruto = (max - min) / marcas, pot = 10 ** Math.floor(Math.log10(bruto));
    const paso = [1, 2, 2.5, 5, 10].map(p => p * pot).find(p => p >= bruto);
    const ini = Math.floor(min / paso) * paso, fin = Math.ceil(max / paso) * paso, t = [];
    for (let v = ini; v <= fin + paso / 2; v += paso) t.push(Math.round(v * 1e6) / 1e6);
    return { min: ini, max: fin, marcas: t };
  }
  function leyenda(cont, series, tipo) {
    if (series.length < 2) return;
    const l = document.createElement('div');
    l.className = 'leyenda';
    for (const s of series) {
      const e = document.createElement('span'), k = document.createElement('i');
      k.className = tipo;
      k.style.background = s.c;
      e.append(k, document.createTextNode(s.n));
      l.appendChild(e);
    }
    cont.appendChild(l);
  }
  function vacio(cont) {
    const p = document.createElement('p');
    p.className = 'suave sin-datos';
    p.textContent = 'Sin datos en este periodo.';
    cont.replaceChildren(p);
  }
  function rejillaY(svg, e, W, y, dec = 0) {
    for (const v of e.marcas) {
      const py = y(v);
      svgEl(svg, 'line', { x1: M.i, x2: W - M.d, y1: py, y2: py, class: v === 0 ? 'eje' : 'rejilla' });
      svgEl(svg, 'text', { x: M.i - 6, y: py + 4, 'text-anchor': 'end', class: 'marca-eje' }).textContent = num(v, dec);
    }
  }
  function marcasFecha(t0, t1, plotW, soloMes) {
    const pasos = soloMes ? [1, 2, 3] : [1, 2, 3, 6, 12, 24, 36, 60];
    const n = (t1 - t0) / (30.44 * 864e5);
    const paso = pasos.find(p => n / p * 52 <= plotW) || pasos[pasos.length - 1];
    const f = new Date(t0), r = [];
    let a = f.getUTCFullYear(), m = f.getUTCMonth();
    if (Date.UTC(a, m, 1) < t0) m += 1;
    if (paso >= 12) { a += m > 0 ? 1 : 0; m = 0; } else m = Math.ceil(m / paso) * paso;
    for (let t = Date.UTC(a, m, 1); t <= t1; m += paso, t = Date.UTC(a, m, 1)) {
      const d = new Date(t);
      const et = soloMes ? MES[d.getUTCMonth()] : paso >= 12 ? String(d.getUTCFullYear())
        : d.getUTCMonth() === 0 || !r.length ? `${MES[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}` : MES[d.getUTCMonth()];
      r.push({ t, et });
    }
    return r;
  }
  /* Teclado y puntero comparten el mismo índice: se busca la posición, no la línea. */
  function navegar(svg, n, indice, marcar) {
    let act = -1;
    const pon = (i, x, y) => { act = i; marcar(i, x, y); };
    const fin = () => { act = -1; marcar(-1); ocultar(); };
    svg.addEventListener('pointermove', e => pon(indice(e), e.clientX, e.clientY));
    svg.addEventListener('pointerleave', fin);
    svg.addEventListener('blur', fin);
    svg.addEventListener('keydown', e => {
      const d = { ArrowLeft: -1, ArrowRight: 1, Home: -n, End: n }[e.key];
      if (!d) return;
      e.preventDefault();
      const i = Math.max(0, Math.min(n - 1, (act < 0 ? n : act) + d));
      const c = svg.getBoundingClientRect();
      pon(i, c.left + c.width / 2, c.top + 40);
    });
  }

  /* ---------- Líneas ---------- */
  function lineas(cont, o) {
    const validos = o.series.some(s => s.v.some(v => v != null));
    if (!o.x.length || !validos) return vacio(cont);
    cont.replaceChildren();
    leyenda(cont, o.series.filter(s => !s.sinLeyenda), 'k-linea');
    const W = Math.max(cont.clientWidth, 280), H = ALTO, plotW = W - M.i - M.d, plotH = H - M.a - M.b;
    const t0 = o.x[0], t1 = o.x[o.x.length - 1], todos = o.series.flatMap(s => s.v).filter(v => v != null);
    if (o.ref) todos.push(o.ref.y);
    const e = escala(Math.min(...todos), Math.max(...todos), 5, o.cero);
    const px = t => t1 === t0 ? M.i + plotW / 2 : M.i + (t - t0) / (t1 - t0) * plotW;
    const py = v => M.a + (e.max - v) / (e.max - e.min) * plotH;
    const svg = svgEl(cont, 'svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', tabindex: 0, 'aria-label': o.nombre + '. Usa las flechas para recorrer los valores; la tabla está en Ver datos.' });
    rejillaY(svg, e, W, py, o.decEje || 0);
    for (const m of marcasFecha(t0, t1, plotW, o.soloMes)) {
      svgEl(svg, 'text', { x: px(m.t), y: H - 8, 'text-anchor': 'middle', class: 'marca-eje' }).textContent = m.et;
    }
    if (o.ref) {
      svgEl(svg, 'line', { x1: M.i, x2: W - M.d, y1: py(o.ref.y), y2: py(o.ref.y), class: 'eje' });
      svgEl(svg, 'text', { x: M.i + 4, y: py(o.ref.y) - 5, class: 'marca-eje' }).textContent = o.ref.t;
    }
    const finales = [];
    for (const s of o.series) {
      let d = '', pluma = false, ultimo = -1;
      s.v.forEach((v, i) => {
        if (v == null) { pluma = false; return; }
        d += `${pluma ? 'L' : 'M'}${px(o.x[i]).toFixed(1)} ${py(v).toFixed(1)}`;
        pluma = true; ultimo = i;
      });
      svgEl(svg, 'path', { d, fill: 'none', stroke: s.c, 'stroke-width': s.ancho || 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' });
      if (o.puntos && o.x.length <= 60) s.v.forEach((v, i) => { if (v != null) svgEl(svg, 'circle', { cx: px(o.x[i]), cy: py(v), r: 2.5, fill: s.c }); });
      if (ultimo >= 0 && !s.sinEtiqueta) {
        svgEl(svg, 'circle', { cx: px(o.x[ultimo]), cy: py(s.v[ultimo]), r: 4, fill: s.c, class: 'anillo' });
        finales.push({ x: px(o.x[ultimo]), y: py(s.v[ultimo]), v: s.v[ultimo] });
      }
    }
    /* Si los finales chocan no se apilan: quedan la leyenda y el tooltip. */
    if (!finales.some((a, i) => finales.some((b, j) => i < j && Math.abs(a.y - b.y) < 14))) {
      for (const f of finales) svgEl(svg, 'text', { x: f.x + 7, y: f.y + 4, class: 'valor-fin' }).textContent = o.ud === 'h' ? hm(f.v) : num(f.v, o.dec || 0);
    }
    const cruz = svgEl(svg, 'line', { y1: M.a, y2: H - M.b, class: 'cruz', visibility: 'hidden' });
    const puntos = o.series.map(s => svgEl(svg, 'circle', { r: 4, fill: s.c, class: 'anillo', visibility: 'hidden' }));
    const fx = o.soloMes ? fechaMes : fechaLarga;
    navegar(svg, o.x.length, ev => {
      const c = svg.getBoundingClientRect(), t = t0 + ((ev.clientX - c.left) - M.i) / (plotW || 1) * (t1 - t0);
      let a = 0, b = o.x.length - 1;
      while (b - a > 1) { const m = (a + b) >> 1; if (o.x[m] < t) a = m; else b = m; }
      return t - o.x[a] < o.x[b] - t ? a : b;
    }, (i, x, y) => {
      if (i < 0) { cruz.setAttribute('visibility', 'hidden'); puntos.forEach(p => p.setAttribute('visibility', 'hidden')); return; }
      const cx = px(o.x[i]);
      cruz.setAttribute('x1', cx); cruz.setAttribute('x2', cx); cruz.setAttribute('visibility', 'visible');
      o.series.forEach((s, k) => {
        const v = s.v[i];
        puntos[k].setAttribute('visibility', v == null ? 'hidden' : 'visible');
        if (v != null) { puntos[k].setAttribute('cx', cx); puntos[k].setAttribute('cy', py(v)); }
      });
      mostrar(fx(o.x[i]), o.series.filter(s => s.v[i] != null).map(s => ({ c: s.c, v: valor(s.v[i], o), n: s.n })), x, y);
    });
  }

  /* ---------- Columnas ---------- */
  function columnas(cont, o) {
    if (!o.v.length) return vacio(cont);
    cont.replaceChildren();
    const W = Math.max(cont.clientWidth, 280), H = ALTO, der = 12, plotW = W - M.i - der, plotH = H - M.a - M.b - 6;
    const e = escala(0, Math.max(...o.v), 5, true);
    const py = v => M.a + 6 + (e.max - v) / (e.max - e.min) * plotH;
    const banda = plotW / o.v.length, gap = banda > 5 ? 2 : banda > 2.5 ? 1 : 0, ancho = Math.min(24, banda - gap);
    const svg = svgEl(cont, 'svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', tabindex: 0, 'aria-label': o.nombre + '. Usa las flechas para recorrer los valores; la tabla está en Ver datos.' });
    for (const v of e.marcas) {
      svgEl(svg, 'line', { x1: M.i, x2: W - der, y1: py(v), y2: py(v), class: v === 0 ? 'eje' : 'rejilla' });
      svgEl(svg, 'text', { x: M.i - 6, y: py(v) + 4, 'text-anchor': 'end', class: 'marca-eje' }).textContent = num(v);
    }
    const cx = i => M.i + banda * (i + 0.5);
    const barras = o.v.map((v, i) => {
      const y = py(v), alto = py(0) - y, r = Math.min(4, ancho / 2, alto), x = cx(i) - ancho / 2;
      const d = `M${x} ${py(0)}V${y + r}Q${x} ${y} ${x + r} ${y}H${x + ancho - r}Q${x + ancho} ${y} ${x + ancho} ${y + r}V${py(0)}Z`;
      return svgEl(svg, 'path', { d, fill: o.c, class: 'barra' });
    });
    const salto = Math.max(1, Math.ceil(o.corta.length * (o.anchoEt || 48) / plotW));
    o.corta.forEach((t, i) => {
      if ((o.corta.length - 1 - i) % salto === 0) svgEl(svg, 'text', { x: cx(i), y: H - 8, 'text-anchor': 'middle', class: 'marca-eje' }).textContent = t;
    });
    const mx = o.v.indexOf(Math.max(...o.v));
    const et = o.todas ? o.v.map((_, i) => i) : [mx];
    if (banda >= 30 || !o.todas) for (const i of et) {
      if (o.v[i] > 0) svgEl(svg, 'text', { x: Math.min(cx(i), W - 24), y: py(o.v[i]) - 5, 'text-anchor': 'middle', class: 'valor-fin' }).textContent = o.ud === 'h' ? hm(o.v[i]) : num(o.v[i], o.dec || 0);
    }
    navegar(svg, o.v.length, ev => {
      const c = svg.getBoundingClientRect();
      return Math.max(0, Math.min(o.v.length - 1, Math.floor((ev.clientX - c.left - M.i) / banda)));
    }, (i, x, y) => {
      barras.forEach((b, k) => b.classList.toggle('activa', k === i));
      if (i >= 0) mostrar(o.larga[i], [{ v: valor(o.v[i], o), n: o.nombreValor }].concat(o.extra ? o.extra(i) : []), x, y);
    });
  }

  /* ---------- Columnas apiladas ---------- */
  function apiladas(cont, o) {
    const totales = o.cats.map((_, i) => o.series.reduce((a, s) => a + s.v[i], 0));
    if (!o.cats.length || !Math.max(...totales)) return vacio(cont);
    cont.replaceChildren();
    leyenda(cont, o.series, 'k-rect');
    const W = Math.max(cont.clientWidth, 280), H = ALTO, der = 12, plotW = W - M.i - der, plotH = H - M.a - M.b - 6;
    const e = escala(0, Math.max(...totales), 5, true);
    const py = v => M.a + 6 + (e.max - v) / (e.max - e.min) * plotH;
    const banda = plotW / o.cats.length, ancho = Math.min(24, banda - 2);
    const svg = svgEl(cont, 'svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', tabindex: 0, 'aria-label': o.nombre + '. Usa las flechas para recorrer los valores; la tabla está en Ver datos.' });
    for (const v of e.marcas) {
      svgEl(svg, 'line', { x1: M.i, x2: W - der, y1: py(v), y2: py(v), class: v === 0 ? 'eje' : 'rejilla' });
      svgEl(svg, 'text', { x: M.i - 6, y: py(v) + 4, 'text-anchor': 'end', class: 'marca-eje' }).textContent = num(v);
    }
    const cx = i => M.i + banda * (i + 0.5);
    const grupos = o.cats.map((c, i) => {
      const g = svgEl(svg, 'g', { class: 'barra' });
      let acum = 0;
      const vis = o.series.map(s => s.v[i]);
      const ult = vis.map(v => v > 0).lastIndexOf(true);
      vis.forEach((v, k) => {
        if (v <= 0) return;
        const y0 = py(acum), y1 = py(acum + v), x = cx(i) - ancho / 2, alto = Math.max(y0 - y1 - 2, 1), y = y0 - 2 - alto;
        const r = k === ult ? Math.min(4, alto) : 0;
        svgEl(g, 'path', { d: `M${x} ${y + alto}V${y + r}Q${x} ${y} ${x + r} ${y}H${x + ancho - r}Q${x + ancho} ${y} ${x + ancho} ${y + r}V${y + alto}Z`, fill: o.series[k].c });
        acum += v;
      });
      return g;
    });
    const salto = Math.max(1, Math.ceil(o.cats.length * 46 / plotW));
    o.cats.forEach((t, i) => { if ((o.cats.length - 1 - i) % salto === 0) svgEl(svg, 'text', { x: cx(i), y: H - 8, 'text-anchor': 'middle', class: 'marca-eje' }).textContent = t; });
    navegar(svg, o.cats.length, ev => {
      const c = svg.getBoundingClientRect();
      return Math.max(0, Math.min(o.cats.length - 1, Math.floor((ev.clientX - c.left - M.i) / banda)));
    }, (i, x, y) => {
      grupos.forEach((g, k) => g.classList.toggle('activa', k === i));
      if (i >= 0) mostrar(o.cats[i], [{ v: num(totales[i]) + ' km', n: 'en total' }].concat(o.series.filter(s => s.v[i] > 0).map(s => ({ c: s.c, v: num(s.v[i]) + ' km', n: s.n }))), x, y);
    });
    tabla(cont, [o.etCat || 'Temporada'].concat(o.series.map(s => s.n), 'Total'), o.cats.map((c, i) => [c].concat(o.series.map(s => num(s.v[i])), num(totales[i]))).reverse());
  }

  function pintarBicis(D) {
    const c = ['--serie1', '--serie2', '--serie3', '--serie4', '--serie5', '--serie6', '--serie7', '--serie8'].map(css);
    apiladas($('g-temporadas'), { nombre: 'Kilómetros por temporada y bici', cats: D.cats, series: D.series.map((s, i) => ({ ...s, c: c[i] })) });
    const caja = $('g-juegos');
    caja.replaceChildren();
    D.por_juegos.forEach(b => {
      const p = document.createElement('section'), h = document.createElement('h2'), g = document.createElement('div');
      const det = document.createElement('details'), res = document.createElement('summary'), tab = document.createElement('div');
      p.className = 'panel';
      h.textContent = `${b.nombre}: kilómetros por juego de ruedas`;
      g.className = 'graf';
      det.className = 'ver';
      res.textContent = 'Ver datos';
      tab.className = 'tabla';
      det.append(res, tab);
      p.append(h, g, det);
      caja.appendChild(p);
      apiladas(g, { nombre: h.textContent, cats: b.cats, series: b.series.map((s, i) => ({ ...s, c: c[i] })) });
    });
  }

  /* ---------- Mapa de calor año × mes ---------- */
  function mapa(cont, d) {
    cont.replaceChildren();
    const envol = document.createElement('div');
    envol.className = 'tabla';
    const t = document.createElement('table');
    t.className = 'mapa';
    const cab = t.insertRow();
    cab.appendChild(document.createElement('th'));
    for (const m of MES) { const c = document.createElement('th'); c.textContent = m; cab.appendChild(c); }
    const max = Math.max(...d.km.flat());
    d.anios.forEach((a, f) => {
      const r = t.insertRow(), h = document.createElement('th');
      h.textContent = a;
      r.appendChild(h);
      d.km[f].forEach((km, m) => {
        const c = r.insertCell();
        if (km > 0) c.style.background = `color-mix(in oklab, var(--serie1) ${Math.round(12 + 88 * Math.sqrt(km / max))}%, var(--panel))`;
        c.tabIndex = -1;
        const txt = [{ v: num(km) + ' km', n: '' }];
        c.addEventListener('pointermove', e => mostrar(`${MES[m]} ${a}`, txt, e.clientX, e.clientY));
        c.addEventListener('pointerleave', ocultar);
      });
    });
    envol.appendChild(t);
    const esc = document.createElement('p');
    esc.className = 'suave escala';
    esc.append('0 km ');
    const g = document.createElement('i');
    esc.appendChild(g);
    esc.append(` ${num(max)} km al mes`);
    cont.append(envol, esc);
  }

  /* ---------- Tabla equivalente ---------- */
  function tabla(cont, cabs, filas) {
    const det = cont.parentElement.querySelector('details.ver');
    if (!det) return;
    const pinta = () => {
      const caja = det.querySelector('div');
      const t = document.createElement('table');
      const c = t.insertRow();
      cabs.forEach((h, i) => { const th = document.createElement('th'); th.textContent = h; if (i) th.className = 'num'; c.appendChild(th); });
      for (const f of filas) {
        const r = t.insertRow();
        f.forEach((v, i) => { const td = r.insertCell(); td.textContent = v; if (i) td.className = 'num'; });
      }
      caja.replaceChildren(t);
    };
    det.ontoggle = () => { if (det.open) pinta(); };
    if (det.open) pinta();
  }

  /* ---------- Colores y agrupación ---------- */
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function agrupar(sem) {
    /* Más de 100 columnas no se leen: se agrupa por mes y, si no basta, por año. */
    const clave = [f => f, f => f.slice(0, 7), f => f.slice(0, 4)];
    let nivel = 0, cubos;
    for (; nivel < 3; nivel++) {
      cubos = new Map();
      sem.forEach(s => {
        const k = clave[nivel](s.f), c = cubos.get(k) || { f: k, h: 0, km: 0 };
        c.h += s.h; c.km += s.km; cubos.set(k, c);
      });
      if (cubos.size <= 100) break;
    }
    nivel = Math.min(nivel, 2);
    const l = [...cubos.values()];
    const larga = k => nivel === 0 ? 'Semana del ' + fechaLarga(ms(k)) : nivel === 1 ? `${MES[+k.slice(5) - 1]} ${k.slice(0, 4)}` : k;
    const corta = k => nivel === 0 ? fechaMes(ms(k)) : nivel === 1 ? `${MES[+k.slice(5) - 1]} ${k.slice(2, 4)}` : k;
    return { nivel: ['semana', 'mes', 'año'][nivel], cubos: l, larga: l.map(c => larga(c.f)), corta: l.map(c => corta(c.f)) };
  }
  const recorta = (fechas, listas, desde) => {
    const i = fechas.findIndex(f => ms(f) >= desde);
    const n = i < 0 ? fechas.length : i;
    return { x: fechas.slice(n).map(ms), f: fechas.slice(n), v: listas.map(l => l.slice(n)) };
  };

  /* ---------- Vistas ---------- */
  const $ = id => document.getElementById(id);
  let pintores = [];
  const registrar = (el, fn) => { if (el) pintores.push(fn); };

  function pintarSerie(D, desde) {
    const azul = css('--serie1'), naranja = css('--serie2');
    const r = recorta(D.pmc.f, [D.pmc.CTL, D.pmc.ATL, D.pmc.TSB], desde);
    if ($('g-carga')) {
      lineas($('g-carga'), { nombre: 'Forma y fatiga', x: r.x, cero: true, series: [{ n: 'Forma (CTL)', v: r.v[0], c: azul }, { n: 'Fatiga (ATL)', v: r.v[1], c: naranja }] });
      tabla($('g-carga'), ['Fecha', 'CTL', 'ATL'], r.f.map((f, i) => [fechaLarga(ms(f)), num(r.v[0][i]), num(r.v[1][i])]).reverse());
    }
    if ($('g-tsb')) {
      lineas($('g-tsb'), { nombre: 'Frescura', x: r.x, cero: true, series: [{ n: 'Frescura (TSB)', v: r.v[2], c: azul }] });
      tabla($('g-tsb'), ['Fecha', 'TSB'], r.f.map((f, i) => [fechaLarga(ms(f)), num(r.v[2][i])]).reverse());
    }
    if ($('g-horas')) {
      const s = D.semanas.filter(c => ms(c.f) >= desde), g = agrupar(s);
      $('t-horas').textContent = `Horas de bici por ${g.nivel}`;
      columnas($('g-horas'), { nombre: 'Horas de bici', v: g.cubos.map(c => c.h), larga: g.larga, corta: g.corta, c: azul, dec: 1, ud: 'h', nombreValor: 'de bici', anchoEt: 58, extra: i => [{ v: num(g.cubos[i].km) + ' km', n: '' }] });
      tabla($('g-horas'), [g.nivel[0].toUpperCase() + g.nivel.slice(1), 'Horas', 'km'], g.cubos.map((c, i) => [g.larga[i], hm(c.h), num(c.km)]).reverse());
    }
    if ($('g-potencia')) {
      const p = recorta(D.potencia.f, [D.potencia.w], desde);
      lineas($('g-potencia'), { nombre: 'Mejor potencia de 20 minutos por mes', x: p.x, series: [{ n: 'Mejor 20 min', v: p.v[0], c: azul }], ud: 'W', puntos: true });
      tabla($('g-potencia'), ['Mes', 'Vatios'], p.f.map((f, i) => [`${MES[+f.slice(5, 7) - 1]} ${f.slice(0, 4)}`, num(p.v[0][i])]).reverse());
    }
    const s = recorta(D.salud.f, [D.salud.sueno, D.salud.vfc, D.salud.fc], desde);
    [['g-sueno', 0, 'Sueño', 'h', 1, { y: D.sueno_ref, t: `Referencia: ${num(D.sueno_ref, D.sueno_ref % 1 ? 1 : 0)} h` }], ['g-vfc', 1, 'VFC', 'ms', 0], ['g-fc', 2, 'FC en reposo', 'ppm', 0]].forEach(([id, k, n, ud, dec, ref]) => {
      if (!$(id)) return;
      lineas($(id), { nombre: n + ', media de 7 días', x: s.x, series: [{ n, v: s.v[k], c: azul }], ud, dec, ref, decEje: 0 });
      tabla($(id), ['Fecha', ud === 'h' ? n : `${n} (${ud})`], s.f.map((f, i) => [fechaLarga(ms(f)), ud === 'h' ? hm(s.v[k][i]) : num(s.v[k][i], dec)]).reverse());
    });
    if ($('g-peso')) {
      const p = recorta(D.peso.f, [D.peso.kg], desde);
      lineas($('g-peso'), { nombre: 'Peso', x: p.x, series: [{ n: 'Peso', v: p.v[0], c: azul }], ud: 'kg', dec: 1, puntos: true });
      tabla($('g-peso'), ['Fecha', 'kg'], p.f.map((f, i) => [fechaLarga(ms(f)), num(p.v[0][i], 1)]).reverse());
    }
  }

  function pintarHistorico(D) {
    const azul = css('--serie1'), naranja = css('--serie2'), gris = css('--gris-serie');
    if ($('g-anual')) {
      const a = D.anual;
      columnas($('g-anual'), { nombre: 'Kilómetros de bici por año', v: a.km, larga: a.a.map(String), corta: a.a.map(String), c: azul, ud: 'km', nombreValor: 'de bici', anchoEt: 40, extra: i => [{ v: num(a.h[i]) + ' h', n: '' }, { v: num(a.n[i]), n: 'salidas' }, { v: num(a.desnivel[i]) + ' m', n: 'de desnivel' }] });
      tabla($('g-anual'), ['Año', 'km', 'Horas', 'Salidas', 'Desnivel (m)'], a.a.map((y, i) => [String(y), num(a.km[i]), hm(a.h[i]), num(a.n[i]), num(a.desnivel[i])]).reverse());
    }
    if ($('g-acum')) {
      const c = D.acumulado, n = c.series.length;
      const series = c.series.map((s, i) => i === n - 1 ? { n: String(s.a), v: s.km, c: azul } : i === n - 2 ? { n: String(s.a), v: s.km, c: naranja } : { n: String(s.a), v: s.km, c: gris, ancho: 1, sinEtiqueta: true, sinLeyenda: true });
      lineas($('g-acum'), { nombre: 'Kilómetros acumulados por año', x: c.f.map(ms), series, ud: 'km', soloMes: true, cero: true });
      const idx = c.f.map((_, i) => i).filter(i => c.f[i].endsWith('-01') || i === c.f.length - 1);
      tabla($('g-acum'), ['Fecha'].concat(c.series.map(s => String(s.a))), idx.map(i => [fechaMes(ms(c.f[i]))].concat(c.series.map(s => num(s.km[i])))));
    }
    if ($('g-mapa')) mapa($('g-mapa'), D.mapa);
    if ($('g-dist')) {
      const d = D.distancias;
      columnas($('g-dist'), { nombre: 'Salidas de bici según su distancia', v: d.n, larga: d.et.map(e => e + ' km'), corta: d.et, c: azul, nombreValor: 'salidas', todas: true, anchoEt: 52 });
      tabla($('g-dist'), ['Distancia (km)', 'Salidas'], d.et.map((e, i) => [e, num(d.n[i])]));
    }
  }

  function spark(svg) {
    const v = JSON.parse(svg.dataset.v).filter(x => x != null);
    if (v.length < 2) return;
    const W = 110, H = 26, a = Math.min(...v), b = Math.max(...v), r = b - a || 1;
    const px = i => 2 + i / (v.length - 1) * (W - 8), py = x => H - 5 - (x - a) / r * (H - 10);
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svgEl(svg, 'path', { d: v.map((x, i) => `${i ? 'L' : 'M'}${px(i).toFixed(1)} ${py(x).toFixed(1)}`).join(''), fill: 'none', class: 'spark-l' });
    svgEl(svg, 'circle', { cx: px(v.length - 1), cy: py(v[v.length - 1]), r: 3, class: 'spark-p' });
  }

  function iniciar() {
    document.querySelectorAll('svg.spark').forEach(spark);
    if ($('g-brevets')) {
      fetch('/datos/brevets.json').then(r => r.json()).then(D => {
        const pinta = () => {
          const c = ['--serie1', '--serie2', '--serie3', '--serie4', '--serie5'].map(css);
          apiladas($('g-brevets'), { nombre: 'Kilómetros de brevet por año y distancia', etCat: 'Año', cats: D.anios.map(String), series: D.series.map((s, i) => ({ ...s, c: c[i] })) });
        };
        pinta();
        document.querySelectorAll('details.plegable').forEach(d => d.addEventListener('toggle', () => { if (d.open) pinta(); }));
        let ancho = innerWidth;
        addEventListener('resize', () => { if (innerWidth !== ancho) { ancho = innerWidth; pinta(); } });
        matchMedia('(prefers-color-scheme: dark)').addEventListener('change', pinta);
      });
      return;
    }
    if ($('g-temporadas')) {
      fetch('/datos/bicis.json').then(r => r.json()).then(D => {
        pintarBicis(D);
        let ancho = innerWidth;
        addEventListener('resize', () => { if (innerWidth !== ancho) { ancho = innerWidth; pintarBicis(D); } });
        matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => pintarBicis(D));
      });
      return;
    }
    if (!document.querySelector('[data-grafica]')) return;
    fetch('/datos/graficas.json').then(r => { if (!r.ok) throw new Error(); return r.json(); }).then(D => {
      const hoy = ms(D.hoy);
      const botones = [...document.querySelectorAll('.rango button')];
      let meses = +(document.body.dataset.rango || 12);
      const todo = () => {
        pintarSerie(D, meses ? hoy - meses * 30.44 * 864e5 : 0);
        pintarHistorico(D);
      };
      botones.forEach(b => b.addEventListener('click', () => {
        meses = +b.dataset.meses;
        botones.forEach(x => x.setAttribute('aria-pressed', x === b));
        try { localStorage.setItem('venb-rango', meses); } catch (e) { /* solo es una comodidad */ }
        pintarSerie(D, meses ? hoy - meses * 30.44 * 864e5 : 0);
      }));
      if (botones.length) {
        try {
          const g = localStorage.getItem('venb-rango');
          if (g !== null && botones.some(b => b.dataset.meses === g)) meses = +g;
        } catch (e) { /* idem */ }
        botones.forEach(x => x.setAttribute('aria-pressed', +x.dataset.meses === meses));
      }
      todo();
      // Las gráficas de una sección plegada no tienen ancho: se dibujan de nuevo al desplegarla
      document.querySelectorAll('details.plegable').forEach(d => d.addEventListener('toggle', () => { if (d.open) todo(); }));
      let ancho = innerWidth, espera;
      addEventListener('resize', () => {
        if (innerWidth === ancho) return;
        ancho = innerWidth;
        clearTimeout(espera);
        espera = setTimeout(todo, 150);
      });
      matchMedia('(prefers-color-scheme: dark)').addEventListener('change', todo);
    }).catch(() => {
      document.querySelectorAll('[data-grafica]').forEach(e => {
        e.textContent = 'Aún no hay datos para esta gráfica.';
        e.className = 'suave';
      });
    });
  }
  iniciar();
})();
