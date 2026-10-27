from django.test import TestCase
from django.urls import reverse

from Usuarios.models import Usuario
from .models import PreguntaFrecuente


class AyudaTests(TestCase):
    """G1-1197: módulo de ayuda con preguntas frecuentes y buscador."""

    def setUp(self):
        PreguntaFrecuente.objects.create(
            pregunta='¿Cómo recupero mi contraseña?',
            respuesta='En el login haz clic en "¿Olvidaste tu contraseña?".',
            categoria='cuenta',
        )
        PreguntaFrecuente.objects.create(
            pregunta='¿Cómo registro un proveedor?',
            respuesta='Entra a Proveedores y haz clic en Nuevo proveedor.',
            categoria='administracion',
        )
        PreguntaFrecuente.objects.create(
            pregunta='Pregunta vieja que ya no aplica',
            respuesta='Esta no se debe ver.',
            activa=False,
        )

    def test_pagina_de_ayuda_carga(self):
        resp = self.client.get(reverse('ayuda'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'ayuda/ayuda.html')

    def test_muestra_preguntas_activas(self):
        resp = self.client.get(reverse('ayuda'))
        self.assertContains(resp, '¿Cómo recupero mi contraseña?')
        self.assertContains(resp, '¿Cómo registro un proveedor?')

    def test_no_muestra_preguntas_inactivas(self):
        resp = self.client.get(reverse('ayuda'))
        self.assertNotContains(resp, 'Pregunta vieja que ya no aplica')

    def test_buscador_filtra_preguntas(self):
        resp = self.client.get(reverse('ayuda'), {'q': 'proveedor'})
        self.assertContains(resp, '¿Cómo registro un proveedor?')
        self.assertNotContains(resp, '¿Cómo recupero mi contraseña?')

    def test_buscador_sin_resultados(self):
        resp = self.client.get(reverse('ayuda'), {'q': 'xyz123'})
        self.assertContains(resp, 'No encontramos preguntas relacionadas')

    def test_cliente_ve_ayuda_en_la_tienda(self):
        resp = self.client.get(reverse('ayuda'))
        self.assertTemplateUsed(resp, 'base.html')

    def test_administrador_ve_ayuda_en_el_panel(self):
        admin = Usuario.objects.create_user(
            username='luis.silva@tecniled.com', email='luis.silva@tecniled.com',
            password='Prueba123!', rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.client.force_login(admin)
        resp = self.client.get(reverse('ayuda'))
        self.assertTemplateUsed(resp, 'admin_base.html')

    def test_encabezado_no_tiene_enlace_de_ayuda(self):
        resp = self.client.get(reverse('inicio'))
        self.assertNotContains(resp, '>Ayuda</span>')

    def test_enlace_ayuda_en_el_menu_lateral(self):
        admin = Usuario.objects.create_user(
            username='luis.silva@tecniled.com', email='luis.silva@tecniled.com',
            password='Prueba123!', rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.client.force_login(admin)
        resp = self.client.get(reverse('usuarios_lista'))
        self.assertContains(resp, 'href="' + reverse('ayuda') + '"')


    def test_boton_flotante_de_ayuda_en_la_pagina_principal(self):
        resp = self.client.get(reverse('inicio'))
        self.assertTemplateUsed(resp, 'partials/accesibilidad.html')
        self.assertContains(resp, 'aria-label="Ir a la ayuda y preguntas frecuentes"')