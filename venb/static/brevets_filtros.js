// Brevets: filtros del historial, en el navegador y sin recargar. Muestra cuántas pruebas y km quedan a la vista
// y recuerda la selección en este navegador (localStorage, como los plegables).
(() => {
  const f = document.getElementById('filtros');
  if (!f) return;
  const filas = [...document.querySelectorAll('.tabla-brevets tbody tr')];
  const tramos = JSON.parse(f.dataset.tramos || '[]');
  const recuento = document.getElementById('recuento');
  const mas = document.getElementById('filtros-mas'), botonMas = document.getElementById('mas-filtros');
  const clave = 'venb-filtros:' + location.pathname;
  const campos = [...f.elements].filter(e => e.name);
  const iso = t => { const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec((t || '').trim()); return m ? `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}` : ''; };
  const n = x => String(Math.round(x)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');   // 5.500, como en el resto de VenB
  const v = nombre => { const e = f.elements[nombre]; return e.type === 'checkbox' ? e.checked : e.value; };

  function pasa(tr) {
    const d = tr.dataset, fecha = d.fecha || '', km = parseFloat(d.km) || 0;
    const q = v('q').trim().toLowerCase();
    if (q && !(d.nombre || '').toLowerCase().includes(q)) return false;
    if (v('anio') && fecha.slice(0, 4) !== v('anio')) return false;
    if (v('temp')) {   // temporada randonneur: de noviembre del año anterior a octubre
      const t = +fecha.slice(0, 4) + (+fecha.slice(5, 7) >= 11 ? 1 : 0);
      if (String(t) !== v('temp')) return false;
    }
    if (v('tipo') && d.tipo !== v('tipo')) return false;
    if (v('dist') !== '') { const t = tramos[+v('dist')]; if (!t || km < t[1] || km >= t[2]) return false; }
    if (v('org') && d.org !== v('org')) return false;
    if (v('ins') && d.ins !== v('ins')) return false;
    for (const k of ['hom', 'r5', 'r10', 'act']) if (v(k) !== '' && d[k] !== v(k)) return false;
    if (v('pbp') && !(fecha >= '2026-11-01' && fecha <= '2027-06-30')) return false;
    const p = v('pct');
    if (p) {
      const x = d.pct === '' ? null : +d.pct;
      if (p === 'sin') { if (x !== null) return false; }
      else if (x === null) return false;
      else if (p === '-75' && x > 75) return false;
      else if (p === '75-90' && (x <= 75 || x > 90)) return false;
      else if (p === '90-' && x <= 90) return false;
    }
    const desde = iso(v('desde')), hasta = iso(v('hasta'));
    if (desde && fecha < desde) return false;
    if (hasta && fecha > hasta) return false;
    return true;
  }

  function aplicar() {
    let cuantas = 0, km = 0;
    filas.forEach(tr => { const ok = pasa(tr); tr.hidden = !ok; if (ok) { cuantas++; km += parseFloat(tr.dataset.km) || 0; } });
    const activos = campos.some(e => e.type === 'checkbox' ? e.checked : e.value);
    recuento.textContent = `${activos ? 'Se ven' : 'En total'}: ${cuantas} ${cuantas === 1 ? 'prueba' : 'pruebas'}, ${n(km)} km` + (activos ? ` (de ${filas.length})` : '') + '.';
    const g = {};
    campos.forEach(e => { g[e.name] = e.type === 'checkbox' ? e.checked : e.value; });
    g._mas = !mas.hidden;
    try { localStorage.setItem(clave, JSON.stringify(g)); } catch (e) { /* solo es una comodidad */ }
  }

  function verMas(abrir) { mas.hidden = !abrir; botonMas.setAttribute('aria-expanded', String(abrir)); botonMas.textContent = abrir ? 'Menos filtros ▴' : 'Más filtros ▾'; }

  let g = {};
  try { g = JSON.parse(localStorage.getItem(clave) || '{}'); } catch (e) { /* sin memoria */ }
  campos.forEach(e => { if (e.name in g) { if (e.type === 'checkbox') e.checked = !!g[e.name]; else e.value = g[e.name]; } });
  verMas(!!g._mas || ['ins', 'hom', 'r5', 'r10', 'act', 'pct', 'desde', 'hasta'].some(k => g[k]));
  f.addEventListener('input', aplicar);
  f.addEventListener('change', aplicar);
  botonMas.addEventListener('click', () => { verMas(mas.hidden); aplicar(); });
  document.getElementById('quitar-filtros').addEventListener('click', () => {
    campos.forEach(e => { if (e.type === 'checkbox') e.checked = false; else e.value = ''; });
    aplicar();
  });
  aplicar();
})();
