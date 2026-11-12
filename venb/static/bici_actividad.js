// Bici de cada actividad (Histórico y cierre del mes en Bicis): guarda al cambiar el desplegable.
// VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0.
(function () {
  document.querySelectorAll('select.bici-actividad').forEach(function (s) {
    var antes = s.value;
    s.addEventListener('change', function () {
      var nota = s.parentElement.querySelector('.nota-bici'), datos = new FormData();
      datos.append('bici', s.value);
      s.disabled = true;
      fetch(s.dataset.url, { method: 'POST', body: datos })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || 'No se ha podido guardar.'); return j; }); })
        .then(function (j) {
          if (j.valor !== undefined) s.value = j.valor;  // si quitas la tuya, vuelve la de Garmin Connect
          antes = s.value;
          if (s.dataset.recargar) { location.reload(); return; }
          if (nota) { nota.textContent = j.aviso || ''; nota.hidden = !j.aviso; }
        })
        .catch(function (e) {
          s.value = antes;
          if (nota) { nota.textContent = e.message; nota.hidden = false; }
        })
        .finally(function () { s.disabled = false; });
    });
  });
})();
