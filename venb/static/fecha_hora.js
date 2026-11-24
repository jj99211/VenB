// Campo de fecha y hora en español: la fecha se escribe «DD/MM/AAAA» o se elige en un calendario de lunes a domingo
// (botón 📅) y la hora, en dos desplegables (horas y minutos de 5 en 5).
// Uso: const c = FechaHora(input); c.value devuelve o recibe la fecha en ISO local («AAAA-MM-DDTHH:MM», '' si no es
// válida); c.disabled la desactiva entera.
window.FechaHora = (() => {
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const DIAS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
  const z = n => String(n).padStart(2, '0');
  const aIso = d => `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`;
  const aTexto = d => `${z(d.getDate())}/${z(d.getMonth() + 1)}/${d.getFullYear()}`;

  // fecha escrita (admite también la hora detrás, como antes: «12/08/2027 07:30»)
  function leer(texto) {
    const m = String(texto || '').trim().match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{4})(?:[ T,]+(\d{1,2})[:.h](\d{2}))?$/);
    if (!m) return null;
    const d = new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0));
    if (d.getDate() !== +m[1] || d.getMonth() !== +m[2] - 1 || +(m[4] || 0) > 23 || +(m[5] || 0) > 59) return null;
    return { fecha: d, hora: m[4] !== undefined ? [+m[4], +m[5]] : null };
  }
  function deIso(iso) {
    const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
    return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null;
  }
  const opciones = (desde, hasta, paso) => { let s = ''; for (let i = desde; i <= hasta; i += paso) s += `<option value="${i}">${z(i)}</option>`; return s; };

  return function (campo) {
    campo.type = 'text';
    campo.placeholder = 'DD/MM/AAAA';
    campo.inputMode = 'numeric';
    campo.autocomplete = 'off';
    campo.size = 11;
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
    const selH = document.createElement('select'), selM = document.createElement('select');
    selH.className = 'hora-h'; selM.className = 'hora-m';
    selH.setAttribute('aria-label', 'Hora'); selM.setAttribute('aria-label', 'Minutos');
    selH.innerHTML = opciones(0, 23, 1); selM.innerHTML = opciones(0, 55, 5);
    selH.value = '7'; selM.value = '0';
    const hora = document.createElement('span');
    hora.className = 'hora-desplegables';
    hora.append(selH, document.createTextNode(':'), selM, document.createTextNode(' h'));
    const panel = document.createElement('div');
    panel.className = 'calendario-emergente';
    panel.hidden = true;
    caja.append(campo, boton, hora, panel);

    // minutos que no son múltiplo de 5 (de una hoja de ruta o de un plan antiguo): se añaden a la lista
    function ponerMinutos(m) {
      if (![...selM.options].some(o => +o.value === m)) {
        const o = document.createElement('option'); o.value = m; o.textContent = z(m);
        const sig = [...selM.options].find(x => +x.value > m);
        selM.insertBefore(o, sig || null);
      }
      selM.value = String(m);
    }
    function ponerHora(h, m) { selH.value = String(h); ponerMinutos(m); }

    let vista = new Date();          // mes que se ve en el calendario
    const avisar = () => campo.dispatchEvent(new Event('input', { bubbles: true }));
    const comprobar = () => campo.classList.toggle('no-valido', !!campo.value.trim() && !leer(campo.value));
    campo.addEventListener('input', comprobar);
    campo.addEventListener('blur', () => {
      const r = leer(campo.value);
      if (r) { campo.value = aTexto(r.fecha); if (r.hora) { ponerHora(...r.hora); avisar(); } }
      comprobar();
    });
    [selH, selM].forEach(s => s.addEventListener('change', avisar));

    function pintar() {
      const r = leer(campo.value), actual = r && r.fecha;
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
      panel.innerHTML = `<div class="cal-cab"><button type="button" class="discreto" data-mover="-1" aria-label="Mes anterior">‹</button>
        <b>${MESES[m][0].toUpperCase() + MESES[m].slice(1)} ${y}</b><button type="button" class="discreto" data-mover="1" aria-label="Mes siguiente">›</button></div>
        <div class="cal-dias">${DIAS.map(x => `<span>${x}</span>`).join('')}${celdas}</div>
        <div class="cal-hora"><span class="suave">La hora, en los desplegables junto a la fecha.</span>
        <button type="button" class="discreto cal-cerrar">Cerrar</button></div>`;
    }
    function abrir() {
      const r = leer(campo.value);
      vista = r ? r.fecha : new Date();
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
      if (b.dataset.mover) { vista = new Date(vista.getFullYear(), vista.getMonth() + +b.dataset.mover, 1); pintar(); panel.querySelector(`[data-mover="${b.dataset.mover}"]`).focus(); return; }
      if (b.classList.contains('cal-cerrar')) { cerrar(true); return; }
      if (b.dataset.dia) {
        campo.value = aTexto(new Date(vista.getFullYear(), vista.getMonth(), +b.dataset.dia));
        comprobar(); avisar(); cerrar(true);
      }
    });
    panel.addEventListener('keydown', e => { if (e.key === 'Escape') cerrar(true); });
    // al cambiar de mes el panel se rehace y el botón pulsado ya no está en la página: no es un clic fuera
    document.addEventListener('click', e => { if (!panel.hidden && e.target.isConnected && !caja.contains(e.target)) cerrar(); });

    return {
      get value() {
        const r = leer(campo.value);
        if (!r) return '';
        const d = new Date(r.fecha); d.setHours(+selH.value, +selM.value);
        return aIso(d);
      },
      set value(iso) {
        const d = deIso(iso);
        campo.value = d ? aTexto(d) : '';
        if (d) ponerHora(d.getHours(), d.getMinutes());
        comprobar();
      },
      get disabled() { return campo.disabled; },
      set disabled(v) { [campo, boton, selH, selM].forEach(x => { x.disabled = !!v; }); if (v) cerrar(); },
      addEventListener: (...a) => campo.addEventListener(...a),
      campo,
    };
  };
})();
