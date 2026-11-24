/* VenB: rutas insertadas en otra web (iframe con class="venb-ruta").
 *
 * La página de cada ruta (generada por VenB) envía su altura con postMessage cada vez que cambia:
 *   {tipo: "venb-ruta", version: 1, altura: <px>}
 * Como la ruta puede cargarse antes que este script (y su primer aviso perderse), al cargar se la pide a cada iframe:
 *   {tipo: "venb-ruta", version: 1, pedir: "altura"}
 * Este script, cargado una vez en la página que contiene los iframes, ajusta cada iframe a la altura de su ruta,
 * así no hay desplazamiento dentro del iframe. Sin este script, el iframe conserva el alto que tenga en su estilo.
 *
 * Se sube una sola vez a la carpeta de rutas de la web (junto a las carpetas de cada ruta) y se carga con
 *   <script src="https://tu-web/rutas/venb-insertar.js" defer></script>
 * Cada versión de VenB trae la última: basta con sustituir este fichero; la página de la web no cambia.
 * Solo acepta mensajes de sus propios iframes y solo cambia la altura, entre un mínimo y un máximo.
 *
 * Autor: José A. Jiménez (VenB, vivirenbici.es). Licencia CC BY-NC-SA 4.0.
 */
(function () {
  "use strict";
  if (window.venbInsertar) return;            // cargado más de una vez en la misma página: basta con una
  var MIN = 300, MAX = 20000;
  window.venbInsertar = {version: 1};

  window.addEventListener("message", function (e) {
    var d = e.data;
    if (!d || d.tipo !== "venb-ruta" || typeof d.altura !== "number") return;
    var marcos = document.querySelectorAll("iframe.venb-ruta");
    for (var i = 0; i < marcos.length; i++) {
      if (marcos[i].contentWindow === e.source) {
        var h = Math.round(Math.min(MAX, Math.max(MIN, d.altura)));
        marcos[i].style.height = h + "px";
        return;
      }
    }
  });

  function pedirAlturas() {
    var marcos = document.querySelectorAll("iframe.venb-ruta");
    for (var i = 0; i < marcos.length; i++) {
      try { marcos[i].contentWindow.postMessage({tipo: "venb-ruta", version: 1, pedir: "altura"}, "*"); } catch (err) { /* aún sin cargar */ }
    }
  }
  pedirAlturas();
  if (document.readyState !== "complete") window.addEventListener("load", pedirAlturas);
})();
