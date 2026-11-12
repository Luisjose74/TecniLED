import shutil
import tempfile
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from Usuarios.models import Usuario
from productos.models import Proveedor

from datetime import timedelta
from django.utils import timezone
from productos.forms import ProductoForm

from productos.models import Categoria, MovimientoInventario, Producto
from notificaciones.models import Notificacion

# Las imágenes de los tests se guardan aquí y se borran al terminar
MEDIA_TEMPORAL = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)


def imagen_valida(nombre='foto.png'):
    buffer = BytesIO()
    Image.new('RGB', (10, 10), 'red').save(buffer, 'PNG')
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type='image/png')


def crear_usuario(correo, rol):
    return Usuario.objects.create_user(
        username=correo, email=correo, password='Prueba123!', rol=rol
    )

def categoria(nombre):
    """Devuelve la categoría con ese nombre (las 4 iniciales las crea la migración)."""
    return Categoria.objects.get_or_create(nombre=nombre)[0]

def crear_producto_bd(**overrides):
    datos = {
        'sku': 'E1', 'nombre': 'Cable THW Calibre 12',
        'categoria': categoria('Eléctricos'), 'precio': '45.00', 'stock': 50,
        'descripcion': 'Cable de cobre.', 'instalacion': 'Pelar los extremos.',
    }
    datos.update(overrides)
    return Producto.objects.create(**datos)


class ProductoModeloTests(TestCase):
    def test_precio_oferta_menor_al_precio_es_valido(self):
        p = Producto(
            categoria=categoria('Eléctricos'), sku='M1', nombre='X',
            precio='15.50', precio_oferta='12.00', stock=1,
            descripcion='d', instalacion='i',
        )
        p.full_clean()  # no debe lanzar excepción

    def test_precio_oferta_mayor_o_igual_al_precio_es_invalido(self):
        p = Producto(
            categoria=categoria('Eléctricos'), sku='M2', nombre='X',
            precio='10.00', precio_oferta='10.00', stock=1,
            descripcion='d', instalacion='i',
        )
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn('precio_oferta', ctx.exception.message_dict)

    def test_un_producto_nuevo_queda_activo_y_no_destacado(self):
        p = crear_producto_bd(sku='M3')
        self.assertTrue(p.activo)
        self.assertFalse(p.destacado_en_inicio)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class RegistrarProductoTests(TestCase):
    """G1-141: Productos - Registrar producto."""

    def setUp(self):
        self.admin = crear_usuario('admin_prod@test.com', Usuario.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)

    def datos_validos(self, **overrides):
        datos = {
            'sku': 'E1', 'nombre': 'Cable THW Calibre 12',
            'categoria': categoria('Eléctricos').pk,
            'precio': '45.00', 'precio_oferta': '', 'stock': '50',
            'descripcion': 'Cable de cobre suave.', 'instalacion': 'Pelar los extremos.',
        }
        datos.update(overrides)
        return datos

    def test_registra_producto_y_redirige_al_listado(self):
        resp = self.client.post(reverse('crear_producto'), self.datos_validos())
        self.assertRedirects(resp, reverse('productos_lista'))
        p = Producto.objects.get(sku='E1')
        self.assertEqual(p.nombre, 'Cable THW Calibre 12')
        self.assertEqual(p.stock, 50)

    def test_producto_registrado_aparece_en_el_listado(self):
        self.client.post(reverse('crear_producto'), self.datos_validos())
        resp = self.client.get(reverse('productos_lista'))
        self.assertContains(resp, 'Cable THW Calibre 12')

    def test_control_inventario_tambien_puede_registrar(self):
        control = crear_usuario('inv_prod@test.com', Usuario.Rol.CONTROL_INVENTARIO)
        self.client.force_login(control)
        resp = self.client.post(reverse('crear_producto'), self.datos_validos())
        self.assertRedirects(resp, reverse('productos_lista'))

    def test_campos_obligatorios_vacios_no_crean_producto(self):
        resp = self.client.post(reverse('crear_producto'), {})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Producto.objects.count(), 0)
        errores = resp.context['form'].errors
        for campo in ['sku', 'nombre', 'precio', 'stock', 'descripcion', 'instalacion']:
            self.assertIn(campo, errores)

    def test_sku_duplicado_no_crea_producto(self):
        crear_producto_bd(sku='E1')
        resp = self.client.post(
            reverse('crear_producto'), self.datos_validos(nombre='Otro nombre')
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Producto.objects.filter(sku='E1').count(), 1)

    def test_precio_oferta_mayor_al_precio_es_rechazado(self):
        resp = self.client.post(
            reverse('crear_producto'), self.datos_validos(precio_oferta='50.00')
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Producto.objects.filter(sku='E1').exists())
        self.assertContains(resp, 'El precio de oferta debe ser menor al precio normal.')

    def test_categoria_invalida_manipulada_es_rechazada(self):
        resp = self.client.post(
            reverse('crear_producto'), self.datos_validos(categoria='hacker')
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Producto.objects.filter(sku='E1').exists())

    def test_stock_negativo_es_rechazado(self):
        resp = self.client.post(reverse('crear_producto'), self.datos_validos(stock='-5'))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Producto.objects.filter(sku='E1').exists())

    def test_cliente_recibe_403(self):
        cliente = crear_usuario('cliente_prod@test.com', Usuario.Rol.CLIENTE)
        self.client.force_login(cliente)
        resp = self.client.get(reverse('crear_producto'))
        self.assertEqual(resp.status_code, 403)

    def test_usuario_sin_sesion_no_accede(self):
        self.client.logout()
        resp = self.client.get(reverse('crear_producto'))
        self.assertEqual(resp.status_code, 302)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class CargarImagenTests(TestCase):
    """G1-142: Productos - Cargar imagen."""

    def setUp(self):
        self.admin = crear_usuario('admin_img@test.com', Usuario.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)

    def datos(self, **overrides):
        datos = {
            'sku': 'I1', 'nombre': 'Lámpara Colgante Moderna',
            'categoria': categoria('Interiores').pk,
            'precio': '65.00', 'precio_oferta': '', 'stock': '8',
            'descripcion': 'Lámpara.', 'instalacion': 'Colgar del techo.',
        }
        datos.update(overrides)
        return datos

    def test_imagen_valida_se_almacena(self):
        resp = self.client.post(
            reverse('crear_producto'), self.datos(imagen=imagen_valida())
        )
        self.assertRedirects(resp, reverse('productos_lista'))
        p = Producto.objects.get(sku='I1')
        self.assertTrue(p.imagen)
        self.assertTrue(p.imagen.name.startswith('productos/'))
        self.assertTrue(p.imagen.storage.exists(p.imagen.name))

    def test_imagen_guardada_se_muestra_en_el_listado(self):
        self.client.post(reverse('crear_producto'), self.datos(imagen=imagen_valida()))
        resp = self.client.get(reverse('productos_lista'))
        self.assertContains(resp, 'media/productos/')

    def test_archivo_que_no_es_imagen_es_rechazado(self):
        falso = SimpleUploadedFile('virus.png', b'esto no es una imagen', content_type='image/png')
        resp = self.client.post(reverse('crear_producto'), self.datos(imagen=falso))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Producto.objects.filter(sku='I1').exists())

    def test_se_puede_registrar_sin_imagen(self):
        resp = self.client.post(reverse('crear_producto'), self.datos())
        self.assertRedirects(resp, reverse('productos_lista'))
        self.assertFalse(Producto.objects.get(sku='I1').imagen)


class BuscarProductosTests(TestCase):
    """G1-143: Productos - Buscar productos."""

    def setUp(self):
        self.admin = crear_usuario('admin_lista_prod@test.com', Usuario.Rol.ADMINISTRADOR)
        crear_producto_bd(sku='E1', nombre='Cable THW Calibre 12')
        crear_producto_bd(
            sku='I1', nombre='Lámpara Colgante Moderna',
            categoria=categoria('Interiores'),
        )
        self.client.force_login(self.admin)

    def test_busqueda_encuentra_por_nombre(self):
        resp = self.client.get(reverse('productos_lista'), {'q': 'Cable'})
        self.assertContains(resp, 'Cable THW Calibre 12')
        self.assertNotContains(resp, 'Lámpara Colgante Moderna')

    def test_busqueda_no_distingue_mayusculas(self):
        resp = self.client.get(reverse('productos_lista'), {'q': 'cable thw'})
        self.assertContains(resp, 'Cable THW Calibre 12')

    def test_busqueda_encuentra_por_codigo(self):
        resp = self.client.get(reverse('productos_lista'), {'q': 'I1'})
        self.assertContains(resp, 'Lámpara Colgante Moderna')
        self.assertNotContains(resp, 'Cable THW Calibre 12')

    def test_busqueda_sin_resultados_muestra_mensaje(self):
        resp = self.client.get(reverse('productos_lista'), {'q': 'noexiste'})
        self.assertContains(resp, 'No se encontraron productos.')

    def test_sin_busqueda_muestra_todos(self):
        resp = self.client.get(reverse('productos_lista'))
        self.assertContains(resp, 'Cable THW Calibre 12')
        self.assertContains(resp, 'Lámpara Colgante Moderna')

    def test_filtro_por_categoria(self):
        resp = self.client.get(reverse('productos_lista'), {'categoria': categoria('Interiores').pk})
        self.assertContains(resp, 'Lámpara Colgante Moderna')
        self.assertNotContains(resp, 'Cable THW Calibre 12')

    def test_categoria_invalida_en_la_url_se_ignora(self):
        resp = self.client.get(reverse('productos_lista'), {'categoria': 'hacker'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Cable THW Calibre 12')

    def test_busqueda_y_categoria_se_combinan(self):
        resp = self.client.get(
            reverse('productos_lista'), {'q': 'Cable', 'categoria': categoria('Interiores').pk}
        )
        self.assertContains(resp, 'No se encontraron productos.')

    def test_paginacion_limita_a_10_por_pagina(self):
        for i in range(15):
            crear_producto_bd(sku=f'P{i}', nombre=f'Producto de prueba {i}')
        resp = self.client.get(reverse('productos_lista'))
        self.assertEqual(len(resp.context['productos']), 10)

    def test_segunda_pagina_conserva_la_busqueda(self):
        for i in range(15):
            crear_producto_bd(sku=f'P{i}', nombre=f'Producto de prueba {i}')
        resp = self.client.get(reverse('productos_lista'), {'q': 'Producto de prueba', 'page': 2})
        self.assertEqual(len(resp.context['productos']), 5)
        self.assertEqual(resp.context['query'], 'Producto de prueba')

    def test_cliente_recibe_403(self):
        cliente = crear_usuario('cliente_lista_prod@test.com', Usuario.Rol.CLIENTE)
        self.client.force_login(cliente)
        resp = self.client.get(reverse('productos_lista'))
        self.assertEqual(resp.status_code, 403)
        
        
class DestacarEnInicioTests(TestCase):
    """Interruptor 'Destacado en Inicio' (G1-148)."""

    def setUp(self):
        self.admin = crear_usuario('admin_dest@test.com', Usuario.Rol.ADMINISTRADOR)
        self.producto = crear_producto_bd(sku='D1', nombre='Producto destacable')
        self.client.force_login(self.admin)

    def test_alterna_a_destacado_y_de_vuelta(self):
        url = reverse('alternar_destacado', args=[self.producto.pk])
        self.client.post(url)
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.destacado_en_inicio)
        self.client.post(url)
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.destacado_en_inicio)

    def test_vuelve_a_la_pagina_con_la_busqueda(self):
        url = reverse('alternar_destacado', args=[self.producto.pk])
        resp = self.client.post(url, {'next': '/productos/?q=destacable'})
        self.assertRedirects(resp, '/productos/?q=destacable')

    def test_next_hacia_otro_sitio_es_ignorado(self):
        url = reverse('alternar_destacado', args=[self.producto.pk])
        resp = self.client.post(url, {'next': 'https://sitio-malicioso.com'})
        self.assertRedirects(resp, reverse('productos_lista'))

    def test_get_no_esta_permitido(self):
        resp = self.client.get(reverse('alternar_destacado', args=[self.producto.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_cliente_recibe_403_y_no_cambia_nada(self):
        cliente = crear_usuario('cliente_dest@test.com', Usuario.Rol.CLIENTE)
        self.client.force_login(cliente)
        resp = self.client.post(reverse('alternar_destacado', args=[self.producto.pk]))
        self.assertEqual(resp.status_code, 403)
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.destacado_en_inicio)
        
        
        

# ---------------------------------------------------------------------------
# PROVEEDORES (G1-134, G1-137, G1-138)
# ---------------------------------------------------------------------------



def crear_proveedor_bd(**overrides):
    datos = {
        'nombre': 'Distribuidora Eléctrica S.A.S.', 'nit': '900123456-7',
        'telefono': '3001112233', 'correo': 'ventas@dist.com',
    }
    datos.update(overrides)
    return Proveedor.objects.create(**datos)


class BuscarProveedoresTests(TestCase):
    """G1-134: Proveedor - buscar proveedor."""

    def setUp(self):
        self.admin = crear_usuario('admin_busq_prov@test.com', Usuario.Rol.ADMINISTRADOR)
        crear_proveedor_bd()
        crear_proveedor_bd(nombre='Ferretería El Tornillo', nit='800555111-2')
        self.client.force_login(self.admin)

    def test_busca_por_nombre(self):
        resp = self.client.get(reverse('proveedores_lista'), {'q': 'Distribuidora'})
        self.assertContains(resp, 'Distribuidora Eléctrica S.A.S.')
        self.assertNotContains(resp, 'Ferretería El Tornillo')

    def test_busqueda_no_distingue_mayusculas(self):
        resp = self.client.get(reverse('proveedores_lista'), {'q': 'el tornillo'})
        self.assertContains(resp, 'Ferretería El Tornillo')

    def test_busca_por_nit(self):
        resp = self.client.get(reverse('proveedores_lista'), {'q': '800555'})
        self.assertContains(resp, 'Ferretería El Tornillo')
        self.assertNotContains(resp, 'Distribuidora Eléctrica')

    def test_busca_por_nit_escrito_sin_guion(self):
        resp = self.client.get(reverse('proveedores_lista'), {'q': '9001234567'})
        self.assertContains(resp, 'Distribuidora Eléctrica S.A.S.')
        self.assertNotContains(resp, 'Ferretería El Tornillo')

    def test_sin_resultados_informa_que_no_se_encontraron(self):
        resp = self.client.get(reverse('proveedores_lista'), {'q': 'zzzz'})
        self.assertContains(resp, 'No se encontraron proveedores')
        self.assertNotContains(resp, 'Distribuidora Eléctrica')

    def test_sin_busqueda_muestra_todos(self):
        resp = self.client.get(reverse('proveedores_lista'))
        self.assertContains(resp, 'Distribuidora Eléctrica S.A.S.')
        self.assertContains(resp, 'Ferretería El Tornillo')

    def test_paginacion_conserva_la_busqueda(self):
        for i in range(15):
            crear_proveedor_bd(nombre=f'Proveedor masivo {i}', nit=f'700{i:03d}-1')
        resp = self.client.get(reverse('proveedores_lista'), {'q': 'masivo', 'page': 2})
        self.assertEqual(len(resp.context['proveedores']), 5)
        self.assertEqual(resp.context['query'], 'masivo')

    def test_control_inventario_recibe_403(self):
        inv = crear_usuario('inv_busq_prov@test.com', Usuario.Rol.CONTROL_INVENTARIO)
        self.client.force_login(inv)
        resp = self.client.get(reverse('proveedores_lista'))
        self.assertEqual(resp.status_code, 403)
        
        
        


class ModificarProveedorTests(TestCase):
    """G1-137: Proveedor - modificar proveedor."""

    def setUp(self):
        self.admin = crear_usuario('admin_mod_prov@test.com', Usuario.Rol.ADMINISTRADOR)
        self.proveedor = crear_proveedor_bd()
        self.url = reverse('editar_proveedor', args=[self.proveedor.pk])
        self.client.force_login(self.admin)

    def datos(self, **overrides):
        datos = {
            'contacto': 'Carlos Pérez', 'telefono': '3109998877',
            'correo': 'nuevo@dist.com', 'direccion': 'Calle 10 # 5-20, Sogamoso',
        }
        datos.update(overrides)
        return datos

    def test_formulario_se_precarga_con_los_datos_actuales(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, 'Distribuidora Eléctrica S.A.S.')
        self.assertContains(resp, '900123456-7')
        self.assertEqual(resp.context['form'].initial['telefono'], '3001112233')

    def test_actualiza_telefono_direccion_y_correo(self):
        resp = self.client.post(self.url, self.datos())
        self.assertRedirects(resp, reverse('proveedores_lista'))
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.telefono, '3109998877')
        self.assertEqual(self.proveedor.correo, 'nuevo@dist.com')
        self.assertEqual(self.proveedor.direccion, 'Calle 10 # 5-20, Sogamoso')

    def test_no_permite_cambiar_nombre_ni_nit(self):
        self.client.post(self.url, self.datos(nombre='Hackeado S.A.', nit='111111111-1'))
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.nombre, 'Distribuidora Eléctrica S.A.S.')
        self.assertEqual(self.proveedor.nit, '900123456-7')

    def test_no_cambia_el_estado_activo(self):
        self.client.post(self.url, self.datos())  # sin 'activo' en el POST
        self.proveedor.refresh_from_db()
        self.assertTrue(self.proveedor.activo)

    def test_correo_invalido_es_rechazado(self):
        resp = self.client.post(self.url, self.datos(correo='no-es-correo'))
        self.assertEqual(resp.status_code, 200)
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.correo, 'ventas@dist.com')

    def test_telefono_con_letras_es_rechazado(self):
        resp = self.client.post(self.url, self.datos(telefono='abc123'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('telefono', resp.context['form'].errors)
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.telefono, '3001112233')

    def test_telefono_muy_corto_es_rechazado(self):
        resp = self.client.post(self.url, self.datos(telefono='123'))
        self.assertIn('telefono', resp.context['form'].errors)

    def test_actualiza_los_productos_vinculados(self):
        p1 = crear_producto_bd(sku='V1', nombre='Producto uno', proveedor=self.proveedor)
        p2 = crear_producto_bd(sku='V2', nombre='Producto dos')
        self.client.post(self.url, self.datos(productos=[p2.pk]))
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertIsNone(p1.proveedor)
        self.assertEqual(p2.proveedor, self.proveedor)

    def test_guardar_no_desvincula_un_producto_inactivo_ya_asociado(self):
        inactivo = crear_producto_bd(
            sku='V3', nombre='Producto inactivo', activo=False, proveedor=self.proveedor
        )
        self.client.post(self.url, self.datos(productos=[inactivo.pk]))
        inactivo.refresh_from_db()
        self.assertEqual(inactivo.proveedor, self.proveedor)

    def test_proveedor_inexistente_da_404(self):
        resp = self.client.get(reverse('editar_proveedor', args=[9999]))
        self.assertEqual(resp.status_code, 404)

    def test_la_lista_tiene_el_boton_editar(self):
        resp = self.client.get(reverse('proveedores_lista'))
        self.assertContains(resp, self.url)

    def test_control_inventario_recibe_403(self):
        inv = crear_usuario('inv_mod_prov@test.com', Usuario.Rol.CONTROL_INVENTARIO)
        self.client.force_login(inv)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 403)

    def test_usuario_sin_sesion_no_accede(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        
        

class InactivarProveedorTests(TestCase):
    """G1-138: Proveedor - inactivar proveedor."""

    def setUp(self):
        self.admin = crear_usuario('admin_inact_prov@test.com', Usuario.Rol.ADMINISTRADOR)
        self.proveedor = crear_proveedor_bd()
        self.url = reverse('inactivar_proveedor', args=[self.proveedor.pk])
        self.client.force_login(self.admin)

    def test_inactiva_con_motivo_y_guarda_el_motivo(self):
        resp = self.client.post(self.url, {'motivo': 'Incumplió las entregas'})
        self.assertRedirects(resp, reverse('proveedores_lista'))
        self.proveedor.refresh_from_db()
        self.assertFalse(self.proveedor.activo)
        self.assertEqual(self.proveedor.motivo_inactivacion, 'Incumplió las entregas')

    def test_muestra_mensaje_de_exito(self):
        resp = self.client.post(self.url, {'motivo': 'Incumplió las entregas'}, follow=True)
        self.assertContains(resp, 'inactivado correctamente')

    def test_registra_la_fecha_del_cambio(self):
        antes = timezone.now() - timedelta(days=30)
        Proveedor.objects.filter(pk=self.proveedor.pk).update(fecha_actualizacion=antes)
        self.client.post(self.url, {'motivo': 'Incumplió las entregas'})
        self.proveedor.refresh_from_db()
        self.assertGreater(self.proveedor.fecha_actualizacion, antes)

    def test_conserva_la_informacion_y_los_productos(self):
        producto = crear_producto_bd(sku='I1', nombre='Producto del proveedor', proveedor=self.proveedor)
        self.client.post(self.url, {'motivo': 'Incumplió las entregas'})
        self.assertTrue(Proveedor.objects.filter(pk=self.proveedor.pk).exists())
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.nit, '900123456-7')
        self.assertEqual(self.proveedor.correo, 'ventas@dist.com')
        producto.refresh_from_db()
        self.assertEqual(producto.proveedor, self.proveedor)

    def test_sin_motivo_es_rechazado(self):
        self.client.post(self.url, {'motivo': ''})
        self.proveedor.refresh_from_db()
        self.assertTrue(self.proveedor.activo)

    def test_motivo_muy_corto_es_rechazado(self):
        self.client.post(self.url, {'motivo': 'abc'})
        self.proveedor.refresh_from_db()
        self.assertTrue(self.proveedor.activo)

    def test_motivo_solo_espacios_es_rechazado(self):
        self.client.post(self.url, {'motivo': '        '})
        self.proveedor.refresh_from_db()
        self.assertTrue(self.proveedor.activo)

    def test_motivo_invalido_muestra_el_error(self):
        resp = self.client.post(self.url, {'motivo': ''}, follow=True)
        self.assertContains(resp, 'Debes indicar el motivo')

    def test_inactivar_uno_ya_inactivo_es_transicion_invalida(self):
        self.client.post(self.url, {'motivo': 'Primer motivo válido'})
        resp = self.client.post(self.url, {'motivo': 'Segundo motivo distinto'}, follow=True)
        self.assertContains(resp, 'ya está inactivo')
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.motivo_inactivacion, 'Primer motivo válido')

    def test_metodo_inactivar_del_modelo_rechaza_si_ya_esta_inactivo(self):
        self.proveedor.inactivar('Motivo válido')
        with self.assertRaises(ValueError):
            self.proveedor.inactivar('Otro motivo')

    def test_get_no_esta_permitido(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.proveedor.refresh_from_db()
        self.assertTrue(self.proveedor.activo)

    def test_proveedor_inexistente_da_404(self):
        resp = self.client.post(reverse('inactivar_proveedor', args=[9999]), {'motivo': 'Motivo válido'})
        self.assertEqual(resp.status_code, 404)

    def test_next_externo_se_ignora(self):
        resp = self.client.post(self.url, {'motivo': 'Motivo válido', 'next': 'https://malicioso.com/'})
        self.assertRedirects(resp, reverse('proveedores_lista'))

    def test_next_interno_se_respeta(self):
        siguiente = reverse('proveedores_lista') + '?q=Distribuidora'
        resp = self.client.post(self.url, {'motivo': 'Motivo válido', 'next': siguiente})
        self.assertRedirects(resp, siguiente)

    def test_la_lista_muestra_boton_inactivar_solo_a_proveedores_activos(self):
        self.assertContains(self.client.get(reverse('proveedores_lista')), self.url)
        self.client.post(self.url, {'motivo': 'Motivo válido'})
        self.assertNotContains(self.client.get(reverse('proveedores_lista')), f'data-inactivar-url="{self.url}"')

    def test_proveedor_inactivo_no_se_ofrece_al_crear_productos(self):
        self.assertIn(self.proveedor, ProductoForm().fields['proveedor'].queryset)
        self.client.post(self.url, {'motivo': 'Motivo válido'})
        self.assertNotIn(self.proveedor, ProductoForm().fields['proveedor'].queryset)

    def test_control_inventario_recibe_403(self):
        inv = crear_usuario('inv_inact_prov@test.com', Usuario.Rol.CONTROL_INVENTARIO)
        self.client.force_login(inv)
        self.assertEqual(self.client.post(self.url, {'motivo': 'Motivo válido'}).status_code, 403)
        self.proveedor.refresh_from_db()
        self.assertTrue(self.proveedor.activo)

    def test_usuario_sin_sesion_no_puede_inactivar(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {'motivo': 'Motivo válido'}).status_code, 302)
        self.proveedor.refresh_from_db()
        self.assertTrue(self.proveedor.activo)
        
        
        

class ReactivarProveedorTests(TestCase):
    """Reactivar un proveedor inactivado (G1-138 deja la papelera visible en inactivos)."""

    def setUp(self):
        self.admin = crear_usuario('admin_react_prov@test.com', Usuario.Rol.ADMINISTRADOR)
        self.proveedor = crear_proveedor_bd()
        self.proveedor.inactivar('Incumplió las entregas')
        self.url = reverse('reactivar_proveedor', args=[self.proveedor.pk])
        self.client.force_login(self.admin)

    def test_reactiva_y_limpia_el_motivo(self):
        resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse('proveedores_lista'))
        self.proveedor.refresh_from_db()
        self.assertTrue(self.proveedor.activo)
        self.assertEqual(self.proveedor.motivo_inactivacion, '')

    def test_muestra_mensaje_de_exito(self):
        resp = self.client.post(self.url, follow=True)
        self.assertContains(resp, 'reactivado correctamente')

    def test_conserva_los_datos_del_proveedor(self):
        self.client.post(self.url)
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.nit, '900123456-7')
        self.assertEqual(self.proveedor.correo, 'ventas@dist.com')

    def test_reactivar_uno_ya_activo_es_transicion_invalida(self):
        self.client.post(self.url)
        resp = self.client.post(self.url, follow=True)
        self.assertContains(resp, 'ya está activo')

    def test_metodo_reactivar_del_modelo_rechaza_si_ya_esta_activo(self):
        self.proveedor.reactivar()
        with self.assertRaises(ValueError):
            self.proveedor.reactivar()

    def test_proveedor_reactivado_vuelve_a_ofrecerse_al_crear_productos(self):
        self.assertNotIn(self.proveedor, ProductoForm().fields['proveedor'].queryset)
        self.client.post(self.url)
        self.assertIn(self.proveedor, ProductoForm().fields['proveedor'].queryset)

    def test_la_papelera_aparece_en_activos_e_inactivos(self):
        activo = crear_proveedor_bd(nombre='Activo SAS', nit='700111222-3')
        registrado_inactivo = crear_proveedor_bd(nombre='Nace inactivo', nit='700333444-5', activo=False)
        resp = self.client.get(reverse('proveedores_lista'))
        # inactivo (inactivado antes) y el que se registró como inactivo: botón de reactivar
        self.assertContains(resp, f'data-reactivar-url="{self.url}"')
        self.assertContains(resp, f'data-reactivar-url="{reverse("reactivar_proveedor", args=[registrado_inactivo.pk])}"')
        # activo: botón de inactivar
        self.assertContains(resp, f'data-inactivar-url="{reverse("inactivar_proveedor", args=[activo.pk])}"')

    def test_get_no_esta_permitido(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_proveedor_inexistente_da_404(self):
        self.assertEqual(self.client.post(reverse('reactivar_proveedor', args=[9999])).status_code, 404)

    def test_control_inventario_recibe_403(self):
        inv = crear_usuario('inv_react_prov@test.com', Usuario.Rol.CONTROL_INVENTARIO)
        self.client.force_login(inv)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.proveedor.refresh_from_db()
        self.assertFalse(self.proveedor.activo)

    def test_usuario_sin_sesion_no_puede_reactivar(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.proveedor.refresh_from_db()
        self.assertFalse(self.proveedor.activo)

class CategoriaTests(TestCase):
    """G1-151: crear y editar categorías."""

    def setUp(self):
        self.client.force_login(crear_usuario('cat@t.com', Usuario.Rol.ADMINISTRADOR))

    def test_lista_muestra_categorias_y_cantidad_de_productos(self):
        crear_producto_bd(sku='C1', nombre='Uno')
        r = self.client.get(reverse('categorias_lista'))
        self.assertContains(r, 'Eléctricos')
        self.assertContains(r, '1 producto\n')

    def test_crear_categoria_limpia_espacios(self):
        r = self.client.post(reverse('crear_categoria'), {'nombre': '  Herramientas   manuales '})
        self.assertRedirects(r, reverse('categorias_lista'))
        self.assertTrue(Categoria.objects.filter(nombre='Herramientas manuales').exists())

    def test_crear_con_errores_no_guarda_y_reabre_el_modal(self):
        for dato, mensaje in [('', 'obligatorio'), ('a', 'al menos 2'), ('x' * 61, '60 caracteres'),
                              ('ELÉCTRICOS', 'Ya existe')]:
            cantidad = Categoria.objects.count()
            r = self.client.post(reverse('crear_categoria'), {'nombre': dato})
            self.assertContains(r, mensaje)
            self.assertContains(r, 'data-abrir="crear"')
            self.assertEqual(Categoria.objects.count(), cantidad)

    def test_editar_categoria_y_el_producto_conserva_el_vinculo(self):
        c = categoria('Eléctricos')
        p = crear_producto_bd(sku='C2')
        r = self.client.post(reverse('editar_categoria', args=[c.pk]), {'nombre': 'Eléctricos plus'})
        self.assertRedirects(r, reverse('categorias_lista'))
        p.refresh_from_db()
        self.assertEqual(p.get_categoria_display(), 'Eléctricos plus')

    def test_editar_con_su_mismo_nombre_es_valido_pero_con_el_de_otra_no(self):
        c = categoria('Interiores')
        r = self.client.post(reverse('editar_categoria', args=[c.pk]), {'nombre': 'Interiores'})
        self.assertRedirects(r, reverse('categorias_lista'))
        r = self.client.post(reverse('editar_categoria', args=[c.pk]), {'nombre': 'ferretería'})
        self.assertContains(r, 'Ya existe')

    def test_categoria_nueva_se_asigna_a_un_producto_y_filtra(self):
        self.client.post(reverse('crear_categoria'), {'nombre': 'Seguridad'})
        c = Categoria.objects.get(nombre='Seguridad')
        self.client.post(reverse('crear_producto'), {
            'sku': 'S1', 'nombre': 'Cámara', 'categoria': c.pk, 'precio': '10',
            'stock': '1', 'descripcion': 'd', 'instalacion': 'i',
        })
        self.assertContains(self.client.get(reverse('productos_lista'), {'categoria': c.pk}), 'Cámara')
        self.assertNotContains(
            self.client.get(reverse('productos_lista'), {'categoria': categoria('Interiores').pk}), 'Cámara')

    def test_solo_post_y_permisos(self):
        self.assertEqual(self.client.get(reverse('crear_categoria')).status_code, 405)
        self.client.force_login(crear_usuario('cli@t.com', Usuario.Rol.CLIENTE))
        self.assertEqual(self.client.get(reverse('categorias_lista')).status_code, 403)
        self.assertEqual(self.client.post(reverse('crear_categoria'), {'nombre': 'Hack'}).status_code, 403)



class EntradaInventarioTests(TestCase):
    """G1-149: registrar entradas de mercancía."""

    def setUp(self):
        self.usuario = crear_usuario('ent@t.com', Usuario.Rol.ADMINISTRADOR)
        self.client.force_login(self.usuario)
        self.p = crear_producto_bd(sku='E1', nombre='Foco', stock=10)

    def registrar(self, **cambios):
        datos = {'producto': self.p.pk, 'cantidad': '5', 'observacion': ''}
        datos.update(cambios)
        return self.client.post(reverse('registrar_entrada'), datos)

    def test_la_entrada_suma_al_stock_y_queda_en_el_historial(self):
        r = self.registrar(observacion='  Factura   1  ')
        self.assertRedirects(r, reverse('entradas_lista'))
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 15)
        m = MovimientoInventario.objects.get()
        self.assertEqual((m.cantidad, m.stock_resultante, m.tipo, m.usuario, m.observacion),
                         (5, 15, 'entrada', self.usuario, 'Factura 1'))
        r = self.client.get(reverse('entradas_lista'))
        self.assertContains(r, '+5')
        self.assertContains(r, 'ent@t.com')

    def test_dos_entradas_seguidas_acumulan(self):
        self.registrar(cantidad='5')
        self.registrar(cantidad='3')
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 18)

    def test_datos_invalidos_no_cambian_el_stock_y_reabren_el_modal(self):
        casos = [
            ({'cantidad': '0'}, 'mayor a 0'), ({'cantidad': '-3'}, 'mayor a 0'),
            ({'cantidad': 'abc'}, 'número entero'), ({'cantidad': ''}, 'Indica la cantidad'),
            ({'cantidad': '1.5'}, 'número entero'), ({'cantidad': '100001'}, 'no puede superar 100.000'),
            ({'producto': ''}, 'Selecciona el producto'), ({'producto': '9999'}, 'producto válido'),
            ({'observacion': 'x' * 201}, '200 caracteres'),
        ]
        for cambio, mensaje in casos:
            r = self.registrar(**cambio)
            self.assertContains(r, mensaje)
            self.assertContains(r, 'data-abrir="si"')
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 10)
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_un_producto_inactivo_no_recibe_entradas(self):
        Producto.objects.filter(pk=self.p.pk).update(activo=False)
        self.assertNotContains(self.client.get(reverse('entradas_lista')), 'Foco (SKU')
        self.assertContains(self.registrar(), 'producto válido')
        self.assertEqual(MovimientoInventario.objects.count(), 0)
        with self.assertRaises(ValueError):
            MovimientoInventario.registrar_entrada(self.p, 3)

    def test_permisos_y_metodos(self):
        self.assertEqual(self.client.get(reverse('registrar_entrada')).status_code, 405)
        self.client.force_login(crear_usuario('inv@t.com', Usuario.Rol.CONTROL_INVENTARIO))
        self.assertEqual(self.client.get(reverse('entradas_lista')).status_code, 200)
        self.client.force_login(crear_usuario('cli2@t.com', Usuario.Rol.CLIENTE))
        self.assertEqual(self.client.get(reverse('entradas_lista')).status_code, 403)
        self.assertEqual(self.registrar().status_code, 403)

    def test_busqueda_y_paginacion_del_historial(self):
        for _ in range(12):
            MovimientoInventario.registrar_entrada(self.p, 1, self.usuario)
        self.assertContains(self.client.get(reverse('entradas_lista')), 'Página 1 de 2')
        self.assertContains(self.client.get(reverse('entradas_lista'), {'q': 'E1'}), 'Foco')
        self.assertNotContains(self.client.get(reverse('entradas_lista'), {'q': 'zzz'}), 'Foco</p>')
        
        
class SalidaInventarioTests(TestCase):
    """G1-152: registrar salidas de mercancía (daño, pérdida o venta)."""

    def setUp(self):
        self.usuario = crear_usuario('sal@t.com', Usuario.Rol.ADMINISTRADOR)
        self.client.force_login(self.usuario)
        self.p = crear_producto_bd(sku='S1', nombre='Reflector', stock=10)

    def registrar(self, **cambios):
        datos = {'producto': self.p.pk, 'cantidad': '4', 'motivo': 'dano', 'observacion': ''}
        datos.update(cambios)
        return self.client.post(reverse('registrar_salida'), datos)

    def test_la_salida_descuenta_el_stock_y_queda_en_el_historial(self):
        r = self.registrar(observacion='  Golpeado   en bodega ')
        self.assertRedirects(r, reverse('salidas_lista'))
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 6)
        m = MovimientoInventario.objects.get()
        self.assertEqual((m.cantidad, m.stock_resultante, m.tipo, m.motivo, m.usuario, m.observacion),
                         (4, 6, 'salida', 'dano', self.usuario, 'Golpeado en bodega'))
        r = self.client.get(reverse('salidas_lista'))
        self.assertContains(r, '-4')
        self.assertContains(r, 'Daño')
        self.assertContains(r, 'sal@t.com')

    def test_se_aceptan_los_tres_motivos(self):
        for motivo in ('dano', 'perdida', 'venta'):
            self.registrar(cantidad='1', motivo=motivo)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 7)
        self.assertEqual(MovimientoInventario.objects.filter(tipo='salida').count(), 3)

    def test_se_puede_sacar_todo_el_stock(self):
        self.registrar(cantidad='10')
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 0)

    def test_stock_insuficiente_no_descuenta_y_reabre_el_modal(self):
        r = self.registrar(cantidad='11')
        self.assertContains(r, 'Stock insuficiente')
        self.assertContains(r, 'data-abrir="si"')
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 10)
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_datos_invalidos_no_cambian_el_stock(self):
        casos = [
            ({'cantidad': '0'}, 'mayor a 0'), ({'cantidad': '-3'}, 'mayor a 0'),
            ({'cantidad': 'abc'}, 'número entero'), ({'cantidad': ''}, 'Indica la cantidad'),
            ({'motivo': ''}, 'Selecciona el motivo'), ({'motivo': 'otro'}, 'motivo válido'),
            ({'producto': ''}, 'Selecciona el producto'), ({'producto': '9999'}, 'producto válido'),
            ({'observacion': 'x' * 201}, '200 caracteres'),
        ]
        for cambio, mensaje in casos:
            r = self.registrar(**cambio)
            self.assertContains(r, mensaje)
            self.assertContains(r, 'data-abrir="si"')
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 10)
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_un_producto_inactivo_no_tiene_salidas(self):
        Producto.objects.filter(pk=self.p.pk).update(activo=False)
        self.assertContains(self.registrar(), 'producto válido')
        self.assertEqual(MovimientoInventario.objects.count(), 0)
        with self.assertRaises(ValueError):
            MovimientoInventario.registrar_salida(self.p, 1, 'dano')

    def test_el_modelo_rechaza_cantidad_motivo_o_stock_invalidos(self):
        with self.assertRaises(ValueError):
            MovimientoInventario.registrar_salida(self.p, 0, 'dano')
        with self.assertRaises(ValueError):
            MovimientoInventario.registrar_salida(self.p, 1, 'otro')
        with self.assertRaises(ValueError):
            MovimientoInventario.registrar_salida(self.p, 11, 'venta')
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_las_salidas_no_aparecen_en_el_historial_de_entradas(self):
        self.registrar()
        self.assertContains(self.client.get(reverse('entradas_lista')), 'Aún no hay entradas registradas')
        self.assertNotContains(self.client.get(reverse('salidas_lista')), 'Aún no hay salidas registradas')

    def test_permisos_y_metodos(self):
        self.assertEqual(self.client.get(reverse('registrar_salida')).status_code, 405)
        self.client.force_login(crear_usuario('inv2@t.com', Usuario.Rol.CONTROL_INVENTARIO))
        self.assertEqual(self.client.get(reverse('salidas_lista')).status_code, 200)
        self.client.force_login(crear_usuario('cli3@t.com', Usuario.Rol.CLIENTE))
        self.assertEqual(self.client.get(reverse('salidas_lista')).status_code, 403)
        self.assertEqual(self.registrar().status_code, 403)

    def test_busqueda_y_paginacion_del_historial(self):
        Producto.objects.filter(pk=self.p.pk).update(stock=50)
        for _ in range(12):
            MovimientoInventario.registrar_salida(self.p, 1, 'venta', self.usuario)
        self.assertContains(self.client.get(reverse('salidas_lista')), 'Página 1 de 2')
        self.assertContains(self.client.get(reverse('salidas_lista'), {'q': 'S1'}), 'Reflector')
        self.assertNotContains(self.client.get(reverse('salidas_lista'), {'q': 'zzz'}), 'Reflector</p>')


# ---------------------------------------------------------------------------
# G1-153: inventario - asociación de proveedores
# ---------------------------------------------------------------------------
def datos_producto(proveedor=None, **overrides):
    datos = {
        'sku': 'A1', 'nombre': 'Panel LED', 'categoria': categoria('Eléctricos').pk,
        'precio': '80.00', 'precio_oferta': '', 'stock': '20',
        'descripcion': 'Panel cuadrado.', 'instalacion': 'Fijar al techo.',
    }
    if proveedor is not None:
        datos['proveedor'] = proveedor.pk
    datos.update(overrides)
    return datos


class AsociacionProveedorTests(TestCase):
    """G1-153: asociar productos con proveedores sin perder el vínculo al inactivarlos."""

    def setUp(self):
        self.client.force_login(crear_usuario('asoc_prov@t.com', Usuario.Rol.ADMINISTRADOR))
        self.proveedor = crear_proveedor_bd()

    def test_crear_producto_con_proveedor_guarda_el_vinculo(self):
        resp = self.client.post(reverse('crear_producto'), datos_producto(self.proveedor))
        self.assertRedirects(resp, reverse('productos_lista'))
        self.assertEqual(Producto.objects.get(sku='A1').proveedor, self.proveedor)

    def test_crear_producto_sin_proveedor_es_valido(self):
        resp = self.client.post(reverse('crear_producto'), datos_producto())
        self.assertRedirects(resp, reverse('productos_lista'))
        self.assertIsNone(Producto.objects.get(sku='A1').proveedor)

    def test_proveedor_inactivo_no_se_ofrece_para_productos_nuevos(self):
        self.proveedor.inactivar('Incumplió las entregas')
        self.assertNotIn(self.proveedor, ProductoForm().fields['proveedor'].queryset)

    def test_editar_producto_conserva_el_proveedor_inactivo(self):
        self.proveedor.inactivar('Incumplió las entregas')
        producto = crear_producto_bd(sku='A2', nombre='Lámpara', proveedor=self.proveedor)
        # El proveedor inactivo sigue disponible al editar ese producto
        self.assertIn(self.proveedor, ProductoForm(instance=producto).fields['proveedor'].queryset)
        resp = self.client.post(
            reverse('editar_producto', args=[producto.pk]),
            datos_producto(self.proveedor, sku='A2', nombre='Lámpara'),
        )
        self.assertRedirects(resp, reverse('productos_lista'))
        producto.refresh_from_db()
        self.assertEqual(producto.proveedor, self.proveedor)

    def test_inactivar_proveedor_no_borra_el_vinculo_del_producto(self):
        producto = crear_producto_bd(sku='A3', nombre='Reflector', proveedor=self.proveedor)
        self.client.post(
            reverse('inactivar_proveedor', args=[self.proveedor.pk]),
            {'motivo': 'Incumplió las entregas'},
        )
        producto.refresh_from_db()
        self.proveedor.refresh_from_db()
        self.assertEqual(producto.proveedor, self.proveedor)
        self.assertFalse(self.proveedor.activo)


# ---------------------------------------------------------------------------
# G1-155: inventario actual
# ---------------------------------------------------------------------------
class InventarioListaTests(TestCase):
    """G1-155: listar el inventario actual y exportarlo a Excel."""

    def setUp(self):
        self.client.force_login(crear_usuario('inv_lista@t.com', Usuario.Rol.ADMINISTRADOR))
        self.proveedor = crear_proveedor_bd()
        self.p = crear_producto_bd(
            sku='INV1', nombre='Cable encauchetado', precio='45.00', stock=10,
            stock_minimo=3, ubicacion='Estante A-3', proveedor=self.proveedor,
        )
        crear_producto_bd(sku='INV2', nombre='Foco agotado', precio='10.00', stock=0)

    def test_muestra_los_datos_del_inventario(self):
        resp = self.client.get(reverse('inventario_lista'))
        self.assertContains(resp, 'Inventario actual')
        self.assertContains(resp, 'Cable encauchetado')
        self.assertContains(resp, 'INV1')
        self.assertContains(resp, 'Estante A-3')
        self.assertContains(resp, 'Sin ubicación')

    def test_calcula_los_totales_del_inventario(self):
        totales = self.client.get(reverse('inventario_lista')).context['totales']
        self.assertEqual(totales['total_productos'], 2)
        self.assertEqual(totales['total_unidades'], 10)
        self.assertEqual(totales['total_valor'], 450)
        self.assertEqual(totales['total_agotados'], 1)

    def test_paginacion_de_diez_productos(self):
        for i in range(12):
            crear_producto_bd(sku=f'PG{i}', nombre=f'Producto {i}')
        resp = self.client.get(reverse('inventario_lista'))
        self.assertEqual(len(resp.context['productos']), 10)
        self.assertContains(resp, 'Página 1 de 2')

    def test_exportacion_descarga_un_xlsx_con_los_datos(self):
        resp = self.client.get(reverse('inventario_exportar'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment; filename="inventario_', resp['Content-Disposition'])

        from openpyxl import load_workbook
        libro = load_workbook(BytesIO(resp.content))
        hoja = libro.active
        self.assertEqual(hoja.title, 'Inventario')
        self.assertEqual(hoja['A1'].value, 'Código (SKU)')
        self.assertEqual(hoja.max_row, 3)  # encabezado + 2 productos
        filas = {hoja.cell(row=f, column=1).value: f for f in range(2, hoja.max_row + 1)}
        fila = filas['INV1']
        self.assertEqual(hoja.cell(row=fila, column=5).value, 'Estante A-3')
        self.assertEqual(hoja.cell(row=fila, column=6).value, 10)
        self.assertEqual(hoja.cell(row=fila, column=9).value, 450)

    def test_exportacion_respeta_los_filtros(self):
        from openpyxl import load_workbook
        resp = self.client.get(reverse('inventario_exportar'), {'q': 'INV2'})
        hoja = load_workbook(BytesIO(resp.content)).active
        self.assertEqual(hoja.max_row, 2)
        self.assertEqual(hoja.cell(row=2, column=2).value, 'Foco agotado')

    def test_permisos_del_inventario(self):
        self.client.force_login(crear_usuario('inv_ok@t.com', Usuario.Rol.CONTROL_INVENTARIO))
        self.assertEqual(self.client.get(reverse('inventario_lista')).status_code, 200)
        self.assertEqual(self.client.get(reverse('inventario_exportar')).status_code, 200)
        self.client.force_login(crear_usuario('cli_inv@t.com', Usuario.Rol.CLIENTE))
        self.assertEqual(self.client.get(reverse('inventario_lista')).status_code, 403)
        self.assertEqual(self.client.get(reverse('inventario_exportar')).status_code, 403)

    def test_usuario_sin_sesion_es_redirigido_al_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('inventario_lista')).status_code, 302)


# ---------------------------------------------------------------------------
# G1-156: búsquedas avanzadas y filtros
# ---------------------------------------------------------------------------
class InventarioFiltrosTests(TestCase):
    """G1-156: filtros combinables del inventario actual."""

    def setUp(self):
        self.client.force_login(crear_usuario('inv_filtros@t.com', Usuario.Rol.ADMINISTRADOR))
        self.proveedor = crear_proveedor_bd()
        self.cable = crear_producto_bd(
            sku='F1', nombre='Cable THW', categoria=categoria('Eléctricos'),
            precio='45.00', stock=10, stock_minimo=2,
            ubicacion='Estante A-3', proveedor=self.proveedor,
        )
        self.lampara = crear_producto_bd(
            sku='F2', nombre='Lámpara colgante', categoria=categoria('Interiores'),
            precio='120.00', stock=0, ubicacion='Bodega 2',
        )

    def nombres(self, **filtros):
        resp = self.client.get(reverse('inventario_lista'), filtros)
        return [p.nombre for p in resp.context['productos']]

    def test_busqueda_por_nombre_sku_y_ubicacion(self):
        self.assertEqual(self.nombres(q='Cable'), ['Cable THW'])
        self.assertEqual(self.nombres(q='F2'), ['Lámpara colgante'])
        self.assertEqual(self.nombres(q='Estante'), ['Cable THW'])

    def test_filtro_por_categoria(self):
        self.assertEqual(self.nombres(categoria=categoria('Interiores').pk), ['Lámpara colgante'])

    def test_filtro_por_proveedor(self):
        self.assertEqual(self.nombres(proveedor=self.proveedor.pk), ['Cable THW'])

    def test_filtro_por_estado(self):
        Producto.objects.filter(pk=self.lampara.pk).update(activo=False)
        self.assertEqual(self.nombres(estado='inactivos'), ['Lámpara colgante'])
        self.assertEqual(self.nombres(estado='activos'), ['Cable THW'])

    def test_filtro_por_existencia(self):
        self.assertEqual(self.nombres(existencia='agotados'), ['Lámpara colgante'])
        self.assertEqual(self.nombres(existencia='disponibles'), ['Cable THW'])
        self.assertEqual(self.nombres(existencia='bajo'), [])

    def test_filtro_por_stock_bajo(self):
        Producto.objects.filter(pk=self.cable.pk).update(stock=1)
        self.assertEqual(self.nombres(existencia='bajo'), ['Cable THW'])

    def test_filtro_por_rango_de_precio(self):
        self.assertEqual(self.nombres(precio_min='100'), ['Lámpara colgante'])
        self.assertEqual(self.nombres(precio_max='50'), ['Cable THW'])
        self.assertEqual(self.nombres(precio_min='50', precio_max='100'), [])

    def test_filtros_combinados(self):
        self.assertEqual(
            self.nombres(q='a', categoria=categoria('Eléctricos').pk, existencia='disponibles'),
            ['Cable THW'],
        )

    def test_parametros_invalidos_se_ignoran(self):
        self.assertEqual(len(self.nombres(categoria='hacker', proveedor='9999',
                                         estado='otro', existencia='otro',
                                         precio_min='abc', precio_max='-5')), 2)
        self.assertEqual(len(self.nombres(precio_min='NaN', precio_max='Infinity')), 2)

    def test_los_filtros_se_conservan_en_la_paginacion(self):
        for i in range(12):
            crear_producto_bd(sku=f'PF{i}', nombre=f'Cable extra {i}')
        resp = self.client.get(reverse('inventario_lista'), {'q': 'Cable'})
        self.assertContains(resp, 'q=Cable')
        self.assertContains(resp, 'Página 1 de 2')


# ---------------------------------------------------------------------------
# G1-157: alertas automáticas de stock bajo
# ---------------------------------------------------------------------------
class StockBajoTests(TestCase):
    """G1-157: alertar cuando un producto cruza su stock mínimo."""

    def setUp(self):
        self.admin = crear_usuario('stock_admin@t.com', Usuario.Rol.ADMINISTRADOR)
        self.control = crear_usuario('stock_control@t.com', Usuario.Rol.CONTROL_INVENTARIO)
        self.cliente = crear_usuario('stock_cliente@t.com', Usuario.Rol.CLIENTE)
        self.p = crear_producto_bd(sku='S1', nombre='Reflector', stock=10, stock_minimo=5)

    def test_stock_bajo_solo_cuando_hay_minimo_configurado(self):
        self.assertFalse(self.p.stock_bajo)
        self.p.stock = 4
        self.assertTrue(self.p.stock_bajo)
        self.p.stock = 5  # igual al mínimo: todavía no está bajo
        self.assertFalse(self.p.stock_bajo)
        self.p.stock_minimo = 0
        self.p.stock = 0
        self.assertFalse(self.p.stock_bajo)

    def test_cruzar_el_minimo_notifica_a_quienes_gestionan_inventario(self):
        MovimientoInventario.registrar_salida(self.p, 6, 'venta', self.admin)
        self.p.refresh_from_db()
        self.assertEqual(self.p.stock, 4)
        destinatarios = set(Notificacion.objects.values_list('destinatario__email', flat=True))
        self.assertEqual(destinatarios, {self.admin.email, self.control.email})
        self.assertNotIn(self.cliente.email, destinatarios)
        notificacion = Notificacion.objects.first()
        self.assertEqual(notificacion.tipo, Notificacion.Tipo.GENERAL)
        self.assertIn('Reflector', notificacion.mensaje)
        self.assertIn('4 unidades', notificacion.mensaje)

    def test_no_repite_la_alerta_si_ya_estaba_bajo(self):
        MovimientoInventario.registrar_salida(self.p, 6, 'venta', self.admin)
        cantidad = Notificacion.objects.count()
        MovimientoInventario.registrar_salida(self.p, 1, 'venta', self.admin)
        self.assertEqual(Notificacion.objects.count(), cantidad)

    def test_no_alerta_si_el_minimo_es_cero(self):
        Producto.objects.filter(pk=self.p.pk).update(stock_minimo=0)
        MovimientoInventario.registrar_salida(self.p, 10, 'venta', self.admin)
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_no_alerta_si_la_salida_no_llega_al_minimo(self):
        MovimientoInventario.registrar_salida(self.p, 2, 'venta', self.admin)
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_la_lista_marca_el_producto_con_stock_bajo(self):
        Producto.objects.filter(pk=self.p.pk).update(stock=4)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('inventario_lista'))
        self.assertTrue(resp.context['hay_stock_bajo'])
        self.assertContains(resp, 'Stock bajo')
        self.assertContains(resp, 'Hay productos con stock bajo')

    def test_la_alerta_no_aparece_si_no_hay_productos_bajos(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('inventario_lista'))
        self.assertFalse(resp.context['hay_stock_bajo'])
        self.assertNotContains(resp, 'Hay productos con stock bajo')