"""G1-308: pruebas del doble factor de autenticación (código por correo).

Cubre: envío del código, verificación, código incorrecto/vencido/usado,
límite de intentos y "confiar en este dispositivo" (cookie firmada).
"""
import re
import time
from datetime import timedelta
from unittest.mock import patch

from django.core import signing
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Usuarios.models import CodigoRecuperacion, Usuario
from Usuarios.views import (
    DIAS_DISPOSITIVO_CONFIABLE,
    SAL_DISPOSITIVO,
    nombre_cookie_dispositivo,
)

CLAVE = 'Prueba123!'

# MD5 solo en pruebas: hace los tests mucho más rápidos.
HASHER_RAPIDO = ['django.contrib.auth.hashers.MD5PasswordHasher']


def codigo_enviado(envio):
    """Saca el código de 6 dígitos del correo que la vista intentó enviar."""
    mensaje = envio.call_args.kwargs['message']
    return re.search(r'es: (\d{6})', mensaje).group(1)


@override_settings(PASSWORD_HASHERS=HASHER_RAPIDO)
class DobleFactorBase(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username='dos@test.com', email='dos@test.com',
            password=CLAVE, rol=Usuario.Rol.CLIENTE,
        )

    def paso_uno(self, correo='dos@test.com', clave=CLAVE, cliente=None):
        """Envía el login. Devuelve (respuesta, mock de send_mail)."""
        cliente = cliente or self.client
        with patch('Usuarios.views.send_mail') as envio:
            resp = cliente.post(reverse('login'), {'correo': correo, 'contrasena': clave})
        return resp, envio

    def paso_dos(self, codigo, confiar=False, cliente=None):
        datos = {'codigo': codigo}
        if confiar:
            datos['confiar'] = 'on'
        return (cliente or self.client).post(reverse('verificar_codigo'), datos)

    def login_completo(self, confiar=False, cliente=None):
        """Hace los dos pasos con código correcto."""
        resp, envio = self.paso_uno(cliente=cliente)
        return self.paso_dos(codigo_enviado(envio), confiar=confiar, cliente=cliente)


class EnvioDelCodigoTests(DobleFactorBase):
    def test_login_correcto_envia_codigo_y_redirige_a_verificacion(self):
        resp, envio = self.paso_uno()
        self.assertRedirects(resp, reverse('verificar_codigo'), fetch_redirect_response=False)
        envio.assert_called_once()
        self.assertEqual(envio.call_args.kwargs['recipient_list'], ['dos@test.com'])

    def test_login_correcto_todavia_no_inicia_sesion(self):
        self.paso_uno()
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session['doble_factor_usuario_id'], self.usuario.pk)

    def test_se_guarda_un_codigo_de_doble_factor_sin_guardarlo_en_claro(self):
        resp, envio = self.paso_uno()
        registro = CodigoRecuperacion.objects.get(usuario=self.usuario)
        self.assertEqual(registro.proposito, CodigoRecuperacion.Proposito.DOBLE_FACTOR)
        self.assertNotEqual(registro.codigo_hash, codigo_enviado(envio))

    def test_contrasena_incorrecta_no_envia_codigo_y_cuenta_el_intento(self):
        resp, envio = self.paso_uno(clave='mala')
        envio.assert_not_called()
        self.assertContains(resp, 'Credenciales incorrectas')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.intentos_fallidos, 1)

    def test_tres_contrasenas_malas_siguen_bloqueando_la_cuenta(self):
        for _ in range(3):
            self.paso_uno(clave='mala')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.estado_cuenta, Usuario.EstadoCuenta.BLOQUEADA)

    def test_cuenta_bloqueada_no_recibe_codigo_ni_con_clave_correcta(self):
        self.usuario.estado_cuenta = Usuario.EstadoCuenta.BLOQUEADA
        self.usuario.save()
        resp, envio = self.paso_uno()
        envio.assert_not_called()
        self.assertContains(resp, 'bloqueada')

    def test_cuenta_suspendida_no_recibe_codigo(self):
        self.usuario.estado_cuenta = Usuario.EstadoCuenta.SUSPENDIDA
        self.usuario.save()
        resp, envio = self.paso_uno()
        envio.assert_not_called()
        self.assertContains(resp, 'suspendida')

    def test_el_codigo_se_pide_a_todos_los_roles(self):
        for rol in Usuario.Rol.values:
            with self.subTest(rol=rol):
                Usuario.objects.create_user(
                    username=f'{rol}@test.com', email=f'{rol}@test.com',
                    password=CLAVE, rol=rol,
                )
                resp, envio = self.paso_uno(correo=f'{rol}@test.com', cliente=Client())
                self.assertRedirects(
                    resp, reverse('verificar_codigo'), fetch_redirect_response=False
                )
                envio.assert_called_once()


class VerificacionDelCodigoTests(DobleFactorBase):
    def test_sin_login_previo_redirige_al_login(self):
        resp = self.client.get(reverse('verificar_codigo'))
        self.assertRedirects(resp, reverse('login'), fetch_redirect_response=False)

    def test_pantalla_de_verificacion_se_muestra_tras_el_login(self):
        self.paso_uno()
        resp = self.client.get(reverse('verificar_codigo'))
        self.assertEqual(resp.status_code, 200)

    def test_usuario_con_sesion_iniciada_va_al_inicio(self):
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse('verificar_codigo'))
        self.assertRedirects(resp, reverse('inicio'), fetch_redirect_response=False)

    def test_codigo_correcto_inicia_sesion(self):
        resp = self.login_completo()
        self.assertRedirects(resp, reverse('inicio'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.usuario.pk)
        self.assertNotIn('doble_factor_usuario_id', self.client.session)

    def test_codigo_correcto_queda_marcado_como_usado(self):
        self.login_completo()
        self.assertTrue(CodigoRecuperacion.objects.get(usuario=self.usuario).usado)

    def test_codigo_incorrecto_no_inicia_sesion_y_cuenta_el_intento(self):
        resp, envio = self.paso_uno()
        correcto = codigo_enviado(envio)
        incorrecto = '000000' if correcto != '000000' else '111111'
        resp = self.paso_dos(incorrecto)
        self.assertContains(resp, 'Código incorrecto o vencido')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(CodigoRecuperacion.objects.get(usuario=self.usuario).intentos, 1)

    def test_codigo_con_formato_invalido_no_inicia_sesion(self):
        self.paso_uno()
        for malo in ('abc123', '12345', '1234567'):
            with self.subTest(codigo=malo):
                resp = self.paso_dos(malo)
                self.assertEqual(resp.status_code, 200)
                self.assertNotIn('_auth_user_id', self.client.session)

    def test_codigo_vencido_es_rechazado(self):
        resp, envio = self.paso_uno()
        registro = CodigoRecuperacion.objects.get(usuario=self.usuario)
        registro.expira_en = timezone.now() - timedelta(minutes=1)
        registro.save()
        resp = self.paso_dos(codigo_enviado(envio))
        self.assertContains(resp, 'Código incorrecto o vencido')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_codigo_ya_usado_no_se_puede_reutilizar(self):
        resp, envio = self.paso_uno()
        registro = CodigoRecuperacion.objects.get(usuario=self.usuario)
        registro.marcar_usado()
        resp = self.paso_dos(codigo_enviado(envio))
        self.assertContains(resp, 'Código incorrecto o vencido')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_tras_5_intentos_fallidos_ni_el_codigo_correcto_sirve(self):
        resp, envio = self.paso_uno()
        correcto = codigo_enviado(envio)
        incorrecto = '000000' if correcto != '000000' else '111111'
        for _ in range(CodigoRecuperacion.MAX_INTENTOS):
            self.paso_dos(incorrecto)
        resp = self.paso_dos(correcto)
        self.assertContains(resp, 'Código incorrecto o vencido')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_cuenta_bloqueada_entre_los_dos_pasos_no_puede_verificar(self):
        self.paso_uno()
        self.usuario.estado_cuenta = Usuario.EstadoCuenta.BLOQUEADA
        self.usuario.save()
        resp = self.client.get(reverse('verificar_codigo'))
        self.assertRedirects(resp, reverse('login'), fetch_redirect_response=False)

    def test_un_codigo_nuevo_invalida_el_anterior(self):
        resp, envio1 = self.paso_uno()
        primero = codigo_enviado(envio1)
        resp, envio2 = self.paso_uno()
        segundo = codigo_enviado(envio2)
        if primero == segundo:  # 1 en un millón: el mismo código se repitió
            self.skipTest('El código se repitió por azar')
        resp = self.paso_dos(primero)
        self.assertContains(resp, 'Código incorrecto o vencido')
        resp = self.paso_dos(segundo)
        self.assertRedirects(resp, reverse('inicio'), fetch_redirect_response=False)


class DispositivoDeConfianzaTests(DobleFactorBase):
    def nombre_cookie(self):
        return nombre_cookie_dispositivo(self.usuario)

    def test_sin_marcar_la_casilla_no_se_guarda_cookie(self):
        resp = self.login_completo(confiar=False)
        self.assertNotIn(self.nombre_cookie(), resp.cookies)

    def test_marcando_la_casilla_se_guarda_cookie_firmada_de_365_dias(self):
        resp = self.login_completo(confiar=True)
        cookie = resp.cookies[self.nombre_cookie()]
        self.assertEqual(int(cookie['max-age']), DIAS_DISPOSITIVO_CONFIABLE * 24 * 60 * 60)
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        # firmada: el valor no es el id a secas
        self.assertNotEqual(cookie.value, str(self.usuario.pk))

    def test_dispositivo_de_confianza_salta_el_codigo(self):
        self.login_completo(confiar=True)
        self.client.get(reverse('logout'))
        resp, envio = self.paso_uno()
        self.assertRedirects(resp, reverse('inicio'), fetch_redirect_response=False)
        envio.assert_not_called()
        self.assertEqual(int(self.client.session['_auth_user_id']), self.usuario.pk)

    def test_dispositivo_de_confianza_sigue_pidiendo_la_contrasena(self):
        self.login_completo(confiar=True)
        self.client.get(reverse('logout'))
        resp, envio = self.paso_uno(clave='mala')
        envio.assert_not_called()
        self.assertContains(resp, 'Credenciales incorrectas')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_dispositivo_de_confianza_sigue_contando_intentos_y_bloqueando(self):
        self.login_completo(confiar=True)
        self.client.get(reverse('logout'))
        for _ in range(3):
            self.paso_uno(clave='mala')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.estado_cuenta, Usuario.EstadoCuenta.BLOQUEADA)

    def test_dispositivo_de_confianza_no_salta_el_bloqueo(self):
        self.login_completo(confiar=True)
        self.client.get(reverse('logout'))
        self.usuario.estado_cuenta = Usuario.EstadoCuenta.BLOQUEADA
        self.usuario.save()
        resp, envio = self.paso_uno()
        self.assertContains(resp, 'bloqueada')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_otro_navegador_vuelve_a_pedir_el_codigo(self):
        self.login_completo(confiar=True)
        incognito = Client()
        resp, envio = self.paso_uno(cliente=incognito)
        self.assertRedirects(resp, reverse('verificar_codigo'), fetch_redirect_response=False)
        envio.assert_called_once()

    def test_la_confianza_es_por_usuario_en_el_mismo_navegador(self):
        self.login_completo(confiar=True)
        self.client.get(reverse('logout'))
        Usuario.objects.create_user(
            username='otro@test.com', email='otro@test.com',
            password=CLAVE, rol=Usuario.Rol.CLIENTE,
        )
        resp, envio = self.paso_uno(correo='otro@test.com')
        self.assertRedirects(resp, reverse('verificar_codigo'), fetch_redirect_response=False)
        envio.assert_called_once()

    def test_cookie_falsificada_no_sirve(self):
        self.client.cookies[self.nombre_cookie()] = 'valor-falso'
        resp, envio = self.paso_uno()
        self.assertRedirects(resp, reverse('verificar_codigo'), fetch_redirect_response=False)
        envio.assert_called_once()

    def test_cookie_firmada_con_el_id_de_otro_usuario_no_sirve(self):
        nombre = self.nombre_cookie()
        firmador = signing.get_cookie_signer(salt=nombre + SAL_DISPOSITIVO)
        self.client.cookies[nombre] = firmador.sign(str(self.usuario.pk + 999))
        resp, envio = self.paso_uno()
        self.assertRedirects(resp, reverse('verificar_codigo'), fetch_redirect_response=False)
        envio.assert_called_once()

    def test_cookie_vencida_no_sirve(self):
        nombre = self.nombre_cookie()
        firmador = signing.get_cookie_signer(salt=nombre + SAL_DISPOSITIVO)
        self.client.cookies[nombre] = firmador.sign(str(self.usuario.pk))
        vencimiento = DIAS_DISPOSITIVO_CONFIABLE * 24 * 60 * 60 + 60
        with patch('django.core.signing.time.time', return_value=time.time() + vencimiento):
            resp, envio = self.paso_uno()
        self.assertRedirects(resp, reverse('verificar_codigo'), fetch_redirect_response=False)


class PropositoDelCodigoTests(DobleFactorBase):
    def test_codigo_de_doble_factor_no_invalida_el_de_recuperacion(self):
        rec, _ = CodigoRecuperacion.generar(self.usuario)
        CodigoRecuperacion.generar(self.usuario, CodigoRecuperacion.Proposito.DOBLE_FACTOR)
        self.assertEqual(CodigoRecuperacion.ultimo_vigente(self.usuario), rec)

    def test_ultimo_vigente_filtra_por_proposito(self):
        DF = CodigoRecuperacion.Proposito.DOBLE_FACTOR
        self.assertIsNone(CodigoRecuperacion.ultimo_vigente(self.usuario, DF))
        df, _ = CodigoRecuperacion.generar(self.usuario, DF)
        self.assertEqual(CodigoRecuperacion.ultimo_vigente(self.usuario, DF), df)
        self.assertIsNone(CodigoRecuperacion.ultimo_vigente(self.usuario))