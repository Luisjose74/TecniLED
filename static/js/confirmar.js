// =========================================================
// MODAL DE CONFIRMACIÓN REUTILIZABLE (G1-1216)
// Uso en cualquier plantilla del panel:
//   <form method="post" action="..." data-confirmar="¿Seguro que quieres...?">
// Al enviar el formulario aparece el modal; solo se envía si el usuario acepta.
// Accesibilidad: atrapa el foco dentro del diálogo, Escape cancela y al cerrar
// se devuelve el foco al elemento que abrió el modal.
// =========================================================

// Aquí se guarda el formulario que está esperando confirmación
var formularioPendiente = null;
// Elemento que tenía el foco antes de abrir el modal
var focoAnterior = null;

function modalConfirmacion() {
  return document.getElementById('modal-confirmacion');
}

function abrirConfirmacion(formulario) {
  var modal = modalConfirmacion();
  if (!modal) return;

  formularioPendiente = formulario;
  focoAnterior = document.activeElement;
  document.getElementById('confirmacion-texto').textContent = formulario.dataset.confirmar;

  modal.classList.remove('hidden');
  modal.classList.add('flex');
  document.getElementById('confirmacion-aceptar').focus();
}

function cerrarConfirmacion(devolverFoco) {
  var modal = modalConfirmacion();
  if (!modal || modal.classList.contains('hidden')) return;

  modal.classList.add('hidden');
  modal.classList.remove('flex');
  formularioPendiente = null;

  if (devolverFoco !== false && focoAnterior && typeof focoAnterior.focus === 'function') {
    focoAnterior.focus();
  }
  focoAnterior = null;
}

function aceptarConfirmacion() {
  var formulario = formularioPendiente;
  cerrarConfirmacion(false);
  if (formulario) {
    // submit() envía el formulario sin volver a abrir el modal
    formulario.submit();
  }
}

// Cuando se envía un formulario con data-confirmar, primero se pregunta
document.addEventListener('submit', function (evento) {
  var formulario = evento.target;
  if (formulario.dataset.confirmar) {
    evento.preventDefault();
    abrirConfirmacion(formulario);
  }
});

// Escape cancela y Tab se queda dentro del diálogo
document.addEventListener('keydown', function (evento) {
  var modal = modalConfirmacion();
  if (!modal || modal.classList.contains('hidden')) return;

  if (evento.key === 'Escape') {
    evento.preventDefault();
    cerrarConfirmacion();
    return;
  }

  if (evento.key !== 'Tab') return;

  var enfocables = modal.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  if (!enfocables.length) return;

  var primero = enfocables[0];
  var ultimo = enfocables[enfocables.length - 1];

  if (evento.shiftKey && document.activeElement === primero) {
    evento.preventDefault();
    ultimo.focus();
  } else if (!evento.shiftKey && document.activeElement === ultimo) {
    evento.preventDefault();
    primero.focus();
  }
});

// Clic en el fondo oscuro: se cierra sin confirmar
document.addEventListener('click', function (evento) {
  var modal = modalConfirmacion();
  if (modal && evento.target === modal) {
    cerrarConfirmacion();
  }
});
