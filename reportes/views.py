from decimal import Decimal
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, F, Sum
from django.shortcuts import render

from compras.models import DetalleOrdenCompra
from compras.views import _interpretar_filtro
from productos.models import Proveedor

# Los 8 reportes del diseño (ReportsPanel.tsx). Misma lista y mismo orden.
# ``permiso`` es opcional: si el usuario no lo tiene, la tarjeta se oculta.
REPORTES = [
    {'id': 'inventario', 'titulo': 'Inventario actual', 'descripcion': 'Existencias y valor total por producto.'},
    {'id': 'movimientos', 'titulo': 'Movimientos de inventario', 'descripcion': 'Entradas, salidas y ajustes registrados.'},
    {'id': 'bajas', 'titulo': 'Bajas de productos', 'descripcion': 'Productos retirados por daño, pérdida o vencimiento.'},
    {
        'id': 'compras',
        'titulo': 'Compras',
        'descripcion': 'Historial de compras por proveedor.',
        'permiso': 'Usuarios.gestionar_compras',
    },
    {'id': 'ventas', 'titulo': 'Ventas', 'descripcion': 'Pedidos y productos vendidos a clientes.'},
    {'id': 'arqueo', 'titulo': 'Arqueo de inventario', 'descripcion': 'Comparación entre el stock del sistema y el conteo físico.'},
    {'id': 'rotacion', 'titulo': 'Alta y baja rotación', 'descripcion': 'Qué se vende rápido y qué se queda en bodega.'},
    {'id': 'margen', 'titulo': 'Costo de compra vs. precio de venta', 'descripcion': 'Margen de ganancia de cada producto.'},
]


def _reportes_visibles(usuario):
    """Oculta las tarjetas de los reportes para los que falta permiso."""
    return [
        reporte for reporte in REPORTES
        if not reporte.get('permiso') or usuario.has_perm(reporte['permiso'])
    ]


def _contexto_historial_compras(request):
    """G1-162: historial de compras de un proveedor, ahora dentro de Reportes."""
    proveedor_texto = request.GET.get('proveedor', '').strip()
    desde_texto = request.GET.get('desde', '').strip()
    hasta_texto = request.GET.get('hasta', '').strip()
    desde = _interpretar_filtro(desde_texto)
    hasta = _interpretar_filtro(hasta_texto)

    proveedor = None
    detalles = DetalleOrdenCompra.objects.none()
    resumen = {'compras': 0, 'productos': 0, 'total': Decimal('0')}

    if proveedor_texto.isdigit():
        proveedor = Proveedor.objects.filter(pk=int(proveedor_texto)).first()

    if proveedor:
        detalles = DetalleOrdenCompra.objects.filter(
            orden__proveedor=proveedor
        ).select_related('orden', 'producto')
        if desde:
            detalles = detalles.filter(orden__fecha__gte=desde)
        if hasta:
            detalles = detalles.filter(orden__fecha__lte=hasta)
        detalles = detalles.order_by(
            '-orden__fecha', '-orden__id', 'producto__nombre'
        )
        agregados = detalles.aggregate(
            compras=Count('orden', distinct=True),
            productos=Sum('cantidad'),
            total=Sum(F('cantidad') * F('precio_unitario')),
        )
        resumen = {
            'compras': agregados['compras'] or 0,
            'productos': agregados['productos'] or 0,
            'total': agregados['total'] or Decimal('0'),
        }

    error_rango = bool(desde and hasta and desde > hasta)

    pagina = Paginator(detalles, 25).get_page(request.GET.get('page'))
    # ``tipo`` viaja en los enlaces de paginación para no perder el reporte.
    filtros_qs = urlencode({
        clave: valor for clave, valor in {
            'tipo': 'compras',
            'proveedor': proveedor_texto if proveedor else '',
            'desde': desde_texto if desde else '',
            'hasta': hasta_texto if hasta else '',
        }.items() if valor
    })

    return {
        'proveedores': Proveedor.objects.order_by('nombre'),
        'proveedor': proveedor,
        'proveedor_id': proveedor_texto,
        'desde': desde_texto,
        'hasta': hasta_texto,
        'error_rango': error_rango,
        'detalles': pagina,
        'resumen': resumen,
        'filtros_qs': filtros_qs,
    }


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def reportes_inicio(request):
    """Pantalla de Reportes: tarjetas de selección y el reporte elegido."""
    tipo = request.GET.get('tipo', '')
    if tipo not in [reporte['id'] for reporte in REPORTES]:
        tipo = ''

    if tipo:
        reporte = next(item for item in REPORTES if item['id'] == tipo)
        permiso = reporte.get('permiso')
        # Acceso directo por URL a un reporte sin permiso: 403 (no se oculta).
        if permiso and not request.user.has_perm(permiso):
            raise PermissionDenied

    contexto = {
        'reportes': _reportes_visibles(request.user),
        'tipo': tipo,
    }
    if tipo == 'compras':
        contexto.update(_contexto_historial_compras(request))
    return render(request, 'reportes/reportes.html', contexto)
