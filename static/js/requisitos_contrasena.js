// Marca en vivo qué requisitos de contraseña se van cumpliendo y avisa si la
// confirmación no coincide. Se usa en el formulario de "Nuevo usuario".
(function () {
  var campo = document.getElementById('id_contrasena');
  var confirmacion = document.getElementById('id_contrasena2');
  var lista = document.getElementById('requisitos-contrasena');
  var aviso = document.getElementById('coincidencia-contrasena');
  if (!campo || !lista) return;

  var reglas = {
    longitud: function (valor) { return valor.length >= 8; },
    mayuscula: function (valor) { return /[A-Z]/.test(valor); },
    minuscula: function (valor) { return /[a-z]/.test(valor); },
    numero: function (valor) { return /[0-9]/.test(valor); },
    simbolo: function (valor) { return /[^A-Za-z0-9]/.test(valor); }
  };

  function pintarRequisitos() {
    var valor = campo.value;
    Object.keys(reglas).forEach(function (clave) {
      var item = lista.querySelector('[data-requisito="' + clave + '"]');
      if (!item) return;
      var cumplido = reglas[clave](valor);
      item.classList.toggle('text-emerald-600', cumplido);
      item.classList.toggle('dark:text-emerald-400', cumplido);
      item.classList.toggle('text-gray-500', !cumplido);
      item.classList.toggle('dark:text-gray-400', !cumplido);
      var marca = item.querySelector('.requisito-marca');
      if (marca) marca.textContent = cumplido ? '✓' : '○';
      var estado = item.querySelector('.requisito-estado');
      if (estado) estado.textContent = cumplido ? 'cumplido' : 'pendiente';
    });
  }

  function revisarCoincidencia() {
    if (!confirmacion) return;
    var vacia = confirmacion.value === '';
    var iguales = !vacia && campo.value === confirmacion.value;

    if (vacia) {
      confirmacion.setCustomValidity('');
    } else if (iguales) {
      confirmacion.setCustomValidity('');
    } else {
      confirmacion.setCustomValidity('Las contraseñas no coinciden.');
    }

    if (!aviso) return;
    if (vacia) {
      aviso.textContent = '';
      aviso.className = 'text-xs mt-1';
    } else if (iguales) {
      aviso.textContent = 'Las contraseñas coinciden.';
      aviso.className = 'text-xs mt-1 text-emerald-600 dark:text-emerald-400';
    } else {
      aviso.textContent = 'Las contraseñas no coinciden.';
      aviso.className = 'text-xs mt-1 text-red-500';
    }
  }

  campo.addEventListener('input', function () {
    pintarRequisitos();
    if (confirmacion && confirmacion.value !== '') revisarCoincidencia();
  });

  if (confirmacion) {
    confirmacion.addEventListener('input', revisarCoincidencia);

    // Refuerzo: si el navegador no soporta setCustomValidity con el submit,
    // el backend valida igual, pero evitamos el envío cuando ya se ve el error.
    var formulario = campo.form;
    if (formulario) {
      formulario.addEventListener('submit', function (evento) {
        if (confirmacion.value !== '' && campo.value !== confirmacion.value) {
          evento.preventDefault();
          confirmacion.focus();
        }
      });
    }
  }

  pintarRequisitos();
})();
