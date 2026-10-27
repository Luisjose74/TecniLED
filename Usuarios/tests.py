from datetime import timedelta
from django.core.serializers import python
from django.test import override_settings
from django.utils import timezone
from Usuarios.models import CodigoRecuperacion
from django.test import TestCase
from django.urls import reverse
from Usuarios.models import Usuario


class RolesYPermisosTests(TestCase):
    def crear(self, correo, rol):
        return Usuario.objects.create_user(
            username=correo, email=correo, password='Prueba123!', rol=rol
        )

    def recargar(self, usuario):
        # has_perm guarda una caché por instancia: volvemos a leer de la BD
        return Usuario.objects.get(pk=usuario.pk)

    def test_cliente_no_tiene_permisos_de_gestion(self):
        u = self.crear('cliente@test.com', Usuario.Rol.CLIENTE)
        self.assertFalse(u.has_perm('Usuarios.gestionar_usuarios'))
        self.assertFalse(u.has_perm('Usuarios.gestionar_inventario'))
        self.assertFalse(u.has_perm('Usuarios.gestionar_compras'))

    def test_control_inventario_solo_gestiona_inventario(self):
        u = self.crear('inv@test.com', Usuario.Rol.CONTROL_INVENTARIO)
        self.assertTrue(u.has_perm('Usuarios.gestionar_inventario'))
        self.assertFalse(u.has_perm('Usuarios.gestionar_usuarios'))

    def test_administrador_tiene_todos_los_permisos(self):
        u = self.crear('admin@test.com', Usuario.Rol.ADMINISTRADOR)
        self.assertTrue(u.has_perm('Usuarios.gestionar_usuarios'))
        self.assertTrue(u.has_perm('Usuarios.gestionar_inventario'))
        self.assertTrue(u.has_perm('Usuarios.gestionar_compras'))

    def test_cambiar_rol_actualiza_los_permisos(self):
        u = self.crear('cambio@test.com', Usuario.Rol.CLIENTE)
        u.rol = Usuario.Rol.CONTROL_INVENTARIO
        u.save()
        self.assertTrue(self.recargar(u).has_perm('Usuarios.gestionar_inventario'))
        u.rol = Usuario.Rol.CLIENTE
        u.save()
        self.assertFalse(self.recargar(u).has_perm('Usuarios.gestionar_inventario'))
        self.assertEqual(u.groups.count(), 1)


class UsuariosListaTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin_lista@test.com', email='admin_lista@test.com',
            password='Prueba123!', rol=Usuario.Rol.ADMINISTRADOR,
        )
        Usuario.objects.create_user(
            username='ana@test.com', email='ana@test.com', password='Prueba123!',
            first_name='Ana', last_name='Perez', documento='111', rol=Usuario.Rol.CLIENTE,
        )
        Usuario.objects.create_user(
            username='luis@test.com', email='luis@test.com', password='Prueba123!',
            first_name='Luis', last_name='Gomez', documento='222', rol=Usuario.Rol.CLIENTE,
        )

    def test_requiere_permiso_gestionar_usuarios(self):
        cliente = Usuario.objects.create_user(
            username='sinpermiso@test.com', email='sinpermiso@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE,
        )
        self.client.force_login(cliente)
        resp = self.client.get(reverse('usuarios_lista'))
        self.assertEqual(resp.status_code, 403)

    def test_busqueda_encuentra_por_nombre(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('usuarios_lista'), {'q': 'Ana'})
        self.assertContains(resp, 'ana@test.com')
        self.assertNotContains(resp, 'luis@test.com')

    def test_busqueda_sin_resultados_muestra_mensaje(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('usuarios_lista'), {'q': 'noexiste'})
        self.assertContains(resp, 'No se encontraron usuarios.')

    def test_paginacion_limita_a_10_por_pagina(self):
        for i in range(15):
            Usuario.objects.create_user(
                username=f'user{i}@test.com', email=f'user{i}@test.com',
                password='Prueba123!', rol=Usuario.Rol.CLIENTE,
            )
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('usuarios_lista'))
        self.assertEqual(len(resp.context['usuarios']), 10)


class CrearUsuarioInternoTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin_crear@test.com', email='admin_crear@test.com',
            password='Prueba123!', rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.client.force_login(self.admin)

    def datos_validos(self, **overrides):
        datos = {
            'first_name': 'Nueva', 'apellido': 'Cuenta', 'email': 'nueva@test.com',
            'documento': '999', 'telefono': '3000000000',
            'rol': Usuario.Rol.CONTROL_INVENTARIO, 'contrasena': 'Segura123!',
        }
        datos.update(overrides)
        return datos

    def test_crea_cuenta_con_rol_asignado(self):
        resp = self.client.post(reverse('crear_usuario'), self.datos_validos())
        self.assertRedirects(resp, reverse('usuarios_lista'))
        creado = Usuario.objects.get(email='nueva@test.com')
        self.assertEqual(creado.rol, Usuario.Rol.CONTROL_INVENTARIO)
        self.assertTrue(creado.check_password('Segura123!'))

    def test_correo_duplicado_no_crea_cuenta(self):
        Usuario.objects.create_user(username='dup@test.com', email='dup@test.com', password='Prueba123!')
        resp = self.client.post(reverse('crear_usuario'), self.datos_validos(email='dup@test.com'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Usuario.objects.filter(email='dup@test.com').count(), 1)

    def test_documento_duplicado_no_crea_cuenta(self):
        Usuario.objects.create_user(username='otro@test.com', email='otro@test.com',
                                     password='Prueba123!', documento='999')
        resp = self.client.post(reverse('crear_usuario'), self.datos_validos(email='nueva2@test.com'))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Usuario.objects.filter(email='nueva2@test.com').exists())

    def test_rol_invalido_manipulado_es_rechazado(self):
        resp = self.client.post(reverse('crear_usuario'), self.datos_validos(rol='hacker'))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Usuario.objects.filter(email='nueva@test.com').exists())

    def test_requiere_permiso_gestionar_usuarios(self):
        cliente = Usuario.objects.create_user(
            username='sinpermiso2@test.com', email='sinpermiso2@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE,
        )
        self.client.force_login(cliente)
        resp = self.client.get(reverse('crear_usuario'))
        self.assertEqual(resp.status_code, 403)


class EditarRolTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin_rol@test.com', email='admin_rol@test.com',
            password='Prueba123!', rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.usuario = Usuario.objects.create_user(
            username='cambia@test.com', email='cambia@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE,
        )

    def test_admin_cambia_rol_y_actualiza_permisos(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('editar_rol', args=[self.usuario.pk]),
            {'rol': Usuario.Rol.CONTROL_INVENTARIO, 'estado_cuenta': Usuario.EstadoCuenta.ACTIVA},
        )
        self.assertRedirects(resp, reverse('usuarios_lista'))
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.rol, Usuario.Rol.CONTROL_INVENTARIO)
        self.assertTrue(self.usuario.has_perm('Usuarios.gestionar_inventario'))

    def test_admin_no_puede_quitarse_su_propio_rol(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('editar_rol', args=[self.admin.pk]),
            {'rol': Usuario.Rol.CLIENTE, 'estado_cuenta': Usuario.EstadoCuenta.ACTIVA},
        )
        self.assertEqual(resp.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.rol, Usuario.Rol.ADMINISTRADOR)

    def test_usuario_sin_permiso_no_puede_modificar_rol_de_otro(self):
        self.client.force_login(self.usuario)
        otro = Usuario.objects.create_user(
            username='otro2@test.com', email='otro2@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE,
        )
        resp = self.client.get(reverse('editar_rol', args=[otro.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_funcionalidades_disponibles_cambian_segun_permiso(self):
        control = Usuario.objects.create_user(
            username='inv2@test.com', email='inv2@test.com',
            password='Prueba123!', rol=Usuario.Rol.CONTROL_INVENTARIO,
        )
        self.client.force_login(control)
        resp = self.client.get(reverse('usuarios_lista'))
        self.assertEqual(resp.status_code, 403)
        
class PlantillasBaseTests(TestCase):
    """G1-1190: las pantallas de administración usan admin_base.html."""

    def setUp(self):
        # Antes de cada prueba: crear un administrador e iniciar sesión
        self.admin = Usuario.objects.create_user(
            username='luis.silva@tecniled.com', email='luis.silva@tecniled.com',
            password='Prueba123!', first_name='Luis José', last_name='Silva Fajardo',
            rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.client.force_login(self.admin)

    def test_usuarios_lista_usa_admin_base(self):
        # 1) Abrir la página /usuarios/
        resp = self.client.get(reverse('usuarios_lista'))
        # 2) Debe usar la plantilla del panel...
        self.assertTemplateUsed(resp, 'admin_base.html')
        # 3) ...y NO la plantilla de la tienda
        self.assertTemplateNotUsed(resp, 'base.html')

    def test_usuarios_lista_muestra_titulo_y_miga(self):
        # 1) Abrir la página /usuarios/
        resp = self.client.get(reverse('usuarios_lista'))
        # 2) El título y la miga deben decir "Gestión de usuarios" (con tilde)
        self.assertContains(resp, 'Gestión de usuarios')
        
    def test_usuarios_crear_usa_admin_base(self):
        resp = self.client.get(reverse('crear_usuario'))
        self.assertTemplateUsed(resp, 'admin_base.html')
        self.assertTemplateNotUsed(resp, 'base.html')
        self.assertContains(resp, 'Nuevo usuario')
                
    def test_usuarios_editar_rol_usa_admin_base(self):
        # Usuaria a la que el administrador le va a editar el rol
        giselle = Usuario.objects.create_user(
            username='giselle.velasquez@tecniled.com', email='giselle.velasquez@tecniled.com',
            password='Prueba123!', first_name='Giselle Vanessa', last_name='Velásquez Albarracín',
            rol=Usuario.Rol.CONTROL_INVENTARIO,
        )
        
        # Abrir /usuarios/<id de Giselle>/editar-rol/
        resp = self.client.get(reverse('editar_rol', args=[giselle.pk]))
        # Debe usar la plantilla del panel y no la de la tienda
        self.assertTemplateUsed(resp, 'admin_base.html')
        self.assertTemplateNotUsed(resp, 'base.html')
        # La miga de pan debe decir "Editar usuario"
        self.assertContains(resp, 'Editar usuario')
        
    def test_menu_lateral_enlaza_a_proveedores(self):
        # El enlace "Proveedores" del menú lateral debe llevar a /proveedores/
        resp = self.client.get(reverse('usuarios_lista'))
        self.assertContains(resp, 'href="' + reverse('proveedores_lista') + '"')

    def test_proveedores_lista_usa_admin_base(self):
        # La página de proveedores abre bien desde el panel
        resp = self.client.get(reverse('proveedores_lista'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'admin_base.html')
                
    def test_menu_lateral_enlaza_a_respaldos(self):
        # Al administrador con permiso de respaldos le aparece "Copias de seguridad"
        from django.contrib.auth.models import Permission
        permiso = Permission.objects.get(codename='gestionar_respaldos')
        self.admin.user_permissions.add(permiso)
        resp = self.client.get(reverse('usuarios_lista'))
        self.assertContains(resp, 'href="' + reverse('respaldos_lista') + '"')
        self.assertContains(resp, 'Copias de seguridad')   
    
    def test_ruta_de_prueba_eliminada(self):
        # La página de prueba /productos/prueba/ ya no debe existir
        resp = self.client.get('/productos/prueba/')
        self.assertEqual(resp.status_code, 404)

    def test_tienda_usa_carpeta_partials(self):
        # La tienda arma su header y footer desde template/partials/
        resp = self.client.get(reverse('inicio'))
        self.assertTemplateUsed(resp, 'base.html')
        self.assertTemplateUsed(resp, 'partials/header.html')
        self.assertTemplateUsed(resp, 'partials/footer.html')
                
        
class BloqueoCuentaTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username='bloq@test.com', email='bloq@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE,
        )

    def intentar(self, clave):
        return self.client.post(reverse('login'), {'correo': 'bloq@test.com', 'contrasena': clave})

    def test_tres_fallos_bloquean_la_cuenta(self):
        for _ in range(3):
            self.intentar('mala')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.estado_cuenta, Usuario.EstadoCuenta.BLOQUEADA)
        self.assertFalse(self.usuario.is_active)

    def test_dos_fallos_no_bloquean(self):
        self.intentar('mala')
        self.intentar('mala')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.estado_cuenta, Usuario.EstadoCuenta.ACTIVA)

    def test_cuenta_bloqueada_no_entra_ni_con_clave_correcta(self):
        for _ in range(3):
            self.intentar('mala')
        resp = self.intentar('Prueba123!')
        self.assertContains(resp, 'bloqueada')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_exitoso_reinicia_el_contador(self):
        self.intentar('mala')
        self.intentar('mala')
        self.intentar('Prueba123!')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.intentos_fallidos, 0)

    def test_admin_reactiva_y_el_contador_vuelve_a_cero(self):
        for _ in range(3):
            self.intentar('mala')
        self.usuario.refresh_from_db()
        self.usuario.estado_cuenta = Usuario.EstadoCuenta.ACTIVA
        self.usuario.save()
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.intentos_fallidos, 0)
        self.assertTrue(self.usuario.is_active)
        
# MD5 solo en pruebas: hace los tests mucho más rápidos. En producción se usa el hasher normal.
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CodigoRecuperacionTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username='rec@test.com', email='rec@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE,
        )

    def test_genera_codigo_de_6_digitos_y_no_lo_guarda_en_claro(self):
        objeto, codigo = CodigoRecuperacion.generar(self.usuario)
        self.assertEqual(len(codigo), 6)
        self.assertTrue(codigo.isdigit())
        self.assertNotEqual(objeto.codigo_hash, codigo)

    def test_codigo_correcto_es_valido(self):
        objeto, codigo = CodigoRecuperacion.generar(self.usuario)
        self.assertTrue(objeto.validar(codigo))

    def test_codigo_incorrecto_es_rechazado_y_cuenta_el_intento(self):
        objeto, codigo = CodigoRecuperacion.generar(self.usuario)
        incorrecto = '000000' if codigo != '000000' else '111111'
        self.assertFalse(objeto.validar(incorrecto))
        objeto.refresh_from_db()
        self.assertEqual(objeto.intentos, 1)

    def test_codigo_vencido_es_rechazado(self):
        objeto, codigo = CodigoRecuperacion.generar(self.usuario)
        objeto.expira_en = timezone.now() - timedelta(minutes=1)
        objeto.save()
        self.assertFalse(objeto.validar(codigo))

    def test_codigo_usado_no_se_puede_reutilizar(self):
        objeto, codigo = CodigoRecuperacion.generar(self.usuario)
        self.assertTrue(objeto.validar(codigo))
        objeto.marcar_usado()
        self.assertFalse(objeto.validar(codigo))

    def test_codigo_nuevo_invalida_el_anterior(self):
        primero, codigo1 = CodigoRecuperacion.generar(self.usuario)
        segundo, codigo2 = CodigoRecuperacion.generar(self.usuario)
        primero.refresh_from_db()
        self.assertFalse(primero.validar(codigo1))
        self.assertTrue(segundo.validar(codigo2))

    def test_tras_5_intentos_fallidos_el_codigo_queda_inutilizable(self):
        objeto, codigo = CodigoRecuperacion.generar(self.usuario)
        incorrecto = '000000' if codigo != '000000' else '111111'
        for _ in range(CodigoRecuperacion.MAX_INTENTOS):
            objeto.validar(incorrecto)
        self.assertFalse(objeto.validar(codigo))  # ni con el código correcto

    def test_ultimo_vigente_devuelve_none_si_no_hay(self):
        self.assertIsNone(CodigoRecuperacion.ultimo_vigente(self.usuario))
        objeto, _ = CodigoRecuperacion.generar(self.usuario)
        self.assertEqual(CodigoRecuperacion.ultimo_vigente(self.usuario), objeto)

class VerContrasenaTests(TestCase):
    """Botón del ojo para mostrar u ocultar la contraseña."""

    def test_login_tiene_boton_del_ojo(self):
        resp = self.client.get(reverse('login'))
        self.assertContains(resp, 'Mostrar contraseña')
        self.assertContains(resp, 'js/ver_contrasena.js')

    def test_crear_usuario_tiene_boton_del_ojo(self):
        admin = Usuario.objects.create_user(
            username='laura.sicuariza@tecniled.com', email='laura.sicuariza@tecniled.com',
            password='Prueba123!', first_name='Laura Daniela', last_name='Sicuariza Gómez',
            rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.client.force_login(admin)
        resp = self.client.get(reverse('crear_usuario'))
        self.assertContains(resp, 'Mostrar contraseña')
        self.assertContains(resp, 'js/ver_contrasena.js')

class UsuarioDetalleTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin_det@test.com', email='admin_det@test.com',
            password='Prueba123!', rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.usuario = Usuario.objects.create_user(
            username='ver@test.com', email='ver@test.com', password='Prueba123!',
            first_name='Ana', last_name='Perez', documento='555', rol=Usuario.Rol.CLIENTE,
        )

    def test_admin_ve_datos_rol_y_estado(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('usuario_detalle', args=[self.usuario.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ver@test.com')
        self.assertContains(resp, '555')
        self.assertContains(resp, 'Cliente')
        self.assertContains(resp, 'Activa')

    def test_usuario_inexistente_da_404(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('usuario_detalle', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_cliente_recibe_403(self):
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse('usuario_detalle', args=[self.usuario.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_sin_sesion_va_al_login(self):
        resp = self.client.get(reverse('usuario_detalle', args=[self.usuario.pk]))
        self.assertEqual(resp.status_code, 302)
        
class EditarUsuarioTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin@test.com', email='admin@test.com',
            password='Prueba123!', rol=Usuario.Rol.ADMINISTRADOR)
        self.otro = Usuario.objects.create_user(
            username='otro@test.com', email='otro@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE, first_name='Ana')
        self.client.force_login(self.admin)
        self.url = reverse('editar_rol', args=[self.otro.id])

    def datos(self, **extra):
        d = {'first_name': 'Ana', 'last_name': 'Pérez', 'documento': '123',
             'telefono': '3001234567', 'rol': 'cliente', 'estado_cuenta': 'activa'}
        d.update(extra)
        return d

    def test_admin_actualiza_datos_permitidos(self):
        r = self.client.post(self.url, self.datos(first_name='Ana María'))
        self.assertRedirects(r, reverse('usuarios_lista'))
        self.otro.refresh_from_db()
        self.assertEqual(self.otro.first_name, 'Ana María')
        self.assertEqual(self.otro.telefono, '3001234567')

    def test_no_permite_cambiar_correo(self):
        r = self.client.post(self.url, self.datos(email='hack@test.com'))
        self.assertEqual(r.status_code, 200)
        self.otro.refresh_from_db()
        self.assertEqual(self.otro.email, 'otro@test.com')

    def test_admin_no_puede_suspenderse_a_si_mismo(self):
        url = reverse('editar_rol', args=[self.admin.id])
        r = self.client.post(url, self.datos(rol='administrador', estado_cuenta='suspendida'))
        self.assertEqual(r.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.estado_cuenta, 'activa')


class InactivarUsuarioTests(TestCase):
    """G1-1174: inactivar la cuenta de un usuario."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin_inact@test.com', email='admin_inact@test.com',
            password='Prueba123!', rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.usuario = Usuario.objects.create_user(
            username='victima@test.com', email='victima@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE,
        )
        self.url = reverse('inactivar_usuario', args=[self.usuario.pk])

    def test_admin_inactiva_usuario_activo_y_se_bloquea_su_acceso(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse('usuario_detalle', args=[self.usuario.pk]))
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.estado_cuenta, Usuario.EstadoCuenta.SUSPENDIDA)
        # Acceso bloqueado: ya no puede iniciar sesión con su clave correcta
        self.client.logout()
        resp = self.client.post(reverse('login'), {'correo': 'victima@test.com', 'contrasena': 'Prueba123!'})
        self.assertContains(resp, 'suspendida')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_no_se_puede_inactivar_dos_veces(self):
        self.usuario.estado_cuenta = Usuario.EstadoCuenta.SUSPENDIDA
        self.usuario.save()
        self.client.force_login(self.admin)
        resp = self.client.post(self.url, follow=True)
        self.assertContains(resp, 'ya no está activa')
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.estado_cuenta, Usuario.EstadoCuenta.SUSPENDIDA)

    def test_admin_no_puede_inactivarse_a_si_mismo(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse('inactivar_usuario', args=[self.admin.pk]), follow=True)
        self.assertContains(resp, 'No puedes inactivar tu propia cuenta')
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.estado_cuenta, Usuario.EstadoCuenta.ACTIVA)

    def test_cliente_recibe_403_y_no_inactiva(self):
        otro = Usuario.objects.create_user(
            username='otro@test.com', email='otro@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE,
        )
        self.client.force_login(otro)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 403)
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.estado_cuenta, Usuario.EstadoCuenta.ACTIVA)

    def test_solo_acepta_post(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)
        
class MensajesTests(TestCase):
    def renderizar(self, nivel, texto):
        from django.contrib.messages.storage.base import Message
        from django.template.loader import render_to_string

        return render_to_string(
            'partials/mensajes.html', {'messages': [Message(nivel, texto)]}
        )

    def test_cada_tipo_tiene_su_color(self):
        from django.contrib.messages import constants

        self.assertIn('bg-emerald-50', self.renderizar(constants.SUCCESS, 'Guardado'))
        self.assertIn('bg-red-50', self.renderizar(constants.ERROR, 'Falló'))
        self.assertIn('bg-amber-50', self.renderizar(constants.WARNING, 'Cuidado'))
        self.assertIn('bg-blue-50', self.renderizar(constants.INFO, 'Dato'))

    def test_mensaje_es_accesible_y_se_puede_cerrar(self):
        from django.contrib.messages import constants

        html = self.renderizar(constants.SUCCESS, 'Guardado')
        self.assertIn('role="alert"', html)
        self.assertIn('aria-label="Cerrar mensaje"', html)
        
class ModalConfirmacionTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='admin_modal@test.com', email='admin_modal@test.com',
            password='Prueba123!', rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.usuario = Usuario.objects.create_user(
            username='modal@test.com', email='modal@test.com',
            password='Prueba123!', rol=Usuario.Rol.CLIENTE,
        )
        self.client.force_login(self.admin)

    def test_inactivar_usuario_pide_confirmacion_con_el_modal(self):
        resp = self.client.get(reverse('usuario_detalle', args=[self.usuario.pk]))
        self.assertContains(resp, 'id="modal-confirmacion"')
        self.assertContains(resp, 'data-confirmar=')
        self.assertContains(resp, 'js/confirmar.js')
        self.assertNotContains(resp, 'return confirm(')
        
        
class TipoDeMensajeTests(TestCase):
    def test_recuperar_contrasena_muestra_aviso_informativo(self):
        from django.contrib.messages import get_messages

        resp = self.client.post(reverse('recuperar_contrasena'), {'correo': 'nadie@test.com'})
        mensajes = list(get_messages(resp.wsgi_request))
        self.assertEqual(mensajes[0].level_tag, 'info')
        

class IconosConDescripcionTests(TestCase):
    """G1-1194: revisa todas las plantillas del proyecto."""

    def plantillas(self):
        from pathlib import Path
        from django.conf import settings

        carpeta = Path(settings.BASE_DIR)
        for archivo in carpeta.rglob('*.html'):
            if 'venv' not in archivo.parts:
                yield archivo, archivo.read_text(encoding='utf-8')

    def test_todos_los_iconos_son_decorativos(self):
        import re

        for archivo, texto in self.plantillas():
            for svg in re.findall(r'<svg\b[^>]*>', texto):
                self.assertIn('aria-hidden="true"', svg, f'{archivo.name}: {svg[:60]}')

    def test_botones_solo_con_icono_tienen_descripcion(self):
        import re

        patron = re.compile(r'<(a|button)\b([^>]*)>(.*?)</\1>', re.S)
        for archivo, texto in self.plantillas():
            for etiqueta in patron.finditer(texto):
                atributos, contenido = etiqueta.group(2), etiqueta.group(3)
                if '<svg' not in contenido:
                    continue
                sin_iconos = re.sub(r'<svg.*?</svg>', '', contenido, flags=re.S)
                texto_visible = re.sub(r'<[^>]+>', '', sin_iconos)
                texto_visible = re.sub(r'{%.*?%}|{{.*?}}', 'x', texto_visible).strip()
                if texto_visible:
                    continue
                self.assertIn('aria-label=', atributos, f'{archivo.name}: {atributos[:60]}')
                self.assertIn('title=', atributos, f'{archivo.name}: {atributos[:60]}')
                
                
class ContrasteTests(TestCase):
    """G1-1208: combinaciones de color que no cumplen el contraste mínimo (4.5:1)."""

    def test_no_hay_texto_blanco_sobre_amarillo_ni_sobre_rojo_500(self):
        import re
        from pathlib import Path
        from django.conf import settings

        for archivo in Path(settings.BASE_DIR).rglob('*.html'):
            if 'venv' in archivo.parts:
                continue
            texto = archivo.read_text(encoding='utf-8')
            for clases in re.findall(r'class="([^"]*)"', texto):
                lista = clases.split()
                if 'text-white' not in lista:
                    continue
                self.assertNotIn('bg-[#F2AE30]', lista, f'{archivo.name}: texto blanco sobre amarillo')
                self.assertNotIn('bg-red-500', lista, f'{archivo.name}: texto blanco sobre red-500')


class IdiomaYZonaHorariaTests(TestCase):
    def test_formulario_vacio_muestra_error_en_espanol(self):
        from Usuarios.forms import CrearUsuarioInternoForm

        form = CrearUsuarioInternoForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('Este campo es obligatorio.', form.errors['email'])

    def test_zona_horaria_es_bogota(self):
        self.assertEqual(timezone.get_current_timezone_name(), 'America/Bogota')
        
        
class MigasDePanTests(TestCase):
    """G1-1192: migas de pan con nivel intermedio y títulos claros."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username='luis.silva@tecniled.com', email='luis.silva@tecniled.com',
            password='Prueba123!', first_name='Luis José', last_name='Silva Fajardo',
            rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.client.force_login(self.admin)

    def test_migas_son_navegacion_accesible(self):
        resp = self.client.get(reverse('usuarios_lista'))
        self.assertContains(resp, 'aria-label="Migas de pan"')
        self.assertContains(resp, 'aria-current="page"')

    def test_titulo_pestana_usuarios(self):
        resp = self.client.get(reverse('usuarios_lista'))
        self.assertContains(resp, '<title>Gestión de usuarios - TECNILED</title>')

    def test_crear_usuario_tiene_miga_a_la_lista(self):
        resp = self.client.get(reverse('crear_usuario'))
        self.assertTemplateUsed(resp, 'partials/miga.html')
        self.assertContains(resp, 'href="' + reverse('usuarios_lista') + '"')
        self.assertContains(resp, 'Nuevo usuario')

    def test_registrar_producto_tiene_miga_a_la_lista(self):
        resp = self.client.get(reverse('crear_producto'))
        self.assertTemplateUsed(resp, 'partials/miga.html')
        self.assertContains(resp, 'Registrar producto')

    def test_registrar_proveedor_tiene_miga_a_la_lista(self):
        resp = self.client.get(reverse('crear_proveedor'))
        self.assertTemplateUsed(resp, 'partials/miga.html')
        self.assertContains(resp, 'Registrar proveedor')

    def test_lista_no_tiene_miga_intermedia(self):
        resp = self.client.get(reverse('usuarios_lista'))
        self.assertTemplateNotUsed(resp, 'partials/miga.html')
