from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render

# Los 8 reportes del diseño (ReportsPanel.tsx). Misma lista y mismo orden.
REPORTES = [
    {'id': 'inventario', 'titulo': 'Inventario actual', 'descripcion': 'Existencias y valor total por producto.'},
    {'id': 'movimientos', 'titulo': 'Movimientos de inventario', 'descripcion': 'Entradas, salidas y ajustes registrados.'},
    {'id': 'bajas', 'titulo': 'Bajas de productos', 'descripcion': 'Productos retirados por daño, pérdida o vencimiento.'},
    {'id': 'compras', 'titulo': 'Compras', 'descripcion': 'Compras realizadas a proveedores.'},
    {'id': 'ventas', 'titulo': 'Ventas', 'descripcion': 'Pedidos y productos vendidos a clientes.'},
    {'id': 'arqueo', 'titulo': 'Arqueo de inventario', 'descripcion': 'Comparación entre el stock del sistema y el conteo físico.'},
    {'id': 'rotacion', 'titulo': 'Alta y baja rotación', 'descripcion': 'Qué se vende rápido y qué se queda en bodega.'},
    {'id': 'margen', 'titulo': 'Costo de compra vs. precio de venta', 'descripcion': 'Margen de ganancia de cada producto.'},
]


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def reportes_inicio(request):
    """Pantalla de Reportes: tarjetas de selección (la tabla llega en el paso 2)."""
    tipo = request.GET.get('tipo', '')
    if tipo not in [r['id'] for r in REPORTES]:
        tipo = ''
    return render(request, 'reportes/reportes.html', {'reportes': REPORTES, 'tipo': tipo})