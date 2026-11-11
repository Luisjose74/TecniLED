from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from productos.models import Producto, Proveedor

# G1-159: documentos aceptados como remisión o factura del proveedor
EXTENSIONES_REMISION = ('pdf', 'png', 'jpg', 'jpeg')
TAMANO_MAXIMO_REMISION = 5 * 1024 * 1024  # 5 MB


def validar_tamano_remision(archivo):
    """Rechaza archivos que superen el tamaño permitido (5 MB)."""
    if archivo.size > TAMANO_MAXIMO_REMISION:
        raise ValidationError('El archivo no puede superar los 5 MB.')


class OrdenCompra(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        RECIBIDA = 'recibida', 'Recibida'
        ANULADA = 'anulada', 'Anulada'

    numero_factura = models.CharField('Número de orden/factura', max_length=30, unique=True)
    fecha = models.DateField('Fecha', default=timezone.localdate)
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT, related_name='ordenes_compra',
    )
    estado = models.CharField(
        max_length=10, choices=Estado.choices, default=Estado.PENDIENTE,
    )
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # --- G1-159: soporte documental de la recepción de mercancía ---
    remision = models.FileField(
        'Remisión o factura del proveedor',
        upload_to='remisiones/%Y/%m/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                EXTENSIONES_REMISION,
                message='Solo se permiten archivos PDF o imágenes JPG/PNG.',
            ),
            validar_tamano_remision,
        ],
        help_text='PDF o imagen (JPG, PNG). Tamaño máximo 5 MB.',
    )

    # --- Auditoría ---
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = 'orden de compra'
        verbose_name_plural = 'órdenes de compra'

    def __str__(self):
        return f'Orden {self.numero_factura} - {self.proveedor}'

    def clean(self):
        # G1-132: no se puede asociar un proveedor inactivo a una orden NUEVA.
        # (Si la orden ya existe, se permite que su proveedor quede inactivo después.)
        if self._state.adding and self.proveedor_id and not self.proveedor.activo:
            raise ValidationError({
                'proveedor': 'No puedes asociar un proveedor inactivo a una orden de compra.'
            })

    def calcular_total(self):
        """Suma los subtotales de todas las líneas y guarda el resultado."""
        self.total = sum(
            (linea.subtotal for linea in self.detalles.all()), Decimal('0')
        )
        self.save(update_fields=['total', 'actualizado_en'])
        return self.total

    @property
    def es_editable(self):
        """Solo las órdenes pendientes se pueden modificar (G1-164)."""
        return self.estado == self.Estado.PENDIENTE

    @property
    def tiene_remision(self):
        return bool(self.remision)

    @property
    def nombre_remision(self):
        """Nombre original del archivo adjunto (sin la ruta de almacenamiento)."""
        return Path(self.remision.name).name if self.remision else ''

    @property
    def remision_es_imagen(self):
        """True si el soporte adjunto es una imagen que se puede previsualizar."""
        if not self.remision:
            return False
        return Path(self.remision.name).suffix.lower() in ('.png', '.jpg', '.jpeg')


class DetalleOrdenCompra(models.Model):
    orden = models.ForeignKey(
        OrdenCompra, on_delete=models.CASCADE, related_name='detalles',
    )
    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name='detalles_compra',
    )
    cantidad = models.PositiveIntegerField('Cantidad')
    precio_unitario = models.DecimalField('Precio unitario', max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'línea de la orden'
        verbose_name_plural = 'líneas de la orden'

    def __str__(self):
        return f'{self.producto.sku} x {self.cantidad}'

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def clean(self):
        if self.cantidad is not None and self.cantidad < 1:
            raise ValidationError({'cantidad': 'La cantidad debe ser al menos 1.'})
        if self.precio_unitario is not None and self.precio_unitario <= 0:
            raise ValidationError({'precio_unitario': 'El precio unitario debe ser mayor que 0.'})