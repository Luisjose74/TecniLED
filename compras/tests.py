import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from Usuarios.models import Usuario
from productos.models import Categoria, Producto, Proveedor

from .forms import DetalleEdicionFormSet, DetalleFormSet, OrdenCompraForm, RemisionForm
from .models import OrdenCompra, validar_tamano_remision

# Los archivos de los tests se guardan aquí y se borran al terminar
MEDIA_TEMPORAL = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)


def crear_usuario(correo, rol):
    return Usuario.objects.create_user(
        username=correo, email=correo, password='Prueba123!', rol=rol
    )


def categoria(nombre):
    return Categoria.objects.get_or_create(nombre=nombre)[0]


def crear_producto(sku, nombre, precio='1000.00'):
    return Producto.objects.create(
        sku=sku,
        nombre=nombre,
        categoria=categoria('Pruebas de compras'),
        precio=Decimal(precio),
        stock=100,
        descripcion='Producto de prueba.',
        instalacion='Sin instalación.',
    )


class BaseComprasTests(TestCase):
    """Datos y utilidades compartidas por las pruebas de la app compras."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = crear_usuario('compras.admin@tecniled.com', Usuario.Rol.ADMINISTRADOR)
        cls.cliente = crear_usuario('compras.cliente@tecniled.com', Usuario.Rol.CLIENTE)
        cls.proveedor = Proveedor.objects.create(
            nombre='Distribuidora Eléctrica S.A.S.', nit='900123456-7',
        )
        cls.otro_proveedor = Proveedor.objects.create(
            nombre='Ferretería Central', nit='800555-1',
        )
        cls.producto = crear_producto('C1', 'Cable THW Calibre 12')
        cls.producto2 = crear_producto('C2', 'Lámpara LED 20W', '25000.00')

    def setUp(self):
        self.client.force_login(self.admin)

    def crear_orden(self, numero='F-001', fecha=None, proveedor=None,
                    estado=OrdenCompra.Estado.PENDIENTE, lineas=None):
        orden = OrdenCompra.objects.create(
            numero_factura=numero,
            fecha=fecha or date(2026, 10, 1),
            proveedor=proveedor or self.proveedor,
            estado=estado,
        )
        lineas = lineas or [(self.producto, 2, Decimal('1000.00'))]
        for producto, cantidad, precio in lineas:
            orden.detalles.create(
                producto=producto, cantidad=cantidad, precio_unitario=precio,
            )
        orden.calcular_total()
        return orden

    def datos_edicion(self, orden, lineas):
        """Arma el POST del formulario de edición con su formset."""
        formset = DetalleEdicionFormSet(instance=orden)
        prefijo = formset.prefix
        datos = {
            'numero_factura': orden.numero_factura,
            'fecha': orden.fecha.strftime('%Y-%m-%d'),
            'proveedor': str(orden.proveedor_id),
            f'{prefijo}-TOTAL_FORMS': str(len(lineas)),
            f'{prefijo}-INITIAL_FORMS': str(
                sum(1 for linea in lineas if linea.get('id'))
            ),
            f'{prefijo}-MIN_NUM_FORMS': '0',
            f'{prefijo}-MAX_NUM_FORMS': '1000',
        }
        for indice, linea in enumerate(lineas):
            datos[f'{prefijo}-{indice}-producto'] = str(linea['producto'].pk)
            datos[f'{prefijo}-{indice}-cantidad'] = str(linea['cantidad'])
            datos[f'{prefijo}-{indice}-precio_unitario'] = str(linea['precio'])
            if linea.get('id'):
                datos[f'{prefijo}-{indice}-id'] = str(linea['id'])
                datos[f'{prefijo}-{indice}-orden'] = str(orden.pk)
            if linea.get('DELETE'):
                datos[f'{prefijo}-{indice}-DELETE'] = 'on'
        return datos


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ListadoYFiltrosTests(BaseComprasTests):
    """G1-161: listado de compras por periodo, con estado y exportación."""

    def setUp(self):
        super().setUp()
        self.orden_septiembre = self.crear_orden(
            'F-SEP', date(2026, 9, 15), lineas=[
                (self.producto, 1, Decimal('1000.00')),
            ],
        )
        self.orden_octubre = self.crear_orden(
            'F-OCT', date(2026, 10, 5), self.otro_proveedor,
            OrdenCompra.Estado.RECIBIDA, lineas=[
                (self.producto2, 3, Decimal('25000.00')),
            ],
        )

    def test_listado_muestra_todas_las_compras_con_su_estado(self):
        resp = self.client.get(reverse('ordenes_lista'))
        self.assertEqual(resp.status_code, 200)
        for orden in (self.orden_septiembre, self.orden_octubre):
            self.assertContains(resp, orden.numero_factura)
        self.assertContains(resp, 'Pendiente')
        self.assertContains(resp, 'Recibida')

    def test_filtra_por_rango_de_fechas(self):
        resp = self.client.get(reverse('ordenes_lista'), {
            'desde': '2026-10-01', 'hasta': '2026-10-31',
        })
        self.assertContains(resp, 'F-OCT')
        self.assertNotContains(resp, 'F-SEP')

    def test_filtra_por_proveedor(self):
        resp = self.client.get(reverse('ordenes_lista'), {
            'proveedor': self.otro_proveedor.pk,
        })
        self.assertContains(resp, 'F-OCT')
        self.assertNotContains(resp, 'F-SEP')

    def test_filtra_por_estado(self):
        resp = self.client.get(reverse('ordenes_lista'), {'estado': 'recibida'})
        self.assertContains(resp, 'F-OCT')
        self.assertNotContains(resp, 'F-SEP')

    def test_fecha_inicial_mayor_a_la_final_avisa_al_usuario(self):
        resp = self.client.get(reverse('ordenes_lista'), {
            'desde': '2026-10-31', 'hasta': '2026-10-01',
        })
        self.assertContains(resp, 'La fecha inicial es posterior a la fecha final')
        self.assertNotContains(resp, 'F-SEP')
        self.assertNotContains(resp, 'F-OCT')

    def test_exportar_excel_respeta_los_filtros(self):
        resp = self.client.get(reverse('exportar_ordenes'), {
            'formato': 'xlsx', 'desde': '2026-10-01', 'hasta': '2026-10-31',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('compras_20261001_20261031.xlsx', resp['Content-Disposition'])

        libro = load_workbook(BytesIO(resp.content))
        hoja = libro.active
        self.assertEqual(hoja['A4'].value, 'N.º orden/factura')
        self.assertEqual(hoja['E4'].value, 'Total')
        self.assertEqual(hoja['A5'].value, 'F-OCT')
        self.assertEqual(hoja['D5'].value, 'Recibida')
        self.assertEqual(hoja['A6'].value, None)
        self.assertEqual(hoja['D6'].value, 'Total general')

    def test_exportar_excel_incluye_todas_las_compras_sin_filtros(self):
        resp = self.client.get(reverse('exportar_ordenes'), {'formato': 'xlsx'})
        libro = load_workbook(BytesIO(resp.content))
        valores = [celda.value for celda in libro.active['A']]
        self.assertIn('F-SEP', valores)
        self.assertIn('F-OCT', valores)

    def test_exportar_pdf_genera_un_archivo_pdf(self):
        resp = self.client.get(reverse('exportar_ordenes'), {'formato': 'pdf'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF-'))
        self.assertIn('.pdf', resp['Content-Disposition'])

    def test_exportar_ignora_filtros_con_valores_invalidos(self):
        resp = self.client.get(reverse('exportar_ordenes'), {
            'formato': 'xlsx', 'estado': 'inventado', 'desde': '31/02/2026',
        })
        self.assertEqual(resp.status_code, 200)
        libro = load_workbook(BytesIO(resp.content))
        valores = [celda.value for celda in libro.active['A']]
        self.assertIn('F-SEP', valores)
        self.assertIn('F-OCT', valores)

    def test_exportar_con_formato_invalido_redirige_al_listado(self):
        resp = self.client.get(reverse('exportar_ordenes'), {'formato': 'docx'})
        self.assertRedirects(resp, reverse('ordenes_lista'))

    def test_exportar_requiere_permiso_de_compras(self):
        self.client.force_login(self.cliente)
        resp = self.client.get(reverse('exportar_ordenes'), {'formato': 'xlsx'})
        self.assertEqual(resp.status_code, 403)

    def test_listado_requiere_permiso_de_compras(self):
        self.client.force_login(self.cliente)
        resp = self.client.get(reverse('ordenes_lista'))
        self.assertEqual(resp.status_code, 403)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DetalleOrdenTests(BaseComprasTests):
    def setUp(self):
        super().setUp()
        self.orden = self.crear_orden('F-DET', lineas=[
            (self.producto, 4, Decimal('1500.00')),
            (self.producto2, 2, Decimal('25000.00')),
        ])

    def test_detalle_muestra_productos_y_total(self):
        resp = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'admin_base.html')
        self.assertContains(resp, 'F-DET')
        self.assertContains(resp, self.proveedor.nombre)
        self.assertContains(resp, self.producto.nombre)
        self.assertContains(resp, self.producto2.nombre)
        self.assertContains(resp, '56000,00')
        self.assertContains(resp, 'Esta orden todavía no tiene remisión')
        self.assertContains(
            resp,
            f"{reverse('reportes_inicio')}?tipo=compras&proveedor={self.proveedor.pk}"
        )

    def test_detalle_de_orden_inexistente_devuelve_404(self):
        resp = self.client.get(reverse('orden_detalle', args=[999999]))
        self.assertEqual(resp.status_code, 404)

    def test_detalle_requiere_permiso_de_compras(self):
        self.client.force_login(self.cliente)
        resp = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
        self.assertEqual(resp.status_code, 403)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class EditarOrdenTests(BaseComprasTests):
    """G1-164: editar una orden pendiente y bloquear las demás."""

    def setUp(self):
        super().setUp()
        self.orden = self.crear_orden('F-EDIT', lineas=[
            (self.producto, 2, Decimal('1000.00')),
        ])

    def test_abre_el_formulario_de_una_orden_pendiente(self):
        resp = self.client.get(reverse('editar_orden', args=[self.orden.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'admin_base.html')
        self.assertContains(resp, 'Guardar cambios')
        self.assertContains(resp, self.producto.nombre)

    def test_guarda_cambios_y_recalcula_el_total(self):
        datos = self.datos_edicion(self.orden, [
            {'id': self.orden.detalles.first().pk, 'producto': self.producto,
             'cantidad': 5, 'precio': '1200.00'},
            {'producto': self.producto2, 'cantidad': 2, 'precio': '25000.00'},
        ])
        datos['proveedor'] = str(self.otro_proveedor.pk)

        resp = self.client.post(
            reverse('editar_orden', args=[self.orden.pk]), datos,
        )
        self.assertRedirects(resp, reverse('orden_detalle', args=[self.orden.pk]))

        self.orden.refresh_from_db()
        self.assertEqual(self.orden.proveedor, self.otro_proveedor)
        self.assertEqual(self.orden.total, Decimal('56000.00'))
        self.assertEqual(self.orden.detalles.count(), 2)
        linea = self.orden.detalles.get(producto=self.producto)
        self.assertEqual(linea.cantidad, 5)
        self.assertEqual(linea.precio_unitario, Decimal('1200.00'))

    def test_permite_eliminar_una_linea_con_delete(self):
        linea = self.orden.detalles.first()
        datos = self.datos_edicion(self.orden, [
            {'id': linea.pk, 'producto': self.producto,
             'cantidad': 2, 'precio': '1000.00', 'DELETE': True},
            {'producto': self.producto2, 'cantidad': 1, 'precio': '25000.00'},
        ])
        resp = self.client.post(
            reverse('editar_orden', args=[self.orden.pk]), datos,
        )
        self.assertRedirects(resp, reverse('orden_detalle', args=[self.orden.pk]))
        self.assertEqual(self.orden.detalles.count(), 1)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.total, Decimal('25000.00'))

    def test_no_permite_quedarse_sin_productos(self):
        linea = self.orden.detalles.first()
        datos = self.datos_edicion(self.orden, [
            {'id': linea.pk, 'producto': self.producto,
             'cantidad': 2, 'precio': '1000.00', 'DELETE': True},
        ])
        resp = self.client.post(
            reverse('editar_orden', args=[self.orden.pk]), datos,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Debes agregar al menos un producto')
        self.assertEqual(self.orden.detalles.count(), 1)

    def test_rechaza_productos_repetidos(self):
        linea = self.orden.detalles.first()
        datos = self.datos_edicion(self.orden, [
            {'id': linea.pk, 'producto': self.producto,
             'cantidad': 2, 'precio': '1000.00'},
            {'producto': self.producto, 'cantidad': 3, 'precio': '1000.00'},
        ])
        resp = self.client.post(
            reverse('editar_orden', args=[self.orden.pk]), datos,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Hay un producto repetido')
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.total, Decimal('2000.00'))

    def test_no_edita_una_orden_recibida_y_avisa(self):
        self.orden.estado = OrdenCompra.Estado.RECIBIDA
        self.orden.save(update_fields=['estado'])

        resp = self.client.get(
            reverse('editar_orden', args=[self.orden.pk]), follow=True,
        )
        self.assertRedirects(resp, reverse('orden_detalle', args=[self.orden.pk]))
        self.assertContains(resp, 'ya no se puede modificar')

        datos = self.datos_edicion(self.orden, [
            {'id': self.orden.detalles.first().pk, 'producto': self.producto,
             'cantidad': 99, 'precio': '1.00'},
        ])
        self.client.post(reverse('editar_orden', args=[self.orden.pk]), datos)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.total, Decimal('2000.00'))

    def test_no_edita_una_orden_anulada_y_avisa(self):
        self.orden.estado = OrdenCompra.Estado.ANULADA
        self.orden.save(update_fields=['estado'])

        resp = self.client.get(
            reverse('editar_orden', args=[self.orden.pk]), follow=True,
        )
        self.assertContains(resp, 'ya no se puede modificar')
        self.assertContains(resp, 'anulada')

    def test_conserva_el_proveedor_inactivo_al_editar(self):
        Proveedor.objects.filter(pk=self.proveedor.pk).update(activo=False)
        resp = self.client.get(reverse('editar_orden', args=[self.orden.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'value="{self.proveedor.pk}"')

    def test_conserva_el_producto_inactivo_al_editar(self):
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        linea = self.orden.detalles.first()
        resp = self.client.get(reverse('editar_orden', args=[self.orden.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'value="{self.producto.pk}" selected')

        datos = self.datos_edicion(self.orden, [
            {'id': linea.pk, 'producto': self.producto,
             'cantidad': 3, 'precio': '1000.00'},
        ])
        resp = self.client.post(
            reverse('editar_orden', args=[self.orden.pk]), datos,
        )
        self.assertRedirects(resp, reverse('orden_detalle', args=[self.orden.pk]))
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.total, Decimal('3000.00'))

    def test_no_permite_elegir_otro_proveedor_inactivo(self):
        Proveedor.objects.filter(pk=self.otro_proveedor.pk).update(activo=False)
        datos = self.datos_edicion(self.orden, [
            {'id': self.orden.detalles.first().pk, 'producto': self.producto,
             'cantidad': 2, 'precio': '1000.00'},
        ])
        datos['proveedor'] = str(self.otro_proveedor.pk)
        resp = self.client.post(
            reverse('editar_orden', args=[self.orden.pk]), datos,
        )
        self.assertEqual(resp.status_code, 200)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.proveedor, self.proveedor)

    def test_editar_requiere_permiso_de_compras(self):
        self.client.force_login(self.cliente)
        resp = self.client.get(reverse('editar_orden', args=[self.orden.pk]))
        self.assertEqual(resp.status_code, 403)


def pdf_valido(nombre='remision.pdf'):
    return SimpleUploadedFile(
        nombre,
        b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n',
        content_type='application/pdf',
    )


def imagen_valida(nombre='remision.png'):
    return SimpleUploadedFile(
        nombre,
        b'\x89PNG\r\n\x1a\n' + b'0' * 32,
        content_type='image/png',
    )


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CambioEstadoOrdenTests(BaseComprasTests):
    """Marcar una orden como recibida o anulada desde el detalle."""

    def setUp(self):
        super().setUp()
        self.orden = self.crear_orden('F-EST')

    def test_recibir_marca_la_orden_como_recibida(self):
        resp = self.client.post(
            reverse('recibir_orden', args=[self.orden.pk]), follow=True,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, OrdenCompra.Estado.RECIBIDA)
        self.assertRedirects(
            resp, reverse('orden_detalle', args=[self.orden.pk]),
        )
        self.assertContains(resp, 'se marcó como recibida')

    def test_anular_marca_la_orden_como_anulada(self):
        resp = self.client.post(
            reverse('anular_orden', args=[self.orden.pk]), follow=True,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, OrdenCompra.Estado.ANULADA)
        self.assertContains(resp, 'se marcó como anulada')

    def test_no_se_puede_cambiar_el_estado_de_una_orden_recibida(self):
        self.orden.estado = OrdenCompra.Estado.RECIBIDA
        self.orden.save(update_fields=['estado'])
        resp = self.client.post(
            reverse('anular_orden', args=[self.orden.pk]), follow=True,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, OrdenCompra.Estado.RECIBIDA)
        self.assertContains(resp, 'ya está recibida')

    def test_no_se_puede_volver_a_recibir_una_orden_anulada(self):
        self.orden.estado = OrdenCompra.Estado.ANULADA
        self.orden.save(update_fields=['estado'])
        resp = self.client.post(
            reverse('recibir_orden', args=[self.orden.pk]), follow=True,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, OrdenCompra.Estado.ANULADA)
        self.assertContains(resp, 'ya está anulada')

    def test_los_cambios_de_estado_solo_aceptan_post(self):
        for nombre in ('recibir_orden', 'anular_orden'):
            resp = self.client.get(reverse(nombre, args=[self.orden.pk]))
            self.assertEqual(resp.status_code, 405, nombre)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, OrdenCompra.Estado.PENDIENTE)

    def test_requiere_permiso_para_cambiar_el_estado(self):
        self.client.force_login(self.cliente)
        for nombre in ('recibir_orden', 'anular_orden'):
            resp = self.client.post(reverse(nombre, args=[self.orden.pk]))
            self.assertEqual(resp.status_code, 403, nombre)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, OrdenCompra.Estado.PENDIENTE)

    def test_el_detalle_muestra_las_acciones_solo_si_esta_pendiente(self):
        resp = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
        self.assertContains(resp, 'Marcar como recibida')
        self.assertContains(resp, 'Anular orden')

        self.orden.estado = OrdenCompra.Estado.RECIBIDA
        self.orden.save(update_fields=['estado'])
        resp = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
        self.assertNotContains(resp, 'Marcar como recibida')
        self.assertNotContains(resp, 'Anular orden')


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    MEDIA_ROOT=MEDIA_TEMPORAL,
)
class RemisionTests(BaseComprasTests):
    """G1-159: adjuntar y consultar la remisión del proveedor."""

    def setUp(self):
        super().setUp()
        self.orden = self.crear_orden('F-REM')

    def test_formulario_de_remision_carga(self):
        resp = self.client.get(reverse('adjuntar_remision', args=[self.orden.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'enctype="multipart/form-data"')
        self.assertContains(resp, 'for="id_remision"')

    def test_adjunta_un_pdf_y_lo_muestra_en_el_detalle(self):
        resp = self.client.post(
            reverse('adjuntar_remision', args=[self.orden.pk]),
            {'remision': pdf_valido()},
        )
        self.assertRedirects(resp, reverse('orden_detalle', args=[self.orden.pk]))

        self.orden.refresh_from_db()
        self.assertTrue(self.orden.tiene_remision)
        self.assertTrue(self.orden.remision.name.startswith('remisiones/'))
        self.assertTrue(os.path.exists(self.orden.remision.path))

        detalle = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
        self.assertContains(detalle, 'remision.pdf')
        self.assertContains(detalle, 'Descargar')
        self.assertContains(detalle, self.orden.remision.url)

    def test_adjunta_una_imagen(self):
        resp = self.client.post(
            reverse('adjuntar_remision', args=[self.orden.pk]),
            {'remision': imagen_valida()},
        )
        self.assertRedirects(resp, reverse('orden_detalle', args=[self.orden.pk]))
        self.orden.refresh_from_db()
        self.assertTrue(self.orden.remision_es_imagen)
        detalle = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
        self.assertContains(detalle, '<img')
        self.assertContains(detalle, 'Vista previa de la remisión')

    def test_rechaza_un_pdf_falso(self):
        falso = SimpleUploadedFile(
            'remision.pdf', b'Esto no es un PDF de verdad',
            content_type='application/pdf',
        )
        resp = self.client.post(
            reverse('adjuntar_remision', args=[self.orden.pk]),
            {'remision': falso},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'El archivo no es un PDF o una imagen JPG/PNG válida')
        self.orden.refresh_from_db()
        self.assertFalse(self.orden.tiene_remision)

    def test_rechaza_extensiones_no_permitidas(self):
        archivo = SimpleUploadedFile(
            'remision.txt', b'%PDF-1.4', content_type='text/plain',
        )
        resp = self.client.post(
            reverse('adjuntar_remision', args=[self.orden.pk]),
            {'remision': archivo},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Solo se permiten archivos PDF o imágenes JPG/PNG')
        self.orden.refresh_from_db()
        self.assertFalse(self.orden.tiene_remision)

    def test_rechaza_archivos_de_mas_de_5_mb(self):
        grande = SimpleUploadedFile(
            'remision.pdf', b'%PDF-1.4\n' + b'0' * (5 * 1024 * 1024),
            content_type='application/pdf',
        )
        resp = self.client.post(
            reverse('adjuntar_remision', args=[self.orden.pk]),
            {'remision': grande},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'El archivo no puede superar los 5 MB')
        self.orden.refresh_from_db()
        self.assertFalse(self.orden.tiene_remision)

    def test_reemplazar_la_remision_borra_el_archivo_anterior(self):
        self.client.post(
            reverse('adjuntar_remision', args=[self.orden.pk]),
            {'remision': pdf_valido('primera.pdf')},
        )
        self.orden.refresh_from_db()
        ruta_anterior = self.orden.remision.path
        self.assertTrue(os.path.exists(ruta_anterior))

        self.client.post(
            reverse('adjuntar_remision', args=[self.orden.pk]),
            {'remision': imagen_valida('segunda.png')},
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.nombre_remision, 'segunda.png')
        self.assertFalse(os.path.exists(ruta_anterior))
        self.assertTrue(os.path.exists(self.orden.remision.path))

    def test_remision_requiere_permiso_de_compras(self):
        self.client.force_login(self.cliente)
        resp = self.client.get(reverse('adjuntar_remision', args=[self.orden.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_remision_form_exige_archivo(self):
        form = RemisionForm(data={}, instance=self.orden)
        self.assertFalse(form.is_valid())
        self.assertIn('remision', form.errors)

    def test_validador_de_tamano(self):
        class ArchivoGrande:
            size = 6 * 1024 * 1024

        with self.assertRaisesMessage(ValidationError, '5 MB'):
            validar_tamano_remision(ArchivoGrande())


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class HistorialProveedorTests(BaseComprasTests):
    """G1-162: historial de compras filtrado por proveedor."""

    def setUp(self):
        super().setUp()
        self.orden = self.crear_orden(
            'F-HIS', date(2026, 10, 10), lineas=[
                (self.producto, 4, Decimal('1500.00')),
                (self.producto2, 2, Decimal('25000.00')),
            ],
        )

    def test_sin_proveedor_pide_seleccionar_uno(self):
        resp = self.client.get(reverse('reportes_inicio'), {'tipo': 'compras'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Selecciona un proveedor')

    def test_muestra_fecha_producto_cantidad_y_valores(self):
        resp = self.client.get(
            reverse('reportes_inicio'),
            {'tipo': 'compras', 'proveedor': self.proveedor.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '10/10/2026')
        self.assertContains(resp, self.producto.nombre)
        self.assertContains(resp, self.producto2.nombre)
        self.assertContains(resp, '1500,00')
        self.assertContains(resp, '25000,00')
        self.assertContains(resp, '56000,00')  # total de la compra
        self.assertContains(resp, 'F-HIS')

    def test_informa_cuando_el_proveedor_no_tiene_compras(self):
        resp = self.client.get(
            reverse('reportes_inicio'),
            {'tipo': 'compras', 'proveedor': self.otro_proveedor.pk},
        )
        self.assertContains(resp, 'no tiene compras registradas')
        self.assertContains(resp, self.otro_proveedor.nombre)

    def test_filtra_el_historial_por_fechas(self):
        resp = self.client.get(reverse('reportes_inicio'), {
            'tipo': 'compras',
            'proveedor': self.proveedor.pk,
            'desde': '2026-11-01',
            'hasta': '2026-11-30',
        })
        self.assertContains(resp, 'no tiene compras registradas')
        self.assertContains(resp, 'en el periodo consultado')

    def test_resumen_de_compras_del_proveedor(self):
        resp = self.client.get(
            reverse('reportes_inicio'),
            {'tipo': 'compras', 'proveedor': self.proveedor.pk},
        )
        self.assertEqual(resp.context['resumen']['compras'], 1)
        self.assertEqual(resp.context['resumen']['productos'], 6)
        self.assertEqual(resp.context['resumen']['total'], Decimal('56000.00'))

    def test_proveedores_lista_enlaza_al_historial(self):
        resp = self.client.get(reverse('proveedores_lista'))
        self.assertContains(
            resp,
            f"{reverse('reportes_inicio')}?tipo=compras&proveedor={self.proveedor.pk}",
        )
        self.assertContains(resp, 'Ver historial de compras')

    def test_historial_requiere_permiso_de_compras(self):
        self.client.force_login(self.cliente)
        resp = self.client.get(reverse('reportes_inicio'), {'tipo': 'compras'})
        self.assertEqual(resp.status_code, 403)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ModeloOrdenCompraTests(BaseComprasTests):
    def test_es_editable_solo_en_pendiente(self):
        orden = self.crear_orden('F-EST')
        self.assertTrue(orden.es_editable)
        orden.estado = OrdenCompra.Estado.RECIBIDA
        self.assertFalse(orden.es_editable)
        orden.estado = OrdenCompra.Estado.ANULADA
        self.assertFalse(orden.es_editable)

    def test_calcular_total_suma_los_subtotales(self):
        orden = self.crear_orden('F-TOT', lineas=[
            (self.producto, 3, Decimal('1000.00')),
            (self.producto2, 1, Decimal('25000.00')),
        ])
        self.assertEqual(orden.total, Decimal('28000.00'))

    def test_propiedades_de_la_remision(self):
        orden = self.crear_orden('F-SIN')
        self.assertFalse(orden.tiene_remision)
        self.assertEqual(orden.nombre_remision, '')
        self.assertFalse(orden.remision_es_imagen)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FormulariosComprasTests(BaseComprasTests):
    def test_formset_de_creacion_no_permite_borrar_lineas(self):
        self.assertFalse(DetalleFormSet().can_delete)

    def test_formset_de_edicion_permite_borrar_lineas(self):
        self.assertTrue(DetalleEdicionFormSet().can_delete)

    def test_formulario_de_orden_excluye_proveedores_inactivos(self):
        Proveedor.objects.filter(pk=self.otro_proveedor.pk).update(activo=False)
        form = OrdenCompraForm()
        self.assertIn(self.proveedor, form.fields['proveedor'].queryset)
        self.assertNotIn(self.otro_proveedor, form.fields['proveedor'].queryset)
