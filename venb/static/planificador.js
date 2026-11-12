// Planificador: vista previa del plan recalculada al momento (mismas reglas que generador/datos.py) y generación.
(() => {
  const $ = id => document.getElementById(id);
  const num = s => parseFloat(String(s ?? '').trim().replace(',', '.'));
  const esc = t => String(t ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (x, d = 0) => isFinite(x) ? x.toLocaleString('es-ES', { minimumFractionDigits: d, maximumFractionDigits: d }) : '–';
  // Valores de las casillas: sin separador de miles, para poder leerlos de nuevo
  const ent = (x, d = 1) => isFinite(x) ? String(+(+x).toFixed(d)).replace('.', ',') : '';
  const z = n => String(n).padStart(2, '0');
  const fechaHora = d => d && isFinite(d) ? `${z(d.getDate())}/${z(d.getMonth() + 1)} ${z(d.getHours())}:${z(d.getMinutes())}` : '–';
  const dur = (min, signo) => {
    if (!isFinite(min)) return '–';
    const neg = min < 0; min = Math.round(Math.abs(min));
    return (neg ? '−' : signo ? '+' : '') + Math.floor(min / 60) + ':' + z(min % 60);
  };

  // Seguir un proceso en segundo plano (análisis o generación) hasta que termine
  function seguir(url, pre, fases, fin) {
    const paso = () => fetch(url, { cache: 'no-store' }).then(r => r.json()).then(e => {
      if (pre) pre.textContent = (e.registro || []).join('\n');
      if (fases.includes(e.fase)) setTimeout(paso, 2000); else fin(e);
    }).catch(() => setTimeout(paso, 5000));
    paso();
  }

  const prog = $('progreso');
  if (prog && prog.dataset.estado) {
    if (prog.querySelector('h2').textContent.startsWith('Analizando')) seguir(prog.dataset.estado, prog.querySelector('pre'), ['analizando'], () => location.reload());
    return;
  }
  const nodo = $('datos-plan');
  if (!nodo) return;
  const X = JSON.parse(nodo.textContent), A = X.a;
  const P = X.p && X.p.puntos && X.p.puntos.length === A.puntos.length ? X.p : null;  // parámetros de otra lista de puntos: no valen
  const N = A.puntos.length, TOTAL = A.total_km;
  const copia = o => JSON.parse(JSON.stringify(o));
  let V = copia(P ? P.velocidades : A.velocidades);
  V.factor = V.factor || 1;

  // ---------- velocidades (como datos.velocidad_base y datos.factor_fatiga)
  function base(p) {
    const t = V.tramos;
    for (let i = 0; i < t.length; i++) if (p < t[i][0] || (i === t.length - 1 && p <= t[i][0])) return t[i][1];
    return V.resto;
  }
  const fatiga = f => 1 - Math.min(Math.floor(f / (V.fatiga_cada || 1) + 1e-6) * V.fatiga_pct, V.fatiga_max_pct) / 100;
  // Media en movimiento que da la tabla sin escalar en esta ruta
  function mediaTabla() {
    let h = 0;
    A.puntos.forEach((p, i) => { if (i) h += p.km_tramo / (base(p.pendiente) * fatiga(p.km / TOTAL)); });
    return h > 0 ? TOTAL / h : NaN;
  }

  // ---------- reglas de Randonneurs Mondiaux (como datos.horas_brm; las tablas vienen de allí)
  const R = X.reglas;
  function horasTramos(km, tramos) {
    let h = 0, desde = 0;
    for (const [hasta, v] of tramos) { const t = Math.min(km, hasta) - desde; if (t <= 0) break; h += t / v; desde = hasta; }
    if (km > desde) h += (km - desde) / tramos[tramos.length - 1][1];
    return h;
  }
  function horasBrm(km, d, final) {
    const lim = R.limites[d], ap = horasTramos(Math.min(km, d), R.apertura);
    const ci = final || km >= d ? lim : km <= 60 ? km / 20 + 1 : Math.min(horasTramos(km, R.cierre), lim);
    return [Math.round(ap * 60) / 60, Math.round(ci * 60) / 60];
  }

  // ---------- campos generales
  const salida = FechaHora($('salida')), limite = $('limite'), vel = $('velocidad'), comun = $('parada-comun');
  const modalidad = $('modalidad'), distBrm = $('distancia-brm');
  modalidad.value = (P && P.modalidad) || A.modalidad || 'libre';
  distBrm.value = String((P && P.distancia_brm) || A.distancia_brm || 200);
  const brevet = () => modalidad.value === 'brevet' && R.limites[distBrm.value];
  function explicarModalidad(cambio) {
    const m = modalidad.value;
    $('campo-distancia').hidden = m !== 'brevet';
    $('etiqueta-limite').textContent = m === 'libre' ? 'Tiempo deseado (h)' : 'Tiempo límite (h)';
    $('titulo-cierre').textContent = m === 'libre' ? 'Objetivo' : 'Cierre';
    if (cambio || m === 'brevet') limite.value = m === 'brevet' ? ent(R.limites[distBrm.value], 2) : m === 'sr' ? ent(R.sr600, 2) : limite.value;
    limite.readOnly = m === 'brevet';   // en un brevet, el límite es el del reglamento
    $('explica-modalidad').textContent = m === 'brevet'
      ? 'Apertura y cierre de los controles según la tabla de Randonneurs Mondiaux' + (A.puntos.some(p => p.cierre_hoja) ? '; en los intermedios mandan las horas de la hoja del organizador.' : '.') + ' La meta cierra en el tiempo límite oficial.'
      : m === 'sr' ? 'Super Randonnée: sin horas de control; el cierre de cada punto reparte el tiempo límite (60 h en una SR 600) en proporción a la distancia.'
      : 'Recorrido libre: indica el tiempo que quieres emplear. La columna «Objetivo» reparte ese tiempo en proporción a la distancia.';
  }
  $('nombre').value = P ? P.nombre : A.nombre;
  $('subtitulo').value = P ? P.subtitulo : '';
  salida.value = (P ? P.salida : A.salida) || '';
  limite.value = ent((P ? P.limite_h : A.limite_h) || NaN, 2);
  const mostrarVel = () => { vel.value = ent(mediaTabla() * V.factor, 1); };
  mostrarVel();
  if (P) {
    document.querySelectorAll('input[name=salida]').forEach(c => { c.checked = P.salidas.includes(c.value); });
    if ($('club') && P.club) $('club').value = P.club;
    $('paleta').value = P.paleta; $('estilo-infografia').value = P.estilo_infografia; $('auto-lugares').checked = P.auto_lugares; $('track-pendiente').checked = !!P.track_pendiente;
    const paradasCtrl = P.puntos.filter((x, i) => A.puntos[i].control && i > 0 && i < N - 1).map(x => x.parada);
    if (paradasCtrl.length) comun.value = ent(paradasCtrl[0]);
  }

  // ---------- tabla de puntos
  const cuerpo = document.querySelector('#puntos tbody');
  // tipos de parada, con el icono que llevan en la infografía y la página interactiva (generador/estilo.ICONOS)
  const tipos = [['', '—'], ['salida', '🚩 Salida'], ['cafe', '☕ Café'], ['comida', '🍽 Comida'], ['dormir', '🛏 Dormir'], ['agua', '🚰 Agua'], ['cruce', '🔀 Cruce'], ['peligro', '⚠️ Peligro'], ['interes', '⭐ Punto de interés'], ['llegada', '🏁 Llegada'], ['otra', '✳️ Otra']];
  const defectoParada = i => (A.puntos[i].control && i > 0 && i < N - 1) ? (num(comun.value) || 0) : 0;
  // Cada fila: lo que se recalcula al momento (paradas, tipo, mapa) y lo que cambia los puntos (control, nombre, km,
  // quitar, añadir), que necesita «Actualizar». Las filas nuevas no tienen datos calculados hasta entonces.
  const fila = (p, i, q) => `<tr ${i === null ? 'class="nuevo"' : `data-i="${i}"`}>
      <td><input type="checkbox" class="mostrar" ${q.mostrar ? 'checked' : ''} aria-label="Mostrar ${esc(p.nombre || 'el punto')} en el mapa"></td>
      <td class="nowrap"><label class="casilla"><input type="checkbox" class="ed-control" data-id="${esc(p.control || '')}" ${p.control ? 'checked' : ''} aria-label="Es un control"> <b>${esc(p.control || '')}</b></label></td>
      <td><input class="ed-nombre" size="17" maxlength="80" value="${esc(p.nombre || '')}" aria-label="Nombre del punto" placeholder="Nombre"></td>
      <td class="num"><input class="ed-km" inputmode="decimal" size="4" value="${p.km_hoja === undefined ? '' : ent(p.km_hoja, 3)}" aria-label="km"
        ${i !== null && Math.abs(p.km - p.km_hoja) > 0.05 ? `title="${fmt(p.km, 1)} km en el GPX"` : ''}></td>
      <td class="num">${i === null ? '–' : fmt(p.alt)}</td><td class="num">${i === null ? '–' : fmt(p.asc_total) + ' m'}</td>
      <td class="num">${i ? fmt(p.pendiente * 100, 1) + ' %' : i === null ? '–' : ''}</td>
      <td class="num vel"></td>
      <td><input class="parada" inputmode="numeric" size="3" value="${ent(q.parada)}" aria-label="Parada (min)" ${i === 0 ? 'disabled' : ''}></td>
      <td><select class="tipo" aria-label="Tipo de parada">${tipos.map(([k, t]) => `<option value="${k}" ${q.tipo === k ? 'selected' : ''}>${t}</option>`).join('')}</select></td>
      <td class="num llegada"></td><td class="num cierre"></td><td class="num margen"></td>
      <td><button type="button" class="discreto ed-quitar" ${i === 0 ? 'disabled title="La salida no se puede quitar"' : ''}>Quitar</button></td></tr>`;
  cuerpo.innerHTML = A.puntos.map((p, i) => fila(p, i, P ? P.puntos[i] : { mostrar: !!p.control, parada: defectoParada(i), tipo: '' })).join('');
  const filas = [...cuerpo.rows];
  const paradas = () => filas.map((f, i) => i === 0 ? 0 : Math.max(0, num(f.querySelector('.parada').value) || 0));

  // ---------- cálculo (como datos.calcular)
  function calcular() {
    const t0 = new Date(salida.value), lim = num(limite.value), par = paradas();
    let ant = null;
    return A.puntos.map((p, i) => {
      const r = {};
      if (!ant) { r.llegada = r.salida = t0; r.vel = 0; }
      else {
        r.vel = base(p.pendiente) * fatiga(p.km / TOTAL) * V.factor;
        r.llegada = new Date(ant.salida.getTime() + p.km_tramo / r.vel * 3600e3);
        r.salida = new Date(r.llegada.getTime() + par[i] * 60e3);
      }
      const d = brevet(), rm = d ? horasBrm(p.km_hoja, +distBrm.value, i === N - 1) : null;
      // en un brevet, la meta cierra siempre en el tiempo límite oficial
      r.cierre = !isFinite(t0) && !p.cierre_hoja ? null : rm && i === N - 1 ? new Date(t0.getTime() + rm[1] * 3600e3)
        : p.cierre_hoja ? new Date(p.cierre_hoja) : !isFinite(t0) ? null : rm ? new Date(t0.getTime() + rm[1] * 3600e3)
        : isFinite(lim) ? new Date(t0.getTime() + p.km / TOTAL * lim * 3600e3) : null;
      r.margen = r.cierre && isFinite(r.salida) ? (r.cierre - r.salida) / 60e3 : NaN;   // al reanudar la marcha (llegada + parada)
      const ap = p.apertura_hoja ? new Date(p.apertura_hoja) : rm && p.control && i > 0 && isFinite(t0) ? new Date(t0.getTime() + rm[0] * 3600e3) : null;
      r.antes = ap && r.llegada < ap;
      ant = r;
      return r;
    });
  }

  function cifra(t, v, s = '') { return `<div class="cifra"><h3>${t}</h3><b>${v}</b><span>${s}</span></div>`; }
  function pintar() {
    const res = calcular(), fin = res[N - 1], t0 = res[0].llegada;
    res.forEach((r, i) => {
      const f = filas[i], ctrl = A.puntos[i].control;
      f.querySelector('.vel').textContent = i ? fmt(r.vel, 1) : '';
      f.querySelector('.llegada').textContent = fechaHora(r.llegada) + (r.antes ? ' ⚠' : '');
      f.querySelector('.llegada').title = r.antes ? 'Llegas antes de que abra el control' : '';
      f.querySelector('.cierre').textContent = ctrl || A.puntos[i].cierre_hoja ? fechaHora(r.cierre) : '';
      const m = f.querySelector('.margen');
      m.textContent = ctrl ? dur(r.margen, true) : '';
      m.style.color = ctrl && r.margen < 0 ? 'var(--rojo)' : '';
      m.style.fontWeight = ctrl && r.margen < 0 ? '700' : '';
    });
    const ctrls = res.filter((r, i) => A.puntos[i].control && i > 0);
    const peor = ctrls.reduce((a, r) => (!a || r.margen < a.margen ? r : a), null);
    const iPeor = res.indexOf(peor);
    const mov = res.reduce((s, r, i) => s + (i ? A.puntos[i].km_tramo / r.vel : 0), 0);
    const fuera = ctrls.filter(r => r.margen < 0).length, antes = res.filter(r => r.antes).length;
    $('resumen').innerHTML = cifra('Distancia', fmt(TOTAL, 1) + ' km', A.meta.distancia ? `oficial ${fmt(A.meta.distancia)} km` : '')
      + cifra('Desnivel', fmt(A.total_asc) + ' m', A.meta.desnivel ? `oficial ${fmt(A.meta.desnivel)} m` : 'modelo del terreno')
      + cifra('Tiempo total', dur((fin.llegada - t0) / 60e3), `${dur(mov * 60)} en movimiento`)
      + cifra('Llegada', fechaHora(fin.llegada), `media ${fmt(TOTAL / ((fin.llegada - t0) / 36e5), 1)} km/h con paradas`)
      + cifra('Margen en meta', dur(fin.margen, true), peor && iPeor >= 0 ? `mínimo ${dur(peor.margen, true)} en ${esc(A.puntos[iPeor].control)}` : '');
    $('aviso-generar').textContent = fuera ? `Atención: llegas fuera de cierre a ${fuera} control${fuera > 1 ? 'es' : ''}.` : antes ? `Llegas a ${antes} control${antes > 1 ? 'es' : ''} antes de su apertura.` : '';
    perfil(res);
  }

  // ---------- perfil con los controles
  function perfil() {
    const pf = A.perfil, W = 1000, H = 150, mi = 6, ab = 22;
    if (!pf || pf.length < 2) return;
    const amin = Math.min(...pf.map(p => p[1])), amax = Math.max(...pf.map(p => p[1]));
    const x = km => mi + km / TOTAL * (W - 2 * mi), y = a => 8 + (1 - (a - amin) / Math.max(amax - amin, 1)) * (H - ab - 8);
    const linea = pf.map(p => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
    let s = `<polygon points="${x(0)},${H - ab} ${linea} ${x(TOTAL)},${H - ab}" fill="var(--serie1)" opacity=".18"/>`
      + `<polyline points="${linea}" fill="none" stroke="var(--serie1)" stroke-width="1.5"/>`
      + `<line class="eje" x1="${mi}" x2="${W - mi}" y1="${H - ab}" y2="${H - ab}"/>`;
    A.puntos.forEach((p, i) => {
      if (!p.control) return;
      s += `<line x1="${x(p.km)}" x2="${x(p.km)}" y1="8" y2="${H - ab}" stroke="var(--suave)" stroke-dasharray="2 3"/>`
        + `<text class="marca-eje" x="${x(p.km)}" y="${H - 6}" text-anchor="${i === 0 ? 'start' : i === N - 1 ? 'end' : 'middle'}">${esc(p.control)}</text>`;
    });
    s += `<text class="marca-eje" x="${mi + 6}" y="20">${fmt(amax)} m</text><text class="marca-eje" x="${mi + 6}" y="${H - ab - 6}">${fmt(amin)} m</text>`;
    $('perfil').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Perfil: de ${fmt(amin)} a ${fmt(amax)} m">${s}</svg>`;
  }

  // ---------- eventos
  [salida, limite].forEach(c => c.addEventListener('input', pintar));
  [modalidad, distBrm].forEach(c => c.addEventListener('change', () => { explicarModalidad(true); pintar(); }));
  explicarModalidad(!P && !A.limite_h);
  cuerpo.addEventListener('input', pintar);
  vel.addEventListener('input', () => { const v = num(vel.value), m = mediaTabla(); if (v > 0 && m > 0) { V.factor = v / m; pintar(); } });
  vel.addEventListener('change', mostrarVel);
  $('rellenar').addEventListener('click', () => {
    const v = Math.max(0, num(comun.value) || 0);
    filas.forEach((f, i) => { if (A.puntos[i].control && i > 0 && i < N - 1) f.querySelector('.parada').value = ent(v); });
    pintar();
  });
  const rec = $('usar-reciente');
  if (rec && X.reciente) rec.addEventListener('click', () => { V.factor = X.reciente.kmh / mediaTabla(); mostrarVel(); pintar(); });

  // ---------- ventana de la tabla de velocidades
  const dlg = $('dialogo-vel'), tv = document.querySelector('#tabla-vel tbody');
  function dibujarTablaVel() {
    tv.innerHTML = V.tramos.map((t, i) => `<tr data-i="${i}"><td><input class="lim" inputmode="decimal" size="5" value="${ent(t[0] * 100, 2)}" aria-label="Límite de pendiente del tramo ${i + 1} (%)"></td>
      <td><input class="kmh" inputmode="decimal" size="5" value="${ent(t[1], 1)}" aria-label="Velocidad del tramo ${i + 1} (km/h)"></td>
      <td><button type="button" class="discreto quitar" aria-label="Quitar el tramo ${i + 1}" ${V.tramos.length < 2 ? 'disabled' : ''}>×</button></td></tr>`).join('');
    $('vel-resto').value = ent(V.resto, 1);
    $('fat-pct').value = ent(V.fatiga_pct); $('fat-cada').value = ent(V.fatiga_cada * 100); $('fat-max').value = ent(V.fatiga_max_pct);
    resultadoVel();
  }
  const resultadoVel = () => { $('vel-resultado').textContent = `Con esta tabla, sin escalar, la media en movimiento en esta ruta sería ${fmt(mediaTabla(), 1)} km/h. Con tu velocidad, cada valor se multiplica por ${fmt(V.factor, 3)}.`; };
  function leerTablaVel() {
    const tr = [...tv.rows].map(f => [num(f.querySelector('.lim').value) / 100, num(f.querySelector('.kmh').value)]).filter(t => isFinite(t[0]) && t[1] > 0);
    if (tr.length) V.tramos = tr.sort((a, b) => a[0] - b[0]);
    const r = num($('vel-resto').value); if (r > 0) V.resto = r;
    const fp = num($('fat-pct').value), fc = num($('fat-cada').value), fm = num($('fat-max').value);
    if (fp >= 0) V.fatiga_pct = fp; if (fc > 0) V.fatiga_cada = fc / 100; if (fm >= 0) V.fatiga_max_pct = fm;
    mostrarVel(); pintar(); resultadoVel();
  }
  dlg.addEventListener('input', leerTablaVel);
  tv.addEventListener('click', e => {
    const b = e.target.closest('.quitar');
    if (!b || V.tramos.length < 2) return;
    V.tramos.splice(+b.closest('tr').dataset.i, 1); dibujarTablaVel(); mostrarVel(); pintar();
  });
  $('vel-anadir').addEventListener('click', () => { const u = V.tramos[V.tramos.length - 1]; V.tramos.push([u[0] + 0.01, Math.max(1, u[1] - 2)]); dibujarTablaVel(); mostrarVel(); pintar(); });
  $('vel-defecto').addEventListener('click', () => { V = copia(A.velocidades); V.factor = 1; dibujarTablaVel(); mostrarVel(); pintar(); });
  $('ayuda-vel').addEventListener('click', () => { dibujarTablaVel(); dlg.showModal(); });
  $('vel-cerrar').addEventListener('click', () => { leerTablaVel(); dlg.close(); });
  dlg.addEventListener('close', () => tv.querySelectorAll('input').length && dibujarTablaVel());

  // ---------- generar
  const pg = $('progreso-generar'), boton = $('generar');
  function esperar() {
    pg.hidden = false; boton.disabled = true;
    seguir(X.urlEstado, pg.querySelector('pre'), ['generando'], () => location.reload());
  }
  // Todo lo que hay en la página (para generar o para guardarlo al editar los puntos)
  function recoger() {
    const salidas = [...document.querySelectorAll('input[name=salida]:checked')].map(c => c.value);
    return {
      nombre: $('nombre').value, subtitulo: $('subtitulo').value, salida: salida.value, limite_h: num(limite.value),
      modalidad: modalidad.value, distancia_brm: modalidad.value === 'brevet' ? +distBrm.value : null,
      puntos: filas.map((f, i) => ({ mostrar: f.querySelector('.mostrar').checked, parada: paradas()[i], tipo: f.querySelector('.tipo').value })),
      velocidades: { tramos: V.tramos.map(t => [t[0] * 100, t[1]]), resto: V.resto, fatiga_pct: V.fatiga_pct, fatiga_cada_pct: V.fatiga_cada * 100,
        fatiga_max_pct: V.fatiga_max_pct, factor: V.factor },
      salidas, paleta: $('paleta').value, estilo_infografia: $('estilo-infografia').value, club: $('club') ? $('club').value : '', auto_lugares: $('auto-lugares').checked, track_pendiente: $('track-pendiente').checked,
    };
  }
  boton.addEventListener('click', () => {
    if (pendiente) { $('aviso-generar').textContent = 'Antes de generar, pulsa «Actualizar» para aplicar los cambios en los puntos.'; return; }
    const datos = recoger();
    if (!salida.value || !(datos.limite_h > 0)) { $('aviso-generar').textContent = modalidad.value === 'libre' ? 'Indica la salida y el tiempo deseado.' : 'Indica la salida y el tiempo límite.'; return; }
    boton.disabled = true;
    fetch(X.urlGenerar, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) })
      .then(r => r.json().then(j => ({ ok: r.ok, j })))
      .then(({ ok, j }) => { if (ok) esperar(); else { boton.disabled = false; $('aviso-generar').textContent = j.error || 'No se ha podido generar.'; } })
      .catch(() => { boton.disabled = false; $('aviso-generar').textContent = 'No se ha podido contactar con VenB.'; });
  });

  // ---------- cambios en los puntos (necesitan «Actualizar»)
  const aviso = $('ed-aviso'), actualizar = $('ed-guardar');
  let pendiente = false;
  const marcarPendiente = () => {
    pendiente = true; actualizar.disabled = false;
    aviso.textContent = 'Has cambiado los puntos: pulsa «Actualizar» para recalcular.';
  };
  cuerpo.addEventListener('input', ev => { if (ev.target.matches('.ed-nombre, .ed-km, .ed-control')) marcarPendiente(); });
  cuerpo.addEventListener('change', ev => { if (ev.target.matches('.ed-control')) marcarPendiente(); });
  $('ed-anadir').addEventListener('click', () => {
    cuerpo.insertAdjacentHTML('beforeend', fila({}, null, { mostrar: true, parada: 0, tipo: '' }));
    cuerpo.lastElementChild.querySelector('.ed-nombre').focus();
    marcarPendiente();
  });
  cuerpo.addEventListener('click', ev => {
    const b = ev.target.closest('.ed-quitar');
    if (!b) return;
    const f = b.closest('tr');
    if (f.classList.contains('nuevo')) f.remove();
    else { const q = f.classList.toggle('quitado'); b.textContent = q ? 'Recuperar' : 'Quitar'; }
    marcarPendiente();
  });
  actualizar.addEventListener('click', () => {
    const par = paradas();
    const lista = [...cuerpo.rows].filter(f => !f.classList.contains('quitado')).map(f => {
      const i = f.dataset.i === undefined ? null : +f.dataset.i, o = i === null ? {} : A.puntos[i];
      const c = f.querySelector('.ed-control');
      return { control: c.checked ? (c.dataset.id || 'sí') : '', nombre: f.querySelector('.ed-nombre').value.trim(), km: f.querySelector('.ed-km').value.trim(),
        cierre_hoja: o.cierre_hoja || null, apertura_hoja: o.apertura_hoja || null, localidad: o.localidad ?? true,
        mostrar: f.querySelector('.mostrar').checked, parada: i === null ? Math.max(0, num(f.querySelector('.parada').value) || 0) : par[i],
        tipo: f.querySelector('.tipo').value };
    });
    if (lista.length < 2) { aviso.textContent = 'La ruta necesita al menos la salida y la meta.'; return; }
    if (lista.some(x => !x.nombre || !isFinite(num(x.km)))) { aviso.textContent = 'Cada punto necesita un nombre y un km.'; return; }
    actualizar.disabled = true; aviso.textContent = 'Actualizando…';
    fetch(X.urlPuntos, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...recoger(), lista }) })
      .then(r => r.json().then(j => ({ ok: r.ok, j })))
      .then(({ ok, j }) => { if (ok) location.reload(); else { actualizar.disabled = false; aviso.textContent = j.error || 'No se han podido actualizar los puntos.'; } })
      .catch(() => { actualizar.disabled = false; aviso.textContent = 'No se ha podido contactar con VenB.'; });
  });

  pintar();
  if (X.fase === 'generando') esperar();
})();
