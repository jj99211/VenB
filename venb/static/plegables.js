// Secciones plegables (details.plegable con id): VenB recuerda en este navegador, página a página, cuáles dejaste
// abiertas o plegadas; un enlace a #sección (o una tarjeta) la abre aunque estuviera plegada.
(() => {
  const secciones = [...document.querySelectorAll('details.plegable[id]')];
  if (!secciones.length) return;
  const clave = 'venb-plegables:' + location.pathname;
  let g = {};
  try { g = JSON.parse(localStorage.getItem(clave) || '{}'); } catch (e) { /* solo es una comodidad */ }
  secciones.forEach(d => {
    if (d.id in g && !d.hasAttribute('data-abrir')) d.open = g[d.id];
    d.addEventListener('toggle', () => { g[d.id] = d.open; try { localStorage.setItem(clave, JSON.stringify(g)); } catch (e) {} });
  });
  const abrir = id => {
    const d = id && document.getElementById(id);
    const s = d && (d.matches('details.plegable') ? d : d.closest('details.plegable'));
    if (s) { s.open = true; d.scrollIntoView(); }
  };
  addEventListener('hashchange', () => abrir(decodeURIComponent(location.hash.slice(1))));
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href^="#"]');
    if (a) abrir(decodeURIComponent(a.getAttribute('href').slice(1)));
  });
  abrir(decodeURIComponent(location.hash.slice(1)));
})();
