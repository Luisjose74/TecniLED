// =========================================================
// JAVASCRIPT DE LA TIENDA TECNILED (solo comportamiento visual)
// Cada función se llama desde un onclick="..." en las plantillas.
// =========================================================

// ---------- 1. MENÚ DE CELULAR ----------
function toggleMenuMovil() {
  var menu = document.getElementById('menu-movil');
  var abrir = document.getElementById('icono-menu-abrir');
  var cerrar = document.getElementById('icono-menu-cerrar');
  if (!menu || !abrir || !cerrar) return;
  menu.classList.toggle('hidden');
  // Cambia el ícono: hamburguesa ↔ X
  abrir.classList.toggle('hidden');
  cerrar.classList.toggle('hidden');
}


// ---------- 2. CARRITO LATERAL ----------
function abrirCarrito() {
  var carrito = document.getElementById('carrito');
  var fondo = document.getElementById('carrito-fondo');
  if (!carrito || !fondo) return;
  carrito.classList.add('abierto');
  fondo.classList.remove('hidden');
  document.body.style.overflow = 'hidden';   // evita que la página de atrás haga scroll
}

function cerrarCarrito() {
  var carrito = document.getElementById('carrito');
  var fondo = document.getElementById('carrito-fondo');
  if (!carrito || !fondo) return;
  carrito.classList.remove('abierto');
  fondo.classList.add('hidden');
  document.body.style.overflow = '';
}

// Cerrar el carrito con la tecla Escape
document.addEventListener('keydown', function (evento) {
  if (evento.key === 'Escape') {
    cerrarCarrito();
  }
});


// ---------- 3. ACCESIBILIDAD ----------
function mostrarPanelAccesibilidad(mostrar) {
  var panel = document.getElementById('panel-accesibilidad');
  var boton = document.getElementById('boton-accesibilidad');
  if (!panel) return;

  panel.classList.toggle('hidden', !mostrar);
  if (boton) boton.setAttribute('aria-expanded', mostrar ? 'true' : 'false');

  if (mostrar) {
    var primero = panel.querySelector('button');
    if (primero) primero.focus();
  } else if (boton && panel.contains(document.activeElement)) {
    boton.focus();
  }
}

function toggleAccesibilidad() {
  var panel = document.getElementById('panel-accesibilidad');
  if (!panel) return;
  mostrarPanelAccesibilidad(panel.classList.contains('hidden'));
}

// Cerrar el panel si se hace clic fuera de él
document.addEventListener('click', function (evento) {
  var contenedor = document.getElementById('accesibilidad');
  if (contenedor && !contenedor.contains(evento.target)) {
    mostrarPanelAccesibilidad(false);
  }
});

// Cerrar el panel de accesibilidad con Escape
document.addEventListener('keydown', function (evento) {
  if (evento.key === 'Escape') {
    mostrarPanelAccesibilidad(false);
  }
});

// Modo oscuro / claro (usa la misma clave "theme" que el panel admin)
function cambiarTema() {
  var html = document.documentElement;
  html.classList.toggle('dark');
  if (html.classList.contains('dark')) {
    localStorage.setItem('theme', 'dark');
  } else {
    localStorage.setItem('theme', 'light');
  }
}

// Tamaño de letra: entre 80% y 130%, de 10 en 10
function cambiarTamanoLetra(cambio) {
  var actual = parseInt(localStorage.getItem('fontSize')) || 100;
  var nuevo = actual + cambio;
  if (nuevo < 80) { nuevo = 80; }
  if (nuevo > 130) { nuevo = 130; }

  document.documentElement.style.fontSize = nuevo + '%';
  localStorage.setItem('fontSize', nuevo);
  mostrarTamanoLetra();
}

function mostrarTamanoLetra() {
  var texto = document.getElementById('texto-tamano-letra');
  if (texto) {
    texto.textContent = (localStorage.getItem('fontSize') || 100) + '%';
  }
}

// Alto contraste
function cambiarContraste() {
  var html = document.documentElement;
  html.classList.toggle('alto-contraste');
  if (html.classList.contains('alto-contraste')) {
    localStorage.setItem('contraste', 'alto');
  } else {
    localStorage.removeItem('contraste');
  }
}

// Volver todo a como estaba (menos el tema)
function restablecerAccesibilidad() {
  localStorage.removeItem('fontSize');
  localStorage.removeItem('contraste');
  document.documentElement.style.fontSize = '';
  document.documentElement.classList.remove('alto-contraste');
  mostrarTamanoLetra();
}


// ---------- 4. FORMULARIO DE CONTACTO (DEMO) ----------
// Todavía no hay backend: solo muestra un aviso y limpia el formulario.
function enviarContactoDemo(formulario) {
  alert('¡Gracias! Tu mensaje fue enviado. Pronto un asesor se comunicará contigo.');
  formulario.reset();
  return false;   // "false" evita que la página se recargue
}


// ---------- 5. ANIMACIONES AL HACER SCROLL ----------
// IntersectionObserver "vigila" los elementos y avisa cuando entran en pantalla.
function iniciarAnimaciones() {
  var elementos = document.querySelectorAll('[data-aparecer]');

  // Si el navegador es muy viejo, se muestran todos de una vez
  if (!('IntersectionObserver' in window)) {
    elementos.forEach(function (el) { el.classList.add('visible'); });
    return;
  }

  var observador = new IntersectionObserver(function (entradas) {
    entradas.forEach(function (entrada) {
      if (entrada.isIntersecting) {
        entrada.target.classList.add('visible');
        observador.unobserve(entrada.target);   // solo se anima una vez
      }
    });
  }, { threshold: 0.15 });

  elementos.forEach(function (el) { observador.observe(el); });
}


// ---------- 6. CONTADORES DEL HERO ----------
// Sube el número desde 0 hasta el valor de data-contador en 1.5 segundos.
function iniciarContadores() {
  var contadores = document.querySelectorAll('[data-contador]');

  contadores.forEach(function (contador) {
    var final = parseInt(contador.getAttribute('data-contador'));
    var duracion = 1500;
    var inicio = null;

    function paso(tiempo) {
      if (inicio === null) { inicio = tiempo; }
      var progreso = Math.min((tiempo - inicio) / duracion, 1);
      contador.textContent = Math.round(final * progreso);
      if (progreso < 1) {
        requestAnimationFrame(paso);
      }
    }
    requestAnimationFrame(paso);
  });
}


// ---------- 7. MENSAJES DE DJANGO: se ocultan solos a los 5 segundos ----------
function ocultarMensajes() {
  setTimeout(function () {
    document.querySelectorAll('.mensaje-flotante').forEach(function (mensaje) {
      mensaje.remove();
    });
  }, 5000);
}


// Cuando la página termina de cargar, se arranca todo
document.addEventListener('DOMContentLoaded', function () {
  mostrarTamanoLetra();
  iniciarAnimaciones();
  iniciarContadores();
  ocultarMensajes();
});