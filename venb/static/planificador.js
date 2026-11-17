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
  function seguir(url, pre, fases, fin, cadaVez) {
    const paso = () => fetch(url, { cache: 'no-store' }).then(r => r.json()).then(e => {
      if (pre) pre.textContent = (e.registro || []).join('\n');
      if (cadaVez) cadaVez(e);
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
  const mediaSb = d => (R.medias_sb.find(([hasta]) => d < hasta) || R.medias_sb[R.medias_sb.length - 1])[1];
  function horasBrm(km, d, final) {
    const lim = R.limites[d], ap = horasTramos(Math.min(km, d), R.apertura);
    const ci = final || km >= d ? lim : km <= 60 ? km / 20 + 1 : d > 1200 ? Math.min(km / mediaSb(d), lim) : Math.min(horasTramos(km, R.cierre), lim);
    return [Math.round(ap * 60) / 60, Math.round(ci * 60) / 60];
  }

  // ---------- campos generales
  const salida = FechaHora($('salida')), limite = $('limite'), limH = $('limite-h'), limM = $('limite-m'), vel = $('velocidad'), comun = $('parada-comun');
  const modalidad = $('modalidad'), distBrm = $('distancia-brm');
  // distancias que se pueden elegir: las estándar del brevet, 600 en la SR y de 1.200 a 2.000 en los Super Brevets
  const distancias = m => m === 'brevet' ? R.brevet : m === 'sb' ? R.sb : m === 'sr' ? [600] : [];
  const horasTexto = h => dur(h * 60) + ' h';
  function opcionesDistancia(valor) {
    const m = modalidad.value, ds = distancias(m);
    distBrm.innerHTML = ds.map(d => `<option value="${d}">${fmt(d)} km (${horasTexto(m === 'sr' ? R.sr600 : R.limites[d])})</option>`).join('');
    distBrm.disabled = ds.length < 2;
    if (!ds.length) return;
    const cerca = ds.filter(d => d <= TOTAL * 1.05);
    distBrm.value = String(ds.includes(+valor) ? +valor : cerca.length ? Math.max(...cerca) : ds[0]);
  }
  let m0 = (P && P.modalidad) || A.modalidad || 'libre';
  const d0 = (P && P.distancia_brm) || A.distancia_brm;
  if (m0 === 'brevet' && +d0 === 1200) m0 = 'sb';   // planes anteriores: el 1200 era un brevet
  modalidad.value = m0;
  opcionesDistancia(d0);
  // tiempo del reglamento (NaN en el recorrido libre) y si el escrito es otro: entonces los cálculos son personales
  const oficial = () => modalidad.value === 'sr' ? R.sr600 : ['brevet', 'sb'].includes(modalidad.value) ? R.limites[distBrm.value] : NaN;
  const personal = () => isFinite(oficial()) && isFinite(num(limite.value)) && Math.abs(num(limite.value) - oficial()) > 0.01;
  const brevet = () => ['brevet', 'sb'].includes(modalidad.value) && R.limites[distBrm.value] && !personal();
  function explicarModalidad(cambio) {
    const m = modalidad.value;
    $('campo-distancia').hidden = m === 'libre';
    $('etiqueta-limite').textContent = m === 'libre' ? 'Tiempo deseado' : 'Tiempo límite';
    if (cambio && m !== 'libre') ponerLimite(oficial());
    const hoja = A.puntos.some(p => p.cierre_hoja);
    $('explica-modalidad').textContent = m === 'brevet'
      ? 'Brevet: apertura y cierre de los controles según la tabla de Randonneurs Mondiaux' + (hoja ? '; en los intermedios mandan las horas de la hoja del organizador.' : '.') + ' La meta cierra en el tiempo límite oficial.'
      : m === 'sb' ? 'Super Brevet (1.200 km o más): tiempo límite del reglamento de Randonneurs Mondiaux (90 h en 1.200 km; 12 km/h de media de 1.300 a 1.800 km; 10 km/h desde 1.900 km). Apertura según la tabla de RM; cierres intermedios a la media mínima' + (hoja ? ', salvo donde la hoja del organizador trae hora.' : '.')
      : m === 'sr' ? 'Super Randonnée (600 km): sin horas de control; el cierre de cada punto reparte el tiempo límite (60 h) en proporción a la distancia.'
      : 'Recorrido libre: la distancia es la del track y el tiempo, el que quieras emplear. La columna «Objetivo» reparte ese tiempo en proporción a la distancia.';
    explicarLimite();
    verEtapas();
  }
  // Tiempo cambiado a mano y aviso de velocidad media poco realista en bici
  function explicarLimite() {
    const m = modalidad.value, pers = personal(), lim = num(limite.value);
    $('titulo-cierre').textContent = m === 'libre' || pers ? 'Objetivo' : 'Cierre';
    $('limite-oficial').hidden = !pers;
    $('explica-limite').textContent = m === 'libre' ? '' : pers
      ? `Tiempo personal (el oficial es ${horasTexto(oficial())}): los cálculos no siguen la tabla oficial. El tiempo se reparte en proporción a la distancia y no se usan las horas de control de la hoja.`
      : 'El tiempo límite es el del reglamento. Puedes cambiarlo (por ejemplo, en una SR en modalidad cicloturista, que tiene más tiempo): entonces los cálculos pasan a ser personales, no los de la tabla oficial.';
    const v = TOTAL / lim, avisa = (m === 'libre' || pers) && lim > 0 && (v < 12 || v > 28);
    $('aviso-velocidad').hidden = !avisa;
    if (avisa) $('aviso-velocidad').textContent = `Con ${fmt(TOTAL, 0)} km en ${horasTexto(lim)}, la media neta sería de ${fmt(v, 1)} km/h, ${v < 12 ? 'por debajo de 12' : 'por encima de 28'} km/h: en bici, esos tiempos podrían no ser realistas. Si planificas la ruta con otro medio de transporte, no hace falta cambiarlo.`;
  }
  $('nombre').value = P ? P.nombre : A.nombre;
  $('subtitulo').value = P ? P.subtitulo : '';
  salida.value = (P ? P.salida : A.salida) || '';
  // Tiempo en horas y minutos (desplegables que admiten escribir); #limite guarda las horas con decimales
  function ponerLimite(h) {
    limite.value = isFinite(h) && h > 0 ? String(h) : '';
    const total = Math.round(h * 60);
    limH.value = limite.value ? Math.floor(total / 60) : '';
    limM.value = limite.value ? z(total % 60) : '';
  }
  function leerLimite() {
    const h = num(limH.value), m = num(limM.value);
    limite.value = isFinite(h) || isFinite(m) ? String((isFinite(h) ? h : 0) + (isFinite(m) ? m : 0) / 60) : '';
  }
  ponerLimite((P ? P.limite_h : A.limite_h) || NaN);
  const mostrarVel = () => { vel.value = ent(mediaTabla() * V.factor, 1); };
  mostrarVel();
  if (P) {
    document.querySelectorAll('input[name=salida]').forEach(c => { c.checked = P.salidas.includes(c.value); });
    if ($('club') && P.club) $('club').value = P.club;
    $('paleta').value = P.paleta; $('estilo-infografia').value = P.estilo_infografia; $('auto-lugares').checked = P.auto_lugares; $('track-pendiente').checked = !!P.track_pendiente;
    const paradasCtrl = P.puntos.filter((x, i) => A.puntos[i].control && i > 0 && i < N - 1).map(x => x.parada);
    if (paradasCtrl.length) comun.value = ent(paradasCtrl[0]);
  }

  // ---------- etapas (BRM de 400 km o más, SR, Super Brevets y recorridos libres)
  const rec = $('usar-reciente');
  const etActivas = $('et-activas'), etLlegada = FechaHora($('et-llegada')), etDescanso = $('et-descanso'), etCuerpo = document.querySelector('#et-tabla tbody');
  const E0 = P && P.etapas && P.etapas.activas ? P.etapas : null;
  let ET = (E0 ? E0.paradas : []).map((k, n) => ({ km: k, nombre: (A.puntos.find(p => Math.abs(p.km_hoja - k) < 0.01) || {}).nombre || '',
    descanso: E0.descansos && E0.descansos[n] !== undefined ? E0.descansos[n] : E0.descanso_h }));
  let etPendiente = false;
  etActivas.checked = !!E0;
  etLlegada.value = E0 && E0.llegada || '';
  etDescanso.value = ent(E0 ? E0.descanso_h : 8, 1);
  const etapasPosibles = () => ['sr', 'sb', 'libre'].includes(modalidad.value) || (modalidad.value === 'brevet' && +distBrm.value >= 400);
  const etapas = () => etapasPosibles() && etActivas.checked;
  function verEtapas() {
    $('panel-etapas').hidden = !etapasPosibles();
    $('et-campos').hidden = !etapas();
    const fija = etapas() && !!etLlegada.value;   // con llegada prevista, la velocidad sale de ella
    vel.readOnly = fija;
    vel.title = fija ? 'Calculada a partir de la llegada prevista de Etapas' : '';
    $('vel-bloqueada').hidden = !fija;
    $('quitar-llegada').hidden = !fija;
    if (rec) rec.disabled = fija;
  }
  function dibujarEtapas() {
    etCuerpo.innerHTML = ET.map((x, i) => `<tr data-i="${i}"><td>${i + 1}</td>
      <td class="num"><input class="et-km" inputmode="decimal" size="5" value="${x.km === '' ? '' : ent(x.km, 1)}" aria-label="km de la parada ${i + 1}"></td>
      <td><input class="et-nombre" size="20" maxlength="80" value="${esc(x.nombre)}" placeholder="Noche ${i + 1}" aria-label="Lugar de la parada ${i + 1}"></td>
      <td><button type="button" class="discreto ed-mapa" title="Elegir en el mapa" aria-label="Elegir la parada ${i + 1} en el mapa">📍</button></td>
      <td class="num"><input class="et-descanso" inputmode="decimal" size="4" value="${ent(x.descanso, 2)}" aria-label="Descanso de la noche ${i + 1} (h)"></td>
      <td><button type="button" class="discreto et-quitar">Quitar</button></td></tr>`).join('');
    $('et-anadir').disabled = ET.length >= R.max_etapas - 1;
  }
  const marcarEtapas = () => { etPendiente = true; $('et-aviso').textContent = 'Pulsa «Aplicar las etapas a los puntos» para incluir las paradas en el cálculo.'; };
  dibujarEtapas();
  verEtapas();

  // ---------- tabla de puntos
  const cuerpo = document.querySelector('#puntos tbody');
  // tipos de parada, con el icono que llevan en la infografía y la página interactiva (generador/estilo.ICONOS)
  const tipos = [['', '—'], ['salida', '🚩 Salida'], ['cafe', '☕ Café'], ['comida', '🍽 Comida'], ['dormir', '🛏 Dormir'], ['agua', '🚰 Agua'], ['cruce', '🔀 Cruce'], ['peligro', '⚠️ Peligro'], ['interes', '⭐ Punto de interés'], ['poblacion', '🏘️ Población'], ['panoramica', '🏞️ Panorámica'], ['puerto', '⛰️ Puerto'], ['llegada', '🏁 Llegada'], ['otra', '✳️ Otra']];
  const defectoParada = i => (A.puntos[i].control && i > 0 && i < N - 1) ? (num(comun.value) || 0) : 0;
  // Cada fila: lo que se recalcula al momento (paradas, tipo, mapa) y lo que cambia los puntos (control, nombre, km,
  // quitar, añadir), que necesita «Actualizar». Las filas nuevas no tienen datos calculados hasta entonces.
  const fila = (p, i, q) => `<tr ${i === null ? 'class="nuevo"' : `data-i="${i}"`}>
      <td><input type="checkbox" class="mostrar" ${q.mostrar ? 'checked' : ''} aria-label="Mostrar ${esc(p.nombre || 'el punto')} en el mapa"></td>
      <td class="nowrap"><label class="casilla"><input type="checkbox" class="ed-control" data-id="${esc(p.control || '')}" ${p.control ? 'checked' : ''} aria-label="Es un control"> <b>${esc(p.control || '')}</b></label></td>
      <td><input class="ed-nombre" size="17" maxlength="80" value="${esc(p.nombre || '')}" aria-label="Nombre del punto" placeholder="Nombre"></td>
      <td class="num nowrap"><input class="ed-km" inputmode="decimal" size="4" value="${p.km_hoja === undefined ? '' : ent(p.km_hoja, 3)}" aria-label="km"
        ${i !== null && Math.abs(p.km - p.km_hoja) > 0.05 ? `title="${fmt(p.km, 1)} km en el GPX"` : ''}><button type="button" class="discreto ed-mapa" title="Elegir el punto en el mapa" aria-label="Elegir ${esc(p.nombre || 'el punto')} en el mapa" ${i === 0 ? 'disabled' : ''}>📍</button></td>
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
    const t0 = new Date(salida.value), lim = num(limite.value), par = paradas(), sinHoja = personal();
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
      // con un tiempo personal no valen las horas de la hoja: todo se reparte en proporción a la distancia
      const ch = sinHoja ? null : p.cierre_hoja, ah = sinHoja ? null : p.apertura_hoja;
      // en un brevet, la meta cierra siempre en el tiempo límite oficial
      r.cierre = !isFinite(t0) && !ch ? null : rm && i === N - 1 ? new Date(t0.getTime() + rm[1] * 3600e3)
        : ch ? new Date(ch) : !isFinite(t0) ? null : rm ? new Date(t0.getTime() + rm[1] * 3600e3)
        : isFinite(lim) ? new Date(t0.getTime() + p.km / TOTAL * lim * 3600e3) : null;
      r.margen = r.cierre && isFinite(r.salida) ? (r.cierre - r.salida) / 60e3 : NaN;   // al reanudar la marcha (llegada + parada)
      const ap = ah ? new Date(ah) : rm && p.control && i > 0 && isFinite(t0) ? new Date(t0.getTime() + rm[0] * 3600e3) : null;
      r.antes = ap && r.llegada < ap;
      ant = r;
      return r;
    });
  }

  function cifra(t, v, s = '') { return `<div class="cifra"><h3>${t}</h3><b>${v}</b><span>${s}</span></div>`; }
  // Con etapas y llegada prevista, la velocidad en movimiento sale de la llegada: tiempo total menos paradas
  function ajustarALlegada() {
    if (!etapas() || !etLlegada.value || !salida.value) return null;
    const mov = (new Date(etLlegada.value) - new Date(salida.value)) / 36e5 - paradas().reduce((s, x) => s + x, 0) / 60;
    if (!(mov > 0)) return { error: true };
    let h1 = 0;
    A.puntos.forEach((p, i) => { if (i) h1 += p.km_tramo / (base(p.pendiente) * fatiga(p.km / TOTAL)); });
    if (h1 > 0) { V.factor = h1 / mov; mostrarVel(); }
    return { kmh: TOTAL / mov };
  }
  function resumenEtapas(res) {
    if (!etapas()) return;
    const aj = ajustarALlegada(), t0 = res[0].llegada, fin = res[N - 1].llegada, dias = (fin - t0) / 864e5;
    const noches = A.puntos.filter((p, i) => filas[i] && filas[i].querySelector('.tipo').value === 'dormir').length;
    let s = aj && aj.error ? 'Con esa llegada no queda tiempo para pedalear: revisa la llegada, las paradas o el descanso. '
      : aj ? `Para llegar a esa hora, la media en movimiento debe ser de ${fmt(aj.kmh, 1)} km/h (el campo de velocidad la toma de aquí). ` : '';
    if (isFinite(dias)) s += `La ruta dura ${fmt(dias, 1)} días, con ${noches} parada${noches === 1 ? '' : 's'} de tipo «Dormir».`;
    if (dias > R.max_etapas) s += ` Atención: pasa de ${R.max_etapas} días.`;
    $('et-resumen').textContent = s;
  }
  function pintar() {
    if (etapas()) ajustarALlegada();
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
    resumenEtapas(res);
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
  salida.addEventListener('input', pintar);
  [limH, limM].forEach(c => c.addEventListener('input', () => { leerLimite(); explicarLimite(); pintar(); }));
  limM.addEventListener('change', () => { const m = num(limM.value); if (isFinite(m) && m >= 60) { leerLimite(); ponerLimite(num(limite.value)); } });
  modalidad.addEventListener('change', () => { opcionesDistancia(distBrm.value); explicarModalidad(true); pintar(); });
  distBrm.addEventListener('change', () => { explicarModalidad(true); pintar(); });
  $('limite-oficial').addEventListener('click', () => { ponerLimite(oficial()); explicarLimite(); pintar(); });
  explicarModalidad(modalidad.value !== 'libre' && !isFinite(num(limite.value)));
  etActivas.addEventListener('change', () => { verEtapas(); pintar(); });
  etLlegada.addEventListener('input', () => { verEtapas(); pintar(); });
  etLlegada.campo.addEventListener('change', () => { verEtapas(); if (!etLlegada.value) { V.factor = V.factor || 1; mostrarVel(); } pintar(); });
  // el descanso diario es el de partida: las noches que lo tenían cambian con él
  let descansoAnterior = num(etDescanso.value);
  etDescanso.addEventListener('input', () => {
    const v = num(etDescanso.value);
    if (isFinite(v)) { ET.forEach(x => { if (Math.abs(x.descanso - descansoAnterior) < 1e-6) x.descanso = v; }); descansoAnterior = v; dibujarEtapas(); }
    marcarEtapas();
  });
  etCuerpo.addEventListener('input', ev => {
    const f = ev.target.closest('tr'), x = ET[+f.dataset.i];
    if (ev.target.matches('.et-km')) x.km = num(ev.target.value);
    if (ev.target.matches('.et-nombre')) x.nombre = ev.target.value;
    if (ev.target.matches('.et-descanso')) x.descanso = num(ev.target.value);
    marcarEtapas();
  });
  etCuerpo.addEventListener('click', ev => {
    const f = ev.target.closest('tr');
    if (ev.target.closest('.et-quitar')) { ET.splice(+f.dataset.i, 1); dibujarEtapas(); marcarEtapas(); }
    else if (ev.target.closest('.ed-mapa')) {
      const x = ET[+f.dataset.i];
      elegirEnMapa(x.km, !x.nombre, r => { x.km = r.km; if (r.nombre && !x.nombre) x.nombre = r.nombre; dibujarEtapas(); marcarEtapas(); });
    }
  });
  $('et-anadir').addEventListener('click', () => {
    if (ET.length >= R.max_etapas - 1) return;
    const k = TOTAL * (ET.length + 1) / (ET.length + 2);
    ET.push({ km: Math.round(k), nombre: '', descanso: num(etDescanso.value) || 0 }); dibujarEtapas(); marcarEtapas();
  });
  cuerpo.addEventListener('input', pintar);
  vel.addEventListener('input', () => { const v = num(vel.value), m = mediaTabla(); if (v > 0 && m > 0) { V.factor = v / m; pintar(); } });
  vel.addEventListener('change', mostrarVel);
  $('rellenar').addEventListener('click', () => {
    const v = Math.max(0, num(comun.value) || 0);
    filas.forEach((f, i) => { if (A.puntos[i].control && i > 0 && i < N - 1 && f.querySelector('.tipo').value !== 'dormir') f.querySelector('.parada').value = ent(v); });
    pintar();
  });
  $('quitar-llegada').addEventListener('click', () => { etLlegada.value = ''; verEtapas(); mostrarVel(); pintar(); vel.focus(); vel.select(); });
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
  // Temporizador: tiempo desde que empezó la generación y el paso en curso (la consola queda plegada)
  function esperar(inicio) {
    pg.hidden = false; boton.disabled = true;
    let t0 = inicio || (pg.dataset.inicio ? new Date(pg.dataset.inicio) : new Date());
    const reloj = () => {
      const s = Math.max(0, Math.round((Date.now() - t0) / 1000)), h = Math.floor(s / 3600);
      $('gen-tiempo').textContent = (h ? h + ':' + z(Math.floor(s / 60) % 60) : Math.floor(s / 60)) + ':' + z(s % 60);
    };
    reloj(); setInterval(reloj, 1000);
    seguir(X.urlEstado, pg.querySelector('pre'), ['generando'], () => location.reload(), e => {
      if (e.inicio_generar) t0 = new Date(e.inicio_generar);
      const pasos = (e.registro || []).filter(l => /^\S.*(…|\.\.\.)\s*$/.test(l));   // los pasos acaban en «…»; avisos y detalles, no
      $('gen-paso').textContent = pasos.length ? '· ' + pasos[pasos.length - 1] : '';
    });
  }
  // Todo lo que hay en la página (para generar o para guardarlo al editar los puntos)
  function recoger() {
    const salidas = [...document.querySelectorAll('input[name=salida]:checked')].map(c => c.value);
    return {
      nombre: $('nombre').value, subtitulo: $('subtitulo').value, salida: salida.value, limite_h: num(limite.value),
      modalidad: modalidad.value, distancia_brm: modalidad.value === 'libre' ? null : +distBrm.value,
      etapas: etapas() ? { activas: true, llegada: etLlegada.value || null, descanso_h: num(etDescanso.value) || 0,
        paradas: ET.filter(x => isFinite(num(x.km))).map(x => num(x.km)), descansos: ET.filter(x => isFinite(num(x.km))).map(x => isFinite(x.descanso) ? x.descanso : num(etDescanso.value) || 0) } : null,
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
      .then(({ ok, j }) => { if (ok) esperar(new Date()); else { boton.disabled = false; $('aviso-generar').textContent = j.error || 'No se ha podido generar.'; } })
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
  function listaFilas() {
    const par = paradas();
    return [...cuerpo.rows].filter(f => !f.classList.contains('quitado')).map(f => {
      const i = f.dataset.i === undefined ? null : +f.dataset.i, o = i === null ? {} : A.puntos[i];
      const c = f.querySelector('.ed-control');
      return { control: c.checked ? (c.dataset.id || 'sí') : '', nombre: f.querySelector('.ed-nombre').value.trim(), km: f.querySelector('.ed-km').value.trim(),
        cierre_hoja: o.cierre_hoja || null, apertura_hoja: o.apertura_hoja || null, localidad: o.localidad ?? true,
        mostrar: f.querySelector('.mostrar').checked, parada: i === null ? Math.max(0, num(f.querySelector('.parada').value) || 0) : par[i],
        tipo: f.querySelector('.tipo').value };
    });
  }
  function enviarPuntos(lista, avisoEn, boton) {
    if (lista.length < 2) { avisoEn.textContent = 'La ruta necesita al menos la salida y la meta.'; return; }
    if (lista.some(x => !x.nombre || !isFinite(num(x.km)))) { avisoEn.textContent = 'Cada punto necesita un nombre y un km.'; return; }
    boton.disabled = true; avisoEn.textContent = 'Actualizando…';
    fetch(X.urlPuntos, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...recoger(), lista }) })
      .then(r => r.json().then(j => ({ ok: r.ok, j })))
      .then(({ ok, j }) => { if (ok) location.reload(); else { boton.disabled = false; avisoEn.textContent = j.error || 'No se han podido actualizar los puntos.'; } })
      .catch(() => { boton.disabled = false; avisoEn.textContent = 'No se ha podido contactar con VenB.'; });
  }
  actualizar.addEventListener('click', () => enviarPuntos(listaFilas(), aviso, actualizar));
  // Las paradas para dormir pasan a la tabla: un punto existente a menos de 1 km o uno nuevo, de tipo «Dormir»
  $('et-aplicar').addEventListener('click', () => {
    const lista = listaFilas(), diario = num(etDescanso.value) || 0, avisoEt = $('et-aviso');
    if (ET.some(x => !isFinite(num(x.km)) || num(x.km) <= 0 || num(x.km) >= A.puntos[N - 1].km_hoja)) { avisoEt.textContent = 'Cada parada necesita un km entre la salida y la meta.'; return; }
    if (ET.some(x => !(x.descanso >= 0 && x.descanso <= 48))) { avisoEt.textContent = 'El descanso de cada noche debe estar entre 0 y 48 h.'; return; }
    const nuevas = ET.map(x => num(x.km));
    (E0 ? E0.paradas : []).forEach(k => {     // paradas aplicadas antes que ya no están
      if (nuevas.some(n => Math.abs(n - k) <= 1)) return;
      const q = lista.find(x => Math.abs(num(x.km) - k) < 0.05 && x.tipo === 'dormir');
      if (q) { q.tipo = ''; q.parada = 0; }
    });
    ET.forEach((x, n) => {
      const min = Math.round((isFinite(x.descanso) ? x.descanso : diario) * 60), k = num(x.km), q = lista.reduce((a, y) => (Math.abs(num(y.km) - k) <= 1 && (!a || Math.abs(num(y.km) - k) < Math.abs(num(a.km) - k)) ? y : a), null);
      if (q) { q.tipo = 'dormir'; q.parada = min; x.km = num(q.km); }
      else lista.push({ control: '', nombre: x.nombre.trim() || `Noche ${n + 1}`, km: String(k), cierre_hoja: null, apertura_hoja: null, localidad: true, mostrar: true, parada: min, tipo: 'dormir' });
    });
    lista.sort((a, b) => num(a.km) - num(b.km));
    enviarPuntos(lista, avisoEt, $('et-aplicar'));
  });
  // ---------- elegir un punto en el mapa: el punto del track más cercano a donde se pulsa
  const dm = $('dialogo-mapa');
  let TR = null, mapa = null, marca = null, elegido = null, alHecho = null;
  // km del GPX → km de la hoja (los km de la tabla), interpolando entre los puntos del análisis
  function aHoja(kg) {
    const ps = A.puntos;
    if (kg <= ps[0].km) return ps[0].km_hoja;
    for (let i = 1; i < ps.length; i++) if (kg <= ps[i].km) {
      const a = ps[i - 1], b = ps[i], f = b.km > a.km ? (kg - a.km) / (b.km - a.km) : 0;
      return a.km_hoja + f * (b.km_hoja - a.km_hoja);
    }
    const u = ps[ps.length - 1];
    return u.km_hoja * kg / (u.km || 1);
  }
  function aGpx(kh) {
    const ps = A.puntos;
    for (let i = 1; i < ps.length; i++) if (kh <= ps[i].km_hoja) {
      const a = ps[i - 1], b = ps[i], f = b.km_hoja > a.km_hoja ? (kh - a.km_hoja) / (b.km_hoja - a.km_hoja) : 0;
      return a.km + f * (b.km - a.km);
    }
    return ps[ps.length - 1].km;
  }
  const metros = (a, b) => { const k = Math.cos(a[0] * Math.PI / 180); return Math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * k); };
  function cercanos(ll) {
    // el más cercano y, si la ruta pasa varias veces cerca (ida y vuelta, bucles), uno por cada paso
    const d = TR.map(p => metros(p, ll)), mejor = Math.min(...d), pasos = [];
    d.forEach((x, i) => {
      if (x > mejor * 1.5 + 100) return;
      const u = pasos[pasos.length - 1];
      if (u && TR[i][2] - TR[u.i][2] < 2) { if (x < u.d) Object.assign(u, { i, d: x }); }
      else pasos.push({ i, d: x });
    });
    return pasos.sort((a, b) => a.d - b.d);
  }
  function marcar(i, d) {
    const p = TR[i];
    elegido = { km: Math.round(aHoja(p[2]) * 10) / 10, nombre: elegido && elegido.nombre };
    if (marca) marca.setLatLng([p[0], p[1]]); else marca = L.marker([p[0], p[1]]).addTo(mapa);
    $('mapa-resultado').textContent = `km ${fmt(elegido.km, 1)} de la ruta` + (d !== undefined ? ` (a ${fmt(d)} m de donde has pulsado)` : '') + (elegido.nombre ? ` · ${elegido.nombre}` : '');
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
      'IGN: topográfico': L.tileLayer('https://tms-mapa-raster.ign.es/1.0.0/mapa-raster/{z}/{x}/{y}.jpeg', { tms: true, maxZoom: 17, attribution: '© IGN España (CC BY 4.0)' }),
      'OpenStreetMap': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }),
    };
    (espana ? capas['IGN: topográfico'] : capas.OpenStreetMap).addTo(mapa);
    L.control.layers(capas).addTo(mapa);
    L.polyline(TR.map(p => [p[0], p[1]]), { color: '#c62828', weight: 4, opacity: .85 }).addTo(mapa);
    A.puntos.forEach(p => {
      const q = TR.reduce((a, x) => Math.abs(x[2] - p.km) < Math.abs(a[2] - p.km) ? x : a, TR[0]);
      L.circleMarker([q[0], q[1]], { radius: p.control ? 6 : 4, color: '#1565c0', weight: 2, fillOpacity: .7 }).bindTooltip(`${p.control ? p.control + ' · ' : ''}${p.nombre} (km ${fmt(p.km_hoja, 1)})`).addTo(mapa);
    });
    mapa.on('click', ev => {
      const ll = [ev.latlng.lat, ev.latlng.lng], pasos = cercanos(ll);
      elegido = null;
      marcar(pasos[0].i, pasos[0].d);
      $('mapa-alternativas').innerHTML = pasos.length > 1 ? 'La ruta pasa varias veces por aquí: ' + pasos.map((x, n) =>
        `<button type="button" class="discreto" data-i="${x.i}" data-d="${Math.round(x.d)}">km ${fmt(aHoja(TR[x.i][2]), 1)}</button>`).join(' ') : '';
      if (alHecho && alHecho.nombre) localidad(ll);
    });
  }
  $('mapa-alternativas').addEventListener('click', ev => { const b = ev.target.closest('button'); if (b) marcar(+b.dataset.i, +b.dataset.d); });
  async function elegirEnMapa(kmActual, pedirNombre, hecho) {
    alHecho = { fn: hecho, nombre: pedirNombre };
    elegido = null; $('mapa-usar').disabled = true; $('mapa-resultado').textContent = ''; $('mapa-alternativas').innerHTML = '';
    dm.showModal();
    if (!window.L) { $('mapa-resultado').textContent = 'No se ha podido cargar el mapa: comprueba la conexión a Internet.'; return; }
    if (!TR) {
      $('mapa-resultado').textContent = 'Cargando el track…';
      try { TR = await fetch(X.urlTrazado).then(r => r.json()); } catch (e) { TR = []; }
      if (TR.length < 2) { $('mapa-resultado').textContent = 'No se ha podido leer el track del GPX.'; TR = null; return; }
      $('mapa-resultado').textContent = '';
      prepararMapa();
    }
    mapa.invalidateSize();
    if (marca) { marca.remove(); marca = null; }
    const k = num(kmActual);
    if (isFinite(k) && k > 0) {
      const kg = aGpx(k), i = TR.reduce((a, x, n) => Math.abs(x[2] - kg) < Math.abs(TR[a][2] - kg) ? n : a, 0);
      mapa.setView([TR[i][0], TR[i][1]], 14);
      marcar(i);
    } else mapa.fitBounds(L.latLngBounds(TR.map(p => [p[0], p[1]])), { padding: [20, 20] });
  }
  $('mapa-usar').addEventListener('click', () => { const r = elegido; dm.close(); if (r && alHecho) alHecho.fn(r); });
  $('mapa-cancelar').addEventListener('click', () => dm.close());
  cuerpo.addEventListener('click', ev => {
    const b = ev.target.closest('.ed-mapa');
    if (!b) return;
    const f = b.closest('tr'), nombre = f.querySelector('.ed-nombre');
    elegirEnMapa(f.querySelector('.ed-km').value, !nombre.value.trim(), r => {
      f.querySelector('.ed-km').value = ent(r.km, 1);
      if (r.nombre && !nombre.value.trim()) nombre.value = r.nombre;
      marcarPendiente();
    });
  });

  pintar();
  if (X.fase === 'generando') esperar();
})();
