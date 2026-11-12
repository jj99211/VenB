// Submenús: se abren al pasar el ratón (CSS) y, en pantallas táctiles o con teclado, con el botón ▾.
document.querySelectorAll('.abrir-sub').forEach(b => {
  b.addEventListener('click', e => {
    const li = b.parentElement, abrir = !li.classList.contains('abierto');
    document.querySelectorAll('.con-sub.abierto').forEach(x => { x.classList.remove('abierto'); x.querySelector('.abrir-sub').setAttribute('aria-expanded', 'false'); });
    li.classList.toggle('abierto', abrir);
    b.setAttribute('aria-expanded', String(abrir));
    e.stopPropagation();
  });
});
document.addEventListener('click', e => {
  if (!e.target.closest('.con-sub')) document.querySelectorAll('.con-sub.abierto').forEach(x => { x.classList.remove('abierto'); x.querySelector('.abrir-sub').setAttribute('aria-expanded', 'false'); });
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.querySelectorAll('.con-sub.abierto').forEach(x => { x.classList.remove('abierto'); x.querySelector('.abrir-sub').setAttribute('aria-expanded', 'false'); x.querySelector('.abrir-sub').focus(); });
});
// Pantallas estrechas: el botón ☰ abre y cierra el menú
const plegar = document.querySelector('.plegar-menu');
if (plegar) {
  plegar.addEventListener('click', () => {
    const abrir = !plegar.closest('header').classList.contains('menu-abierto');
    plegar.closest('header').classList.toggle('menu-abierto', abrir);
    plegar.setAttribute('aria-expanded', String(abrir));
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && plegar.getAttribute('aria-expanded') === 'true') { plegar.click(); plegar.focus(); }
  });
}
// El menú queda fijo arriba: los enlaces a una sección de la página (#…) no deben quedar tapados por él.
const cabecera = document.querySelector('header');
const ajustarCabecera = () => {
  if (!cabecera) return;
  document.documentElement.style.scrollPaddingTop = (cabecera.offsetHeight + 8) + 'px';
  document.documentElement.style.setProperty('--alto-menu', cabecera.offsetHeight + 'px');   // cabeceras de tabla fijas
};
ajustarCabecera();
window.addEventListener('resize', ajustarCabecera);
