from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from Usuarios.models import Usuario

from .models import Notificacion


def crear_usuario(email='cliente@test.com', rol=Usuario.Rol.CLIENTE, **extra):
    datos = {
        'username': email,
        'email': email,
        'password': 'Prueba123!',
        'first_name': 'Cliente',
        'last_name': 'Prueba',
        'rol': rol,
    }
    datos.update(extra)
    return Usuario.objects.create_user(**datos)


class NotificacionModeloTests(TestCase):
    def setUp(self):
        self.usuario = crear_usuario()

    def test_valores_por_defecto(self):
        notificacion = Notificacion.objects.create(
            destinatario=self.usuario,
            mensaje='Mensaje de prueba',
        )
        self.assertFalse(notificacion.leido)
        self.assertEqual(notificacion.tipo, Notificacion.Tipo.GENERAL)
        self.assertEqual(notificacion.canal, Notificacion.Canal.INTERNA)
        self.assertIsNotNone(notificacion.fecha_envio)

    def test_marcar_leida(self):
        notificacion = Notificacion.objects.create(
            destinatario=self.usuario,
            mensaje='Mensaje de prueba',
        )
        notificacion.marcar_leida()
        notificacion.refresh_from_db()
        self.assertTrue(notificacion.leido)


class BloqueoDeCuentaNotificacionTests(TestCase):
    """G1-197: alerta al usuario cuando su cuenta queda bloqueada."""

    def setUp(self):
        self.usuario = crear_usuario(email='bloqueo@test.com')

    @patch('notificaciones.services.send_mail')
    def test_bloqueo_crea_notificacion_y_envia_correo(self, enviar_correo):
        self.usuario.intentos_fallidos = Usuario.MAX_INTENTOS
        self.usuario.estado_cuenta = Usuario.EstadoCuenta.BLOQUEADA
        self.usuario.save()

        notificacion = Notificacion.objects.get(destinatario=self.usuario)
        self.assertEqual(notificacion.tipo, Notificacion.Tipo.BLOQUEO_CUENTA)
        self.assertEqual(notificacion.canal, Notificacion.Canal.CORREO)
        self.assertIn('bloqueada', notificacion.mensaje)
        self.assertIn(str(Usuario.MAX_INTENTOS), notificacion.mensaje)
        enviar_correo.assert_called_once()
        self.assertEqual(enviar_correo.call_args.args[3], [self.usuario.email])

    @patch('notificaciones.services.send_mail')
    def test_guardados_posteriores_no_duplican_la_notificacion(self, _correo):
        self.usuario.estado_cuenta = Usuario.EstadoCuenta.BLOQUEADA
        self.usuario.save()
        self.usuario.save()
        self.usuario.save()

        self.assertEqual(
            Notificacion.objects.filter(
                destinatario=self.usuario,
                tipo=Notificacion.Tipo.BLOQUEO_CUENTA,
            ).count(),
            1,
        )

    def test_reactivar_la_cuenta_no_crea_notificacion(self):
        self.usuario.estado_cuenta = Usuario.EstadoCuenta.ACTIVA
        self.usuario.save()

        self.assertFalse(
            Notificacion.objects.filter(
                destinatario=self.usuario,
                tipo=Notificacion.Tipo.BLOQUEO_CUENTA,
            ).exists()
        )

    @patch('notificaciones.services.send_mail')
    def test_tres_intentos_fallidos_en_login_generan_la_alerta(self, _correo):
        for _ in range(Usuario.MAX_INTENTOS):
            self.client.post(
                reverse('login'),
                {'correo': self.usuario.email, 'contrasena': 'incorrecta'},
            )

        self.usuario.refresh_from_db()
        self.assertEqual(
            self.usuario.estado_cuenta, Usuario.EstadoCuenta.BLOQUEADA
        )
        self.assertTrue(
            Notificacion.objects.filter(
                destinatario=self.usuario,
                tipo=Notificacion.Tipo.BLOQUEO_CUENTA,
            ).exists()
        )


class NotificacionesVistasTests(TestCase):
    def setUp(self):
        self.usuario = crear_usuario(email='uno@test.com')
        self.otro = crear_usuario(email='dos@test.com')

        self.propia = Notificacion.objects.create(
            destinatario=self.usuario,
            tipo=Notificacion.Tipo.SEGURIDAD,
            mensaje='Notificación propia',
        )
        self.ajena = Notificacion.objects.create(
            destinatario=self.otro,
            mensaje='Notificación ajena',
        )

    def test_lista_requiere_inicio_de_sesion(self):
        respuesta = self.client.get(reverse('notificaciones_lista'))
        self.assertEqual(respuesta.status_code, 302)

    def test_lista_solo_muestra_notificaciones_propias(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse('notificaciones_lista'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Notificación propia')
        self.assertNotContains(respuesta, 'Notificación ajena')

    def test_cliente_usa_plantilla_de_tienda(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse('notificaciones_lista'))

        self.assertTemplateUsed(respuesta, 'notificaciones/lista.html')
        self.assertTemplateNotUsed(respuesta, 'notificaciones/lista_admin.html')

    def test_administrador_usa_plantilla_del_panel(self):
        admin = crear_usuario(
            email='admin@test.com', rol=Usuario.Rol.ADMINISTRADOR
        )
        self.client.force_login(admin)
        respuesta = self.client.get(reverse('notificaciones_lista'))

        self.assertTemplateUsed(respuesta, 'notificaciones/lista_admin.html')
        self.assertTemplateNotUsed(respuesta, 'notificaciones/lista.html')

    def test_marcar_una_notificacion_propia(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse('notificacion_marcar_leida', args=[self.propia.pk])
        )

        self.assertRedirects(respuesta, reverse('notificaciones_lista'))
        self.propia.refresh_from_db()
        self.assertTrue(self.propia.leido)

    def test_no_puede_marcar_una_notificacion_ajena(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse('notificacion_marcar_leida', args=[self.ajena.pk])
        )

        self.assertEqual(respuesta.status_code, 404)
        self.ajena.refresh_from_db()
        self.assertFalse(self.ajena.leido)

    def test_marcar_todas_solo_afecta_al_usuario(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse('notificaciones_marcar_todas'))

        self.assertRedirects(respuesta, reverse('notificaciones_lista'))
        self.propia.refresh_from_db()
        self.ajena.refresh_from_db()
        self.assertTrue(self.propia.leido)
        self.assertFalse(self.ajena.leido)

    def test_marcar_todas_solo_acepta_post(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse('notificaciones_marcar_todas'))
        self.assertEqual(respuesta.status_code, 405)

    def test_context_processor_deja_el_contador(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse('inicio'))

        self.assertEqual(respuesta.context['notificaciones_sin_leer'], 1)
        self.assertEqual(len(respuesta.context['ultimas_notificaciones']), 1)

    def test_campana_muestra_el_contador_de_sin_leer(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse('inicio'))

        self.assertContains(respuesta, 'Notificaciones: 1 sin leer')

    def test_context_processor_no_falla_sin_sesion(self):
        respuesta = self.client.get(reverse('inicio'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('notificaciones_sin_leer', respuesta.context)
