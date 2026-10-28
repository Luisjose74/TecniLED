// Chrome y Edge rellenan las credenciales guardadas al abrir el login, aunque
// el formulario pida autocomplete="off". Eso deja el correo y la contraseña del
// usuario anterior a la vista en un equipo compartido.
//
// Aquí vaciamos los campos en la primera carga de la página. Si la persona
// elige una credencial a propósito desde el gestor de contraseñas, ese relleno
// ocurre después de su clic y no se toca.
(function () {
  var correo = document.getElementById('login-correo');
  var contrasena = document.getElementById('login-contrasena');
  if (!correo || !contrasena) return;

  var interactuo = false;

  function marcarInteraccion() {
    interactuo = true;
  }

  ['keydown', 'pointerdown'].forEach(function (evento) {
    correo.addEventListener(evento, marcarInteraccion);
    contrasena.addEventListener(evento, marcarInteraccion);
  });

  function vaciar() {
    if (interactuo) return;
    correo.value = '';
    contrasena.value = '';
  }

  // El navegador puede rellenar un instante después de load; se revisa varias
  // veces durante el primer medio segundo.
  window.addEventListener('load', function () {
    vaciar();
    setTimeout(vaciar, 150);
    setTimeout(vaciar, 500);
  });

  // Al volver con atrás/adelante el navegador puede restaurar los valores.
  window.addEventListener('pageshow', function (evento) {
    if (evento.persisted) {
      interactuo = false;
      vaciar();
    }
  });
})();
