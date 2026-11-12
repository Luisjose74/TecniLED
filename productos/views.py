from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Replace
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from .models import Categoria, MovimientoInventario, Producto, Proveedor
from .forms import CategoriaForm, EntradaInventarioForm, InactivarProveedorForm, ProductoForm, ProveedorEditarForm, ProveedorForm, SalidaInventarioForm

@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def productos_lista(request):
    query = request.GET.get('q', '').strip()
    categoria = request.GET.get('categoria', '').strip()

    productos = Producto.objects.select_related('proveedor', 'categoria')

    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) | Q(sku__icontains=query)
        )

        # G1-151: el filtro llega con el id de la categoría (se ignora si no existe)
    if categoria.isdigit() and Categoria.objects.filter(pk=categoria).exists():
        productos = productos.filter(categoria_id=categoria)
    else:
        categoria = ''  # valor manipulado en la URL: se ignora

    paginador = Paginator(productos, 10)
    pagina = paginador.get_page(request.GET.get('page'))

    return render(request, 'productos/productos_lista.html', {
        'productos': pagina,
        'query': query,
        'categoria': categoria,
        'categorias': Categoria.objects.all(),
    })


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def crear_producto(request):
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            producto = form.save()
            messages.success(request, f'Producto "{producto.nombre}" registrado correctamente.')
            return redirect('productos_lista')
    else:
        form = ProductoForm()

    return render(request, 'productos/productos_crear.html', {'form': form})


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def editar_producto(request, pk):
    """G1-145: modifica un producto existente (mismo formulario del diseño, precargado)."""
    producto = get_object_or_404(Producto, pk=pk)

        # G1-146: un producto inactivo está retirado también de la edición
    if not producto.activo:
        messages.error(request, f'El producto "{producto.nombre}" está inactivo. Actívalo para poder editarlo.')
        return redirect('productos_lista')

    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES, instance=producto)
        if form.is_valid():
            producto = form.save()
            messages.success(request, f'Producto "{producto.nombre}" actualizado correctamente.')
            return redirect('productos_lista')
    else:
        form = ProductoForm(instance=producto)

    return render(request, 'productos/productos_crear.html', {
        'form': form,
        'producto': producto,  # su presencia activa el "modo edición" en la plantilla
    })
    

@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
@require_POST
def cambiar_estado_producto(request, pk, activar):
    """G1-146: activa o desactiva un producto (no se elimina nada).
    `activar` llega desde urls.py: False en /desactivar/, True en /activar/."""
    producto = get_object_or_404(Producto, pk=pk)

    # Volver a la misma página de la lista (con su búsqueda/filtro/paginación).
    # Solo se acepta una ruta interna del propio sitio.
    siguiente = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        siguiente = reverse('productos_lista')

    if producto.activo == activar:
        estado = 'activo' if activar else 'inactivo'
        messages.error(request, f'El producto "{producto.nombre}" ya está {estado}.')
        return redirect(siguiente)

    producto.activo = activar
    producto.save(update_fields=['activo', 'actualizado_en'])
    if activar:
        messages.success(request, f'Producto "{producto.nombre}" activado: vuelve a estar disponible para venta y edición.')
    else:
        messages.success(request, f'Producto "{producto.nombre}" desactivado: queda retirado de la venta y de la edición.')
    return redirect(siguiente)
    
@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
@require_POST
def alternar_destacado(request, producto_id):
    """Activa/desactiva ''Destacado en inicio' (interruptor verde de la tabla)."""
    producto = get_object_or_404(Producto, pk=producto_id)
    producto.destacado_en_inicio = not producto.destacado_en_inicio
    producto.save(update_fields=['destacado_en_inicio', 'actualizado_en'])

    # Volver a la misma página, con la búsqueda/filtro/paginación que tenía.
    # Solo se acepta una ruta interna del propio sitio.
    siguiente = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        siguiente = reverse('productos_lista')
    return redirect(siguiente)


def producto_detalle(request, producto_id):
    # Página pública: la ve cualquier cliente, por eso NO lleva @login_required

    # 1) Buscar el producto que el usuario quiere ver
    producto = get_object_or_404(Producto, pk=producto_id, activo=True)

    # 2) Buscar productos relacionados (misma categoría, sin repetir este, máximo 2)
    relacionados = Producto.objects.filter(
        categoria=producto.categoria, activo=True
    ).exclude(pk=producto.pk)[:2]

    # 3) Enviar las dos cosas a la plantilla
    return render(request, 'productos/producto_detalle.html', {
        'producto': producto,
        'relacionados': relacionados,
    })


@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
def proveedores_lista(request):
    query = request.GET.get('q', '').strip()
    proveedores = Proveedor.objects.prefetch_related('productos')

    if query:
        # G1-134: busca por nombre o NIT. El NIT también se encuentra si se escribe
        # sin guiones, puntos ni espacios (ej: 9001234567 encuentra 900123456-7).
        nit_buscado = query.replace('-', '').replace('.', '').replace(' ', '')
        filtro = Q(nombre__icontains=query) | Q(nit__icontains=query)
        if nit_buscado:
            proveedores = proveedores.annotate(
                nit_limpio=Replace(
                    Replace(Replace('nit', Value('-'), Value('')), Value('.'), Value('')),
                    Value(' '), Value(''),
                )
            )
            filtro |= Q(nit_limpio__icontains=nit_buscado)
        proveedores = proveedores.filter(filtro)

    pagina = Paginator(proveedores, 10).get_page(request.GET.get('page'))
    return render(request, 'productos/proveedores_lista.html', {
        'proveedores': pagina,
        'query': query,
    })


@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
def crear_proveedor(request):
    if request.method == 'POST':
        form = ProveedorForm(request.POST)
        if form.is_valid():
            proveedor = form.save()
            elegidos = form.cleaned_data['productos']
            # Los desmarcados quedan sin proveedor; los marcados pasan a este proveedor
            proveedor.productos.exclude(pk__in=elegidos).update(proveedor=None)
            elegidos.update(proveedor=proveedor)
            messages.success(request, f'Proveedor "{proveedor.nombre}" registrado correctamente.')
            return redirect('proveedores_lista')
    else:
        form = ProveedorForm()

    return render(request, 'productos/proveedores_crear.html', {'form': form})




@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
def editar_proveedor(request, pk):
    """G1-137: actualiza contacto/dirección/correo. Nombre y NIT no se modifican."""
    proveedor = get_object_or_404(Proveedor, pk=pk)

    if request.method == 'POST':
        form = ProveedorEditarForm(request.POST, instance=proveedor)
        if form.is_valid():
            proveedor = form.save()
            elegidos = form.cleaned_data['productos']
            # Los desmarcados quedan sin proveedor; los marcados pasan a este proveedor
            proveedor.productos.exclude(pk__in=elegidos).update(proveedor=None)
            elegidos.update(proveedor=proveedor)
            messages.success(request, f'Proveedor "{proveedor.nombre}" actualizado correctamente.')
            return redirect('proveedores_lista')
    else:
        form = ProveedorEditarForm(instance=proveedor)

    return render(request, 'productos/proveedores_crear.html', {
        'form': form,
        'proveedor': proveedor,  # su presencia activa el "modo edición" en la plantilla
    })
    
    
    


@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
@require_POST
def inactivar_proveedor(request, pk):
    """G1-138: inactiva un proveedor registrando el motivo. No elimina nada."""
    proveedor = get_object_or_404(Proveedor, pk=pk)

    # Volver a la misma página de la lista (con su búsqueda/paginación).
    # Solo se acepta una ruta interna del propio sitio.
    siguiente = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        siguiente = reverse('proveedores_lista')

    if not proveedor.activo:
        messages.warning(request, f'El proveedor "{proveedor.nombre}" ya está inactivo.')
        return redirect(siguiente)

    form = InactivarProveedorForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.errors['motivo'][0])
        return redirect(siguiente)

    proveedor.inactivar(form.cleaned_data['motivo'])
    messages.success(request, f'Proveedor "{proveedor.nombre}" inactivado correctamente.')
    return redirect(siguiente)




@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
@require_POST
def reactivar_proveedor(request, pk):
    """Vuelve a activar un proveedor que había sido inactivado."""
    proveedor = get_object_or_404(Proveedor, pk=pk)

    siguiente = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        siguiente = reverse('proveedores_lista')

    if proveedor.activo:
        messages.warning(request, f'El proveedor "{proveedor.nombre}" ya está activo.')
        return redirect(siguiente)

    proveedor.reactivar()
    messages.success(request, f'Proveedor "{proveedor.nombre}" reactivado correctamente.')
    return redirect(siguiente)

# ---------------------------------------------------------------------------
# G1-151: gestión de categorías
# ---------------------------------------------------------------------------
def _render_categorias(request, form, modal_abierto='', categoria_editada=None):
    """Dibuja la lista; si hubo un error al guardar, la plantilla reabre el modal con el error."""
    query = request.GET.get('q', '').strip()
    categorias = Categoria.objects.annotate(total_productos=Count('productos'))
    if query:
        categorias = categorias.filter(nombre__icontains=query)
    return render(request, 'productos/categorias_lista.html', {
        'categorias': categorias,
        'query': query,
        'form': form,
        'modal_abierto': modal_abierto,        # '', 'crear' o 'editar'
        'categoria_editada': categoria_editada,
    })


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def categorias_lista(request):
    return _render_categorias(request, CategoriaForm())


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
@require_POST
def crear_categoria(request):
    form = CategoriaForm(request.POST)
    if form.is_valid():
        categoria = form.save()
        messages.success(request, f'Categoría "{categoria.nombre}" creada correctamente.')
        return redirect('categorias_lista')
    return _render_categorias(request, form, modal_abierto='crear')


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
@require_POST
def editar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    form = CategoriaForm(request.POST, instance=categoria)
    if form.is_valid():
        categoria = form.save()
        messages.success(request, f'Categoría "{categoria.nombre}" actualizada correctamente.')
        return redirect('categorias_lista')
    return _render_categorias(request, form, modal_abierto='editar', categoria_editada=categoria)



# ---------------------------------------------------------------------------
# G1-149: entradas de inventario
# ---------------------------------------------------------------------------
def _render_entradas(request, form, abrir_modal=False):
    """Dibuja el historial de entradas; si hubo un error, la plantilla reabre el modal."""
    query = request.GET.get('q', '').strip()
    movimientos = MovimientoInventario.objects.filter(
        tipo=MovimientoInventario.Tipo.ENTRADA
    ).select_related('producto', 'usuario')
    if query:
        movimientos = movimientos.filter(Q(producto__nombre__icontains=query) | Q(producto__sku__icontains=query))
    pagina = Paginator(movimientos, 10).get_page(request.GET.get('page'))
    return render(request, 'productos/entradas_lista.html', {
        'movimientos': pagina,
        'query': query,
        'form': form,
        'abrir_modal': abrir_modal,
    })


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def entradas_lista(request):
    return _render_entradas(request, EntradaInventarioForm())


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
@require_POST
def registrar_entrada(request):
    form = EntradaInventarioForm(request.POST)
    if form.is_valid():
        producto = form.cleaned_data['producto']
        cantidad = form.cleaned_data['cantidad']
        try:
            movimiento = MovimientoInventario.registrar_entrada(
                producto, cantidad, usuario=request.user, observacion=form.cleaned_data['observacion'],
            )
        except ValueError as error:  # p. ej. el producto se inactivó justo antes de guardar
            form.add_error(None, str(error))
        else:
            messages.success(
                request,
                f'Entrada registrada: +{cantidad} unidades de "{producto.nombre}". '
                f'Stock actual: {movimiento.stock_resultante}.'
            )
            return redirect('entradas_lista')
    return _render_entradas(request, form, abrir_modal=True)


# ---------------------------------------------------------------------------
# G1-152: salidas de inventario
# ---------------------------------------------------------------------------
def _render_salidas(request, form, abrir_modal=False):
    """Dibuja el historial de salidas; si hubo un error, la plantilla reabre el modal."""
    query = request.GET.get('q', '').strip()
    movimientos = MovimientoInventario.objects.filter(
        tipo=MovimientoInventario.Tipo.SALIDA
    ).select_related('producto', 'usuario')
    if query:
        movimientos = movimientos.filter(Q(producto__nombre__icontains=query) | Q(producto__sku__icontains=query))
    pagina = Paginator(movimientos, 10).get_page(request.GET.get('page'))
    return render(request, 'productos/salidas_lista.html', {
        'movimientos': pagina,
        'query': query,
        'form': form,
        'abrir_modal': abrir_modal,
    })


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def salidas_lista(request):
    return _render_salidas(request, SalidaInventarioForm())


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
@require_POST
def registrar_salida(request):
    form = SalidaInventarioForm(request.POST)
    if form.is_valid():
        producto = form.cleaned_data['producto']
        cantidad = form.cleaned_data['cantidad']
        try:
            movimiento = MovimientoInventario.registrar_salida(
                producto, cantidad, form.cleaned_data['motivo'],
                usuario=request.user, observacion=form.cleaned_data['observacion'],
            )
        except ValueError as error:  # p. ej. otro usuario sacó stock justo antes de guardar
            form.add_error(None, str(error))
        else:
            messages.success(
                request,
                f'Salida registrada: -{cantidad} unidades de "{producto.nombre}". '
                f'Stock actual: {movimiento.stock_resultante}.'
            )
            return redirect('salidas_lista')
    return _render_salidas(request, form, abrir_modal=True)


# ---------------------------------------------------------------------------
# G1-155 / G1-156 / G1-157: inventario actual, filtros y alertas de stock
# ---------------------------------------------------------------------------
def _decimal_parametro(valor):
    """Convierte un parámetro de la URL en Decimal; si no es válido devuelve None."""
    if valor in (None, ''):
        return None
    try:
        numero = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not numero.is_finite() or numero < 0:
        return None
    return numero


def _productos_filtrados(request):
    """G1-156: aplica los filtros combinables del inventario y devuelve la lista y los valores usados."""
    filtros = {
        'q': request.GET.get('q', '').strip(),
        'categoria': request.GET.get('categoria', '').strip(),
        'proveedor': request.GET.get('proveedor', '').strip(),
        'estado': request.GET.get('estado', '').strip(),
        'existencia': request.GET.get('existencia', '').strip(),
        'precio_min': request.GET.get('precio_min', '').strip(),
        'precio_max': request.GET.get('precio_max', '').strip(),
    }

    productos = Producto.objects.select_related('proveedor', 'categoria').annotate(
        valor_total=ExpressionWrapper(
            F('stock') * F('precio'),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )

    if filtros['q']:
        productos = productos.filter(
            Q(nombre__icontains=filtros['q'])
            | Q(sku__icontains=filtros['q'])
            | Q(ubicacion__icontains=filtros['q'])
        )

    if filtros['categoria'].isdigit() and Categoria.objects.filter(pk=filtros['categoria']).exists():
        productos = productos.filter(categoria_id=filtros['categoria'])
    else:
        filtros['categoria'] = ''

    if filtros['proveedor'].isdigit() and Proveedor.objects.filter(pk=filtros['proveedor']).exists():
        productos = productos.filter(proveedor_id=filtros['proveedor'])
    else:
        filtros['proveedor'] = ''

    if filtros['estado'] == 'activos':
        productos = productos.filter(activo=True)
    elif filtros['estado'] == 'inactivos':
        productos = productos.filter(activo=False)
    else:
        filtros['estado'] = ''

    if filtros['existencia'] == 'agotados':
        productos = productos.filter(stock=0)
    elif filtros['existencia'] == 'bajo':
        productos = productos.filter(stock_minimo__gt=0, stock__lt=F('stock_minimo'))
    elif filtros['existencia'] == 'disponibles':
        productos = productos.filter(stock__gt=0)
    else:
        filtros['existencia'] = ''

    precio_min = _decimal_parametro(filtros['precio_min'])
    if precio_min is None:
        filtros['precio_min'] = ''
    else:
        productos = productos.filter(precio__gte=precio_min)

    precio_max = _decimal_parametro(filtros['precio_max'])
    if precio_max is None:
        filtros['precio_max'] = ''
    else:
        productos = productos.filter(precio__lte=precio_max)

    return productos, filtros


def _totales_inventario(productos):
    """G1-155: totales del inventario (respetan los filtros activos)."""
    agregados = productos.aggregate(
        total_unidades=Sum('stock'),
        total_valor=Sum('valor_total'),
        total_bajo_stock=Count('pk', filter=Q(stock_minimo__gt=0, stock__lt=F('stock_minimo'))),
        total_agotados=Count('pk', filter=Q(stock=0)),
    )
    return {
        'total_productos': productos.count(),
        'total_unidades': agregados['total_unidades'] or 0,
        'total_valor': agregados['total_valor'] or Decimal('0'),
        'total_bajo_stock': agregados['total_bajo_stock'] or 0,
        'total_agotados': agregados['total_agotados'] or 0,
    }


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def inventario_lista(request):
    """G1-155 / G1-156: listado del inventario actual con filtros combinables."""
    productos, filtros = _productos_filtrados(request)
    pagina = Paginator(productos, 10).get_page(request.GET.get('page'))
    return render(request, 'productos/inventario_lista.html', {
        'productos': pagina,
        'filtros': filtros,
        'categorias': Categoria.objects.all(),
        'proveedores': Proveedor.objects.all(),
        'totales': _totales_inventario(productos),
        # G1-157: los productos por debajo del mínimo se resaltan en la tabla
        'hay_stock_bajo': productos.filter(stock_minimo__gt=0, stock__lt=F('stock_minimo')).exists(),
    })


@login_required
@permission_required('Usuarios.gestionar_inventario', raise_exception=True)
def inventario_exportar(request):
    """G1-155: descarga el inventario filtrado en un archivo Excel (.xlsx)."""
    productos, _ = _productos_filtrados(request)

    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Inventario'
    encabezados = [
        'Código (SKU)', 'Producto', 'Categoría', 'Proveedor', 'Ubicación',
        'Existencias', 'Stock mínimo', 'Valor unitario', 'Valor total', 'Estado',
    ]
    hoja.append(encabezados)
    for celda in hoja[1]:
        celda.font = Font(bold=True)

    for producto in productos:
        estado = 'Inactivo' if not producto.activo else ('Stock bajo' if producto.stock_bajo else 'Activo')
        hoja.append([
            producto.sku,
            producto.nombre,
            producto.categoria.nombre if producto.categoria_id else '',
            producto.proveedor.nombre if producto.proveedor_id else '',
            producto.ubicacion,
            producto.stock,
            producto.stock_minimo,
            float(producto.precio),
            float(producto.valor_total),
            estado,
        ])

    for indice, ancho in enumerate([16, 40, 20, 28, 24, 12, 13, 15, 15, 12], start=1):
        hoja.column_dimensions[get_column_letter(indice)].width = ancho
    hoja.freeze_panes = 'A2'

    respuesta = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    nombre = f'inventario_{timezone.localdate():%Y%m%d}.xlsx'
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
    libro.save(respuesta)
    return respuesta



