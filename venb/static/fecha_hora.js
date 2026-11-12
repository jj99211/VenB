// Campo de fecha y hora en español: se escribe «DD/MM/AAAA HH:MM» y el botón abre un calendario de lunes a domingo.
// Uso: const c = FechaHora(input); c.value devuelve o recibe la fecha en ISO local («AAAA-MM-DDTHH:MM», '' si no es válida).
window.FechaHora = (() => {
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const DIAS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
  const z = n => String(n).padStart(2, '0');
  const aIso = d => `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`;
  const aTexto = d => `${z(d.getDate())}/${z(d.getMonth() + 1)}/${d.getFullYear()} ${z(d.getHours())}:${z(d.getMinutes())}`;

  function leer(texto) {
    const m = String(texto || '').trim().match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{4})(?:[ T,]+(\d{1,2})[:.h](\d{2}))?$/);
    if (!m) return null;
    const d = new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0));
    return d.getDate() === +m[1] && d.getMonth() === +m[2] - 1 && +(m[4] || 0) < 24 ? d : null;
  }
  function deIso(iso) {
    const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
    return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null;
  }

  return function (campo) {
    campo.type = 'text';
    campo.placeholder = 'DD/MM/AAAA HH:MM';
    campo.inputMode = 'numeric';
    campo.autocomplete = 'off';
    campo.size = 16;
    const caja = document.createElement('span');
    caja.className = 'fecha-hora';
    campo.replaceWith(caja);
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'discreto abrir-calendario';
    boton.title = 'Elegir en el calendario';
    boton.setAttribute('aria-label', 'Elegir la fecha en el calendario');
    boton.setAttribute('aria-expanded', 'false');
    boton.textContent = '📅';
    const panel = document.createElement('div');
    panel.className = 'calendario-emergente';
    panel.hidden = true;
    caja.append(campo, boton, panel);

    let vista = new Date();          // mes que se ve en el calendario
    const avisar = () => campo.dispatchEvent(new Event('input', { bubbles: true }));
    const comprobar = () => campo.classList.toggle('no-valido', !!campo.value.trim() && !leer(campo.value));
    campo.addEventListener('input', comprobar);
    campo.addEventListener('blur', () => { const d = leer(campo.value); if (d) campo.value = aTexto(d); comprobar(); });

    function pintar() {
      const actual = leer(campo.value);
      const y = vista.getFullYear(), m = vista.getMonth();
      const primero = (new Date(y, m, 1).getDay() + 6) % 7;      // lunes = 0
      const dias = new Date(y, m + 1, 0).getDate();
      const hoy = new Date();
      let celdas = '';
      for (let i = 0; i < primero; i++) celdas += '<span></span>';
      for (let d = 1; d <= dias; d++) {
        const elegido = actual && actual.getFullYear() === y && actual.getMonth() === m && actual.getDate() === d;
        const esHoy = hoy.getFullYear() === y && hoy.getMonth() === m && hoy.getDate() === d;
        celdas += `<button type="button" data-dia="${d}" class="${elegido ? 'elegido' : ''}${esHoy ? ' hoy' : ''}" aria-label="${d} de ${MESES[m]} de ${y}"${elegido ? ' aria-pressed="true"' : ''}>${d}</button>`;
      }
      const h = actual ? actual.getHours() : 7, mi = actual ? actual.getMinutes() : 0;
      panel.innerHTML = `<div class="cal-cab"><button type="button" class="discreto" data-mover="-1" aria-label="Mes anterior">‹</button>
        <b>${MESES[m][0].toUpperCase() + MESES[m].slice(1)} ${y}</b><button type="button" class="discreto" data-mover="1" aria-label="Mes siguiente">›</button></div>
        <div class="cal-dias">${DIAS.map(x => `<span>${x}</span>`).join('')}${celdas}</div>
        <div class="cal-hora"><label>Hora <input class="cal-h" inputmode="numeric" size="2" maxlength="2" value="${z(h)}"></label>:<input class="cal-m" inputmode="numeric" size="2" maxlength="2" value="${z(mi)}" aria-label="Minutos">
        <button type="button" class="discreto cal-cerrar">Cerrar</button></div>`;
    }
    function hora() {
      const h = Math.min(23, Math.max(0, parseInt(panel.querySelector('.cal-h').value, 10) || 0));
      const m = Math.min(59, Math.max(0, parseInt(panel.querySelector('.cal-m').value, 10) || 0));
      return [h, m];
    }
    function abrir() {
      vista = leer(campo.value) || new Date();
      vista = new Date(vista.getFullYear(), vista.getMonth(), 1);
      pintar();
      panel.hidden = false;
      boton.setAttribute('aria-expanded', 'true');
      (panel.querySelector('.elegido') || panel.querySelector('[data-dia]')).focus();
    }
    function cerrar(volver) {
      panel.hidden = true;
      boton.setAttribute('aria-expanded', 'false');
      if (volver) boton.focus();
    }
    boton.addEventListener('click', () => (panel.hidden ? abrir() : cerrar()));
    panel.addEventListener('click', e => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.mover) { vista = new Date(vista.getFullYear(), vista.getMonth() + +b.dataset.mover, 1); pintar(); return; }
      if (b.classList.contains('cal-cerrar')) { cerrar(true); return; }
      if (b.dataset.dia) {
        const [h, m] = hora();
        campo.value = aTexto(new Date(vista.getFullYear(), vista.getMonth(), +b.dataset.dia, h, m));
        comprobar(); avisar(); cerrar(true);
      }
    });
    panel.addEventListener('change', e => {   // cambiar la hora sin tocar el día
      if (!e.target.matches('.cal-h, .cal-m')) return;
      const d = leer(campo.value);
      if (!d) return;
      const [h, m] = hora();
      d.setHours(h, m);
      campo.value = aTexto(d); comprobar(); avisar();
    });
    panel.addEventListener('keydown', e => { if (e.key === 'Escape') cerrar(true); });
    document.addEventListener('click', e => { if (!panel.hidden && !caja.contains(e.target)) cerrar(); });

    return {
      get value() { const d = leer(campo.value); return d ? aIso(d) : ''; },
      set value(iso) { const d = deIso(iso); campo.value = d ? aTexto(d) : ''; comprobar(); },
      addEventListener: (...a) => campo.addEventListener(...a),
      campo,
    };
  };
})();
