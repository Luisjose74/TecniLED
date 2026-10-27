// =========================================================
// MODAL DE CONFIRMACIÓN REUTILIZABLE (G1-1216)
// Uso en cualquier plantilla del panel:
//   <form method="post" action="..." data-confirmar="¿Seguro que quieres...?">
// Al enviar el formulario aparece el modal; solo se envía si el usuario acepta.
// =========================================================

// Aquí se guarda el formulario que está esperando confirmación
var formularioPendiente = null;

function abrirConfirmacion(formulario) {
  formularioPendiente = formulario;
  document.getElementById('confirmacion-texto').textContent = formulario.dataset.confirmar;

  var modal = document.getElementById('modal-confirmacion');
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  document.getElementById('confirmacion-aceptar').focus();
}

function cerrarConfirmacion() {
  var modal = document.getElementById('modal-confirmacion');
  modal.classList.add('hidden');
  modal.classList.remove('flex');
  formularioPendiente = null;
}

function aceptarConfirmacion() {
  var formulario = formularioPendiente;
  cerrarConfirmacion();
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

// La tecla Escape cierra el modal sin hacer nada
document.addEventListener('keydown', function (evento) {
  if (evento.key === 'Escape') {
    cerrarConfirmacion();
  }
});