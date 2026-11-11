from datetime import datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from productos.models import Proveedor

from .forms import (
    DetalleEdicionFormSet,
    DetalleFormSet,
    OrdenCompraForm,
    RemisionForm,
)
from .models import OrdenCompra

TIPOS_EXPORTACION = {'xlsx', 'pdf'}

COLOR_PRIMARIO = 'F2AE30'


def _interpretar_fecha(texto):
    """Devuelve una fecha si el texto parece una (2026-10-14 o 14/10/2026); si no, None."""
    for formato in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _interpretar_filtro(texto):
    """Convierte el valor de un <input type="date"> en fecha (o None si no es válido)."""
    try:
        return datetime.strptime(texto or '', '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _filtrar_ordenes(request):
    """Aplica los filtros de G1-161 y devuelve las órdenes junto con el contexto."""
    query = request.GET.get('q', '').strip()
    desde_texto = request.GET.get('desde', '').strip()
    hasta_texto = request.GET.get('hasta', '').strip()
    proveedor_texto = request.GET.get('proveedor', '').strip()
    estado = request.GET.get('estado', '').strip()

    ordenes = OrdenCompra.objects.select_related('proveedor')

    if query:
        filtro = Q(numero_factura__icontains=query) | Q(proveedor__nombre__icontains=query)
        fecha = _interpretar_fecha(query)
        if fecha:
            filtro |= Q(fecha=fecha)
        ordenes = ordenes.filter(filtro)

    desde = _interpretar_filtro(desde_texto)
    hasta = _interpretar_filtro(hasta_texto)
    if desde:
        ordenes = ordenes.filter(fecha__gte=desde)
    if hasta:
        ordenes = ordenes.filter(fecha__lte=hasta)

    if proveedor_texto.isdigit():
        ordenes = ordenes.filter(proveedor_id=int(proveedor_texto))

    if estado in OrdenCompra.Estado.values:
        ordenes = ordenes.filter(estado=estado)

    error_rango = bool(desde and hasta and desde > hasta)

    filtros = {
        'q': query,
        'desde': desde_texto,
        'hasta': hasta_texto,
        'proveedor': proveedor_texto if proveedor_texto.isdigit() else '',
        'estado': estado if estado in OrdenCompra.Estado.values else '',
    }
    # Solo se conservan en la URL los filtros que realmente se aplicaron
    aplicados = {
        'q': query,
        'desde': desde_texto if desde else '',
        'hasta': hasta_texto if hasta else '',
        'proveedor': filtros['proveedor'],
        'estado': filtros['estado'],
    }
    filtros_qs = urlencode({
        clave: valor for clave, valor in aplicados.items() if valor
    })

    contexto = {
        'filtros': filtros,
        'filtros_qs': filtros_qs,
        'query': query,
        'error_rango': error_rango,
        'proveedores': Proveedor.objects.order_by('nombre'),
        'estados': OrdenCompra.Estado.choices,
    }
    return ordenes, contexto


@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
def ordenes_lista(request):
    """G1-160 / G1-161: lista las órdenes y permite filtrarlas por periodo."""
    ordenes, contexto = _filtrar_ordenes(request)
    pagina = Paginator(ordenes, 10).get_page(request.GET.get('page'))
    contexto['ordenes'] = pagina
    return render(request, 'compras/ordenes_lista.html', contexto)


@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
def crear_orden(request):
    """G1-158 / G1-132: registra una orden de compra con sus productos."""
    if request.method == 'POST':
        form = OrdenCompraForm(request.POST)
        formset = DetalleFormSet(request.POST)
        # Se validan los dos SIEMPRE, así se muestran todos los errores juntos
        cabecera_ok = form.is_valid()
        lineas_ok = formset.is_valid()
        if cabecera_ok and lineas_ok:
            # atomic: o se guarda todo (orden + líneas + total) o no se guarda nada
            with transaction.atomic():
                orden = form.save()          # estado queda en "Pendiente"
                formset.instance = orden
                formset.save()
                orden.calcular_total()
            messages.success(
                request, f'Orden "{orden.numero_factura}" registrada correctamente.'
            )
            return redirect('ordenes_lista')
    else:
        form = OrdenCompraForm()
        formset = DetalleFormSet()

    return render(request, 'compras/orden_crear.html', {
        'form': form,
        'formset': formset,
    })


@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
def orden_detalle(request, pk):
    """G1-159: detalle de la orden, con acceso a la remisión adjunta."""
    orden = get_object_or_404(
        OrdenCompra.objects.select_related('proveedor').prefetch_related(
            'detalles__producto'
        ),
        pk=pk,
    )
    return render(request, 'compras/orden_detalle.html', {'orden': orden})


@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
def editar_orden(request, pk):
    """G1-164: modifica una orden pendiente y recalcula su total."""
    orden = get_object_or_404(OrdenCompra, pk=pk)

    if not orden.es_editable:
        messages.info(
            request,
            f'La orden "{orden.numero_factura}" está {orden.get_estado_display().lower()} '
            'y ya no se puede modificar. Solo las órdenes pendientes son editables.',
        )
        return redirect('orden_detalle', pk=orden.pk)

    if request.method == 'POST':
        form = OrdenCompraForm(request.POST, instance=orden)
        formset = DetalleEdicionFormSet(request.POST, instance=orden)
        cabecera_ok = form.is_valid()
        lineas_ok = formset.is_valid()
        if cabecera_ok and lineas_ok:
            with transaction.atomic():
                orden = form.save()
                formset.save()
                orden.calcular_total()
            messages.success(
                request,
                f'Orden "{orden.numero_factura}" actualizada. '
                f'Nuevo total: ${orden.total:,.2f}.',
            )
            return redirect('orden_detalle', pk=orden.pk)
    else:
        form = OrdenCompraForm(instance=orden)
        formset = DetalleEdicionFormSet(instance=orden)

    return render(request, 'compras/orden_editar.html', {
        'orden': orden,
        'form': form,
        'formset': formset,
    })


@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
def adjuntar_remision(request, pk):
    """G1-159: guarda la remisión o factura del proveedor asociada a la orden."""
    orden = get_object_or_404(OrdenCompra, pk=pk)

    if request.method == 'POST':
        archivo_anterior = orden.remision.name if orden.remision else ''
        form = RemisionForm(request.POST, request.FILES, instance=orden)
        if form.is_valid():
            orden = form.save()
            if archivo_anterior and archivo_anterior != orden.remision.name:
                # No se acumulan versiones viejas del documento
                default_storage.delete(archivo_anterior)
            messages.success(
                request,
                f'Remisión adjuntada a la orden "{orden.numero_factura}".',
            )
            return redirect('orden_detalle', pk=orden.pk)
    else:
        form = RemisionForm(instance=orden)

    return render(request, 'compras/orden_remision.html', {
        'orden': orden,
        'form': form,
    })


def _descripcion_filtros(filtros):
    """Texto legible con el periodo y los filtros usados en una exportación."""
    partes = []
    desde = _interpretar_filtro(filtros.get('desde', ''))
    hasta = _interpretar_filtro(filtros.get('hasta', ''))
    if desde and hasta:
        partes.append(f'Periodo: {desde:%d/%m/%Y} a {hasta:%d/%m/%Y}')
    elif desde:
        partes.append(f'Desde: {desde:%d/%m/%Y}')
    elif hasta:
        partes.append(f'Hasta: {hasta:%d/%m/%Y}')
    else:
        partes.append('Periodo: todas las compras registradas')
    if filtros.get('estado'):
        estado = dict(OrdenCompra.Estado.choices).get(filtros['estado'])
        if estado:
            partes.append(f'Estado: {estado}')
    return ' · '.join(partes)


def _nombre_exportacion(formato, filtros):
    desde = _interpretar_filtro(filtros.get('desde', ''))
    hasta = _interpretar_filtro(filtros.get('hasta', ''))
    inicio = f'{desde:%Y%m%d}' if desde else 'inicio'
    fin = f'{hasta:%Y%m%d}' if hasta else timezone.localdate().strftime('%Y%m%d')
    return f'compras_{inicio}_{fin}.{formato}'


def _exportar_excel(ordenes, filtros):
    """Genera el listado de compras en un archivo .xlsx real."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Compras'

    hoja['A1'] = 'TECNILED - Listado de compras'
    hoja['A1'].font = Font(bold=True, size=14)
    hoja.merge_cells('A1:E1')
    hoja['A2'] = _descripcion_filtros(filtros)
    hoja['A2'].font = Font(size=10, color='555555')
    hoja.merge_cells('A2:E2')

    encabezados = ['N.º orden/factura', 'Fecha', 'Proveedor', 'Estado', 'Total']
    for columna, titulo in enumerate(encabezados, start=1):
        celda = hoja.cell(row=4, column=columna, value=titulo)
        celda.font = Font(bold=True, color='000000')
        celda.fill = PatternFill('solid', fgColor=COLOR_PRIMARIO)
        celda.alignment = Alignment(horizontal='center')

    fila = 5
    total_general = Decimal('0')
    for orden in ordenes:
        hoja.cell(row=fila, column=1, value=orden.numero_factura)
        fecha = hoja.cell(row=fila, column=2, value=orden.fecha)
        fecha.number_format = 'DD/MM/YYYY'
        hoja.cell(row=fila, column=3, value=orden.proveedor.nombre)
        hoja.cell(row=fila, column=4, value=orden.get_estado_display())
        valor = hoja.cell(row=fila, column=5, value=float(orden.total))
        valor.number_format = '"$"#,##0.00'
        total_general += orden.total
        fila += 1

    etiqueta_total = hoja.cell(row=fila, column=4, value='Total general')
    etiqueta_total.font = Font(bold=True)
    etiqueta_total.alignment = Alignment(horizontal='right')
    celda_total = hoja.cell(row=fila, column=5, value=float(total_general))
    celda_total.font = Font(bold=True)
    celda_total.number_format = '"$"#,##0.00'

    hoja.freeze_panes = 'A5'
    hoja.auto_filter.ref = f'A4:E{fila - 1}'
    for indice, ancho in enumerate([22, 14, 32, 14, 16], start=1):
        hoja.column_dimensions[get_column_letter(indice)].width = ancho

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _moneda(valor):
    """Formatea un valor como $ 1.234,56 (mismo formato que la interfaz)."""
    return f'$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _pie_pagina(canvas, documento):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.HexColor('#666666'))
    canvas.drawString(1.5 * cm, 1 * cm, 'TECNILED - Listado de compras')
    canvas.drawRightString(
        documento.pagesize[0] - 1.5 * cm, 1 * cm, f'Página {canvas.getPageNumber()}'
    )
    canvas.restoreState()


def _exportar_pdf(ordenes, filtros):
    """Genera el listado de compras en un PDF descargable."""
    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=landscape(letter),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.8 * cm,
        title='Listado de compras - TECNILED',
    )
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'TituloTecniled', parent=estilos['Title'], fontSize=16, spaceAfter=4
    )
    subtitulo = ParagraphStyle(
        'SubtituloTecniled', parent=estilos['Normal'], fontSize=9,
        textColor=colors.HexColor('#555555'),
    )
    # Celdas con texto largo (factura y proveedor) se envuelven en Paragraph
    # para que no se salgan de la columna cuando el nombre es extenso.
    celda = ParagraphStyle(
        'CeldaTecniled', parent=estilos['Normal'], fontSize=8.5, leading=10.5,
    )
    elementos = [
        Paragraph('TECNILED - Listado de compras', titulo),
        Paragraph(_descripcion_filtros(filtros), subtitulo),
        Spacer(1, 0.4 * cm),
    ]

    datos = [['N.º orden/factura', 'Fecha', 'Proveedor', 'Estado', 'Total']]
    total_general = Decimal('0')
    for orden in ordenes:
        datos.append([
            Paragraph(escape(orden.numero_factura), celda),
            orden.fecha.strftime('%d/%m/%Y'),
            Paragraph(escape(orden.proveedor.nombre), celda),
            orden.get_estado_display(),
            _moneda(orden.total),
        ])
        total_general += orden.total
    datos.append(['', '', '', 'Total general', _moneda(total_general)])

    tabla = Table(
        datos, repeatRows=1,
        colWidths=[4.5 * cm, 2.6 * cm, 8.4 * cm, 3 * cm, 3.2 * cm],
    )
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(f'#{COLOR_PRIMARIO}')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D1D5DB')),
        ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [
            colors.white, colors.HexColor('#F9FAFB'),
        ]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elementos.append(tabla)

    documento.build(elementos, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    return salida.getvalue()


@login_required
@permission_required('Usuarios.gestionar_compras', raise_exception=True)
def exportar_ordenes(request):
    """G1-161: descarga el listado filtrado en Excel o PDF."""
    formato = request.GET.get('formato', 'xlsx').lower()
    ordenes, contexto = _filtrar_ordenes(request)

    if formato not in TIPOS_EXPORTACION:
        messages.error(request, 'Formato de exportación no válido. Usa Excel o PDF.')
        return redirect(f"{reverse('ordenes_lista')}?{contexto['filtros_qs']}")

    if formato == 'pdf':
        contenido = _exportar_pdf(ordenes, contexto['filtros'])
        tipo = 'application/pdf'
    else:
        contenido = _exportar_excel(ordenes, contexto['filtros'])
        tipo = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta['Content-Disposition'] = (
        f'attachment; filename="{_nombre_exportacion(formato, contexto["filtros"])}"'
    )
    return respuesta
