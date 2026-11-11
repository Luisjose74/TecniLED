from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from Usuarios.models import Usuario
from compras.models import OrdenCompra
from productos.models import Categoria, Producto, Proveedor


def crear_usuario(correo, rol):
    return Usuario.objects.create_user(
        username=correo, email=correo, password='Prueba123!', rol=rol
    )


class ReportesTests(TestCase):
    """Reportes: tarjetas por permiso y el historial de compras integrado."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = crear_usuario('reportes.admin@tecniled.com', Usuario.Rol.ADMINISTRADOR)
        cls.inventario = crear_usuario(
            'reportes.inventario@tecniled.com', Usuario.Rol.CONTROL_INVENTARIO
        )
        cls.cliente = crear_usuario('reportes.cliente@tecniled.com', Usuario.Rol.CLIENTE)

        cls.proveedor = Proveedor.objects.create(
            nombre='Distribuidora Eléctrica S.A.S.', nit='900123456-7',
        )
        cls.otro_proveedor = Proveedor.objects.create(
            nombre='Ferretería Central', nit='800555-1',
        )
        categoria, _ = Categoria.objects.get_or_create(nombre='Pruebas de reportes')
        cls.producto = Producto.objects.create(
            sku='R1',
            nombre='Cable THW Calibre 12',
            categoria=categoria,
            precio=Decimal('1000.00'),
            stock=100,
            descripcion='Producto de prueba.',
            instalacion='Sin instalación.',
        )
        cls.orden = OrdenCompra.objects.create(
            numero_factura='R-001',
            fecha=date(2026, 10, 5),
            proveedor=cls.proveedor,
            estado=OrdenCompra.Estado.PENDIENTE,
        )
        cls.orden.detalles.create(
            producto=cls.producto, cantidad=3, precio_unitario=Decimal('1000.00'),
        )
        cls.orden.calcular_total()

    def test_admin_ve_la_tarjeta_de_compras(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('reportes_inicio'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Historial de compras por proveedor.')
        self.assertContains(resp, '?tipo=compras')

    def test_reporte_de_compras_muestra_el_historial(self):
        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse('reportes_inicio'),
            {'tipo': 'compras', 'proveedor': self.proveedor.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['tipo'], 'compras')
        self.assertContains(resp, 'Historial de compras de Distribuidora Eléctrica S.A.S.')
        self.assertContains(resp, 'R-001')
        self.assertContains(resp, '05/10/2026')
        self.assertEqual(resp.context['resumen']['compras'], 1)

    def test_sin_proveedor_invita_a_seleccionar_uno(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('reportes_inicio'), {'tipo': 'compras'})
        self.assertContains(resp, 'Selecciona un proveedor para consultar su historial')

    def test_control_inventario_no_ve_la_tarjeta_de_compras(self):
        self.client.force_login(self.inventario)
        resp = self.client.get(reverse('reportes_inicio'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Inventario actual')
        self.assertNotContains(resp, '?tipo=compras')

    def test_control_inventario_recibe_403_en_el_reporte_de_compras(self):
        self.client.force_login(self.inventario)
        resp = self.client.get(reverse('reportes_inicio'), {'tipo': 'compras'})
        self.assertEqual(resp.status_code, 403)

    def test_cliente_no_puede_entrar_a_reportes(self):
        self.client.force_login(self.cliente)
        resp = self.client.get(reverse('reportes_inicio'))
        self.assertEqual(resp.status_code, 403)

    def test_tipo_desconocido_no_muestra_reporte(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('reportes_inicio'), {'tipo': 'no-existe'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['tipo'], '')
        self.assertContains(resp, 'Selecciona un reporte para comenzar')

    def test_paginacion_conserva_el_tipo_de_reporte(self):
        self.client.force_login(self.admin)
        for indice in range(26):
            orden = OrdenCompra.objects.create(
                numero_factura=f'R-P{indice:03d}',
                fecha=date(2026, 9, 1),
                proveedor=self.proveedor,
                estado=OrdenCompra.Estado.PENDIENTE,
            )
            orden.detalles.create(
                producto=self.producto, cantidad=1,
                precio_unitario=Decimal('1000.00'),
            )
            orden.calcular_total()

        resp = self.client.get(
            reverse('reportes_inicio'),
            {'tipo': 'compras', 'proveedor': self.proveedor.pk},
        )
        self.assertContains(resp, 'page=2')
        self.assertIn('tipo=compras', resp.context['filtros_qs'])
