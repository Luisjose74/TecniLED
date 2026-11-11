/* G1-161 / G1-162: botón visible para abrir el calendario de los campos de fecha.
 *
 * Los input[type="date"] ya tienen selector nativo, pero en modo oscuro el
 * icono se pierde y en algunos navegadores no aparece. Este script agrega un
 * botón con icono al lado del campo que abre el selector con showPicker().
 * Es una mejora progresiva: si el script no carga, el campo sigue funcionando.
 */
(function () {
  'use strict';

  var ICONO_CALENDARIO =
    '<svg aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">' +
    '<rect x="3" y="4" width="18" height="18" rx="2"></rect>' +
    '<path d="M16 2v4M8 2v4M3 10h18"></path></svg>';

  function etiquetaDelCampo(campo) {
    var etiqueta = campo.getAttribute('aria-label');
    if (etiqueta) {
      return etiqueta;
    }
    var id = campo.getAttribute('id');
    if (id) {
      var label = document.querySelector('label[for="' + id + '"]');
      if (label && label.textContent.trim()) {
        return label.textContent.trim().replace(/\s*\*$/, '');
      }
    }
    return 'la fecha';
  }

  function abrirSelector(campo) {
    if (typeof campo.showPicker === 'function') {
      try {
        campo.showPicker();
        return;
      } catch (error) {
        /* Algunos navegadores exigen un gesto del usuario o el campo visible;
           si falla, se intenta el enfoque normal antes de rendirse. */
      }
    }
    campo.focus();
    campo.click();
  }

  function crearBoton(campo) {
    var boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'boton-calendario';
    boton.title = 'Abrir el calendario';
    boton.setAttribute('aria-label', 'Abrir el calendario de ' + etiquetaDelCampo(campo));
    boton.innerHTML = ICONO_CALENDARIO;
    boton.addEventListener('click', function () {
      abrirSelector(campo);
    });
    return boton;
  }

  function mejorarCampo(campo) {
    if (campo.dataset.calendarioListo === 'si') {
      return;
    }
    var contenedor = campo.parentNode;
    if (!contenedor || contenedor.classList.contains('campo-fecha')) {
      return;
    }
    var envoltura = document.createElement('div');
    envoltura.className = 'campo-fecha';
    contenedor.insertBefore(envoltura, campo);
    envoltura.appendChild(campo);
    envoltura.appendChild(crearBoton(campo));
    campo.dataset.calendarioListo = 'si';
  }

  function iniciar() {
    var campos = document.querySelectorAll('input[type="date"]');
    for (var i = 0; i < campos.length; i += 1) {
      mejorarCampo(campos[i]);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
